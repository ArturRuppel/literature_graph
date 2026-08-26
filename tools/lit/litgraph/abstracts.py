"""Backfill missing abstracts onto curated papers from their stored full text (`lit abstracts`).

The gap this closes: OpenAlex and Crossref carry no abstract for most Springer Nature and
Elsevier papers — the publishers never deposit one — so `lit ingest` had nothing to write and
the curated file came out with no `abstract` key at all, silently. `ingest` now falls back to
the paper's own text at ingest time (see `fulltext.extract_abstract`); this is the same move for
the papers already on disk, the way `lit enrich` is for stubs ingested before their fields
existed. Run once, review the diff, commit.

Nothing here fetches: it reads the `<citekey>.md` that ingest already wrote beside the PDF.
Papers whose abstract cannot be *anchored* are reported, not guessed at — see the module comment
in `fulltext.py` for what "anchored" buys and why a wrong abstract is worse than a missing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


from . import store
from .fulltext import extract_abstract
from .yamlio import safe_yaml



@dataclass
class AbstractResult:
    filled: list[tuple[str, str]] = field(default_factory=list)  # (citekey, anchor)
    already: list[str] = field(default_factory=list)
    no_fulltext: list[str] = field(default_factory=list)
    unanchored: list[str] = field(default_factory=list)  # .md on disk, nothing safe to take
    flagged: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)  # PDF text damage


def _families(doc: dict) -> list[str]:
    """Author families from a curated file's `authors` list ("Family, Given" — SCHEMA §4).

    These are what anchors the unlabelled-abstract path onto the paper's byline, so a paper
    whose authors are already curated gets the better of the two extraction anchors for free.
    """
    out = []
    for a in doc.get("authors") or []:
        name = (a or {}).get("name") if isinstance(a, dict) else None
        if name:
            out.append(str(name).split(",")[0].strip())
    return out


def backfill(root: Path, pdf_dir: Path | None, dry_run: bool = False,
             only: tuple[str, ...] = ()) -> AbstractResult:
    """Fill `abstract` on every curated paper missing one, from its `<citekey>.md`.

    `only` restricts the sweep to the given citekeys. Papers that already carry an abstract are
    left alone — this backfills gaps, it never second-guesses a fetched abstract.
    """
    res = AbstractResult()
    pdfs = Path(pdf_dir) if pdf_dir else Path(root) / "pdfs"
    for path in sorted(store.curated_dir(root).glob("*.yaml")):
        key = path.stem
        if only and key not in only:
            continue
        doc = safe_yaml().load(path.read_text()) or {}
        if (doc.get("abstract") or "").strip():
            res.already.append(key)
            continue
        md = pdfs / f"{key}.md"
        if not md.is_file():
            res.no_fulltext.append(key)
            continue
        hit = extract_abstract(md.read_text(), _families(doc))
        if hit is None:
            res.unanchored.append(key)
            continue
        store.write_abstract(Path(root), key, hit.text, dry_run=dry_run)
        res.filled.append((key, hit.anchor))
        if hit.artifacts:
            res.flagged.append((key, hit.artifacts))
    return res
