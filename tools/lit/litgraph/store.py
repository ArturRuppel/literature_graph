"""Filesystem I/O: existing-key index, curated write, stubs merge, PDF rename (spec §4 D).

stubs.yaml is round-tripped with ruamel so the human's comments/formatting survive; merges
are additive and never delete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from .model import CuratedPaper, Stub

_yaml_rt = YAML()  # round-trip (preserves comments)
_yaml_rt.preserve_quotes = True
_yaml_rt.width = 4096                       # never re-wrap long scalars (titles, notes)
_yaml_rt.indent(mapping=2, sequence=4, offset=2)   # match the "  - {…}" sequence style on disk
_yaml_safe = YAML(typ="safe")


def curated_dir(root: Path) -> Path:
    return Path(root) / "curated"


def stubs_path(root: Path) -> Path:
    return Path(root) / "stubs.yaml"


def load_taken(root: Path) -> dict[str, str | None]:
    """Map every in-use citekey -> its DOI: curated/*.yaml stems + stubs.yaml keys."""
    root = Path(root)
    taken: dict[str, str | None] = {}
    cdir = curated_dir(root)
    if cdir.is_dir():
        for f in sorted(cdir.glob("*.yaml")):
            doi = None
            try:
                doc = _yaml_safe.load(f.read_text()) or {}
                doi = doc.get("doi")
            except Exception:
                pass
            taken[f.stem] = doi
    sp = stubs_path(root)
    if sp.exists():
        stubs = _yaml_safe.load(sp.read_text()) or {}
        for key, body in stubs.items():
            taken[key] = (body or {}).get("doi") if isinstance(body, dict) else None
    return taken


@dataclass
class WriteResult:
    curated_path: Path
    pdf_renamed_to: Path | None
    fulltext_path: Path | None
    stubs_added: list[str]
    stubs_deduped: list[str]


def write_curated(root: Path, paper: CuratedPaper, force: bool, dry_run: bool) -> Path:
    """Write curated/<citekey>.yaml; never overwrite a curated file unless `force`."""
    path = curated_dir(root) / f"{paper.citekey}.yaml"
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (use --force to overwrite)")
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(paper.to_yaml())
    return path


def merge_stubs(root: Path, stubs: list[Stub], dry_run: bool) -> tuple[list[str], list[str]]:
    """Additively merge stub entries into stubs.yaml. Returns (added, deduped) citekeys.

    A stub whose citekey already exists is treated as deduped (left untouched). A stub
    whose citekey is already a curated paper is also skipped (handled upstream by key
    allocation, but guarded here too).
    """
    sp = stubs_path(root)
    if sp.exists():
        doc = _yaml_rt.load(sp.read_text()) or {}
    else:
        from ruamel.yaml.comments import CommentedMap

        doc = CommentedMap()

    curated_stems = {f.stem for f in curated_dir(root).glob("*.yaml")} if curated_dir(root).is_dir() else set()

    added: list[str] = []
    deduped: list[str] = []
    for s in stubs:
        if s.citekey in doc or s.citekey in curated_stems:
            deduped.append(s.citekey)
            continue
        doc[s.citekey] = _to_commented(s.to_mapping())
        added.append(s.citekey)

    if not dry_run and added:
        sp.parent.mkdir(parents=True, exist_ok=True)
        with sp.open("w") as fh:
            _yaml_rt.dump(doc, fh)
    return added, deduped


def prune_curated_stubs(root: Path, dry_run: bool, extra_keys: tuple[str, ...] = ()) -> list[str]:
    """Drop from stubs.yaml every key that is now a curated paper (a §6.3 collision).

    A stub is a placeholder for an un-sliced container; the moment a paper is curated
    (its `curated/<key>.yaml` exists) that placeholder is stale and must go, or the build
    fails on the curated/stub collision. `extra_keys` lets a caller name a key that is being
    promoted in the same run (e.g. dry-run, where the curated file isn't on disk yet).
    Returns the citekeys actually removed; round-trips so comments/formatting survive.
    """
    sp = stubs_path(root)
    if not sp.exists():
        return []
    doc = _yaml_rt.load(sp.read_text()) or {}
    curated_stems = {f.stem for f in curated_dir(root).glob("*.yaml")} if curated_dir(root).is_dir() else set()
    curated_stems.update(extra_keys)
    removed = [k for k in list(doc) if k in curated_stems]
    if not removed:
        return []
    if not dry_run:
        for k in removed:
            del doc[k]
        with sp.open("w") as fh:
            _yaml_rt.dump(doc, fh)
    return removed


def _norm_doi(doi: str | None) -> str | None:
    """Bare, lower-cased DOI for matching (OpenAlex keeps case; DOIs are case-insensitive)."""
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE).lower() or None


@dataclass
class EnrichResult:
    enriched: list[str]   # stubs that gained authors and/or journal
    already: list[str]    # already complete (skipped; --force re-fetches these)
    no_doi: list[str]     # no DOI on the stub — nothing to look up
    unmatched: list[str]  # had a DOI but OpenAlex returned no work / no new fields


def enrich_stubs(root: Path, oa, dry_run: bool = False, force: bool = False) -> EnrichResult:
    """Backfill `authors` + `journal` onto existing stubs.yaml entries from OpenAlex (by DOI).

    A stub written before these fields existed carries only title/year/doi/type; this fills the
    gaps in one batched query. Only stubs missing a field are fetched unless `force`. New/other
    fields and comments are round-tripped; the two added keys append to each entry.
    """
    sp = stubs_path(root)
    if not sp.exists():
        return EnrichResult([], [], [], [])
    doc = _yaml_rt.load(sp.read_text()) or {}

    doi_to_keys: dict[str, list[str]] = {}
    already: list[str] = []
    no_doi: list[str] = []
    for key in list(doc):
        body = doc.get(key) or {}
        nd = _norm_doi(body.get("doi"))
        if not nd:
            no_doi.append(key)
            continue
        if body.get("authors") and body.get("journal") and not force:
            already.append(key)
            continue
        doi_to_keys.setdefault(nd, []).append(key)

    enriched: list[str] = []
    unmatched: list[str] = []
    if doi_to_keys:
        works = oa.fetch_works_by_doi(list(doi_to_keys))
        by_doi = {_norm_doi(w.doi): w for w in works if _norm_doi(w.doi)}
        for nd, keys in doi_to_keys.items():
            w = by_doi.get(nd)
            for key in keys:
                body = doc[key]
                names = [a.display_name for a in w.authors if a.display_name] if w else []
                changed = False
                if names and (force or not body.get("authors")):
                    body["authors"] = names
                    changed = True
                if w and w.venue_display and (force or not body.get("journal")):
                    body["journal"] = w.venue_display
                    changed = True
                (enriched if changed else unmatched).append(key)

    if not dry_run and enriched:
        with sp.open("w") as fh:
            _yaml_rt.dump(doc, fh)
    return EnrichResult(enriched, already, no_doi, unmatched)


def _to_commented(mapping: dict):
    from ruamel.yaml.comments import CommentedMap

    cm = CommentedMap()
    for k, v in mapping.items():
        cm[k] = v
    return cm


_SLICE_GROUPS = ("claims", "questions", "methods")


def _loc_cm(page: int, rects: list[list[float]]):
    """A compact `quote_loc` mapping: page + flow-style rects rounded to 4 dp (page fractions)."""
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    rects_seq = CommentedSeq()
    for r in rects:
        row = CommentedSeq(round(float(v), 4) for v in r)
        row.fa.set_flow_style()
        rects_seq.append(row)
    loc = CommentedMap()
    loc["page"] = int(page)
    loc["rects"] = rects_seq
    return loc


def write_quote_loc(root: Path, citekey: str, slice_id: str, page: int,
                    rects: list[list[float]]) -> Path:
    """Set (or replace) `quote_loc` on one slice of curated/<citekey>.yaml, round-tripped so
    the human's comments/formatting survive. `rects` are page fractions (0..1). Raises
    FileNotFoundError / KeyError if the file or slice id is absent."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no curated paper: {citekey}")
    doc = _yaml_rt.load(path.read_text()) or {}

    target = None
    for group in _SLICE_GROUPS:
        for s in doc.get(group, []) or []:
            if s.get("id") == slice_id:
                target = s
                break
        if target is not None:
            break
    if target is None:
        raise KeyError(f"no slice {slice_id} in {citekey}")

    target["quote_loc"] = _loc_cm(page, rects)
    with path.open("w") as fh:
        _yaml_rt.dump(doc, fh)
    return path


def write_quote_locs(root: Path, citekey: str, locs: dict[str, dict]) -> int:
    """Set `quote_loc` on many slices of curated/<citekey>.yaml in one round-trip (for the
    batch `lit locate`). `locs` maps slice_id -> {"page":int, "rects":[[...],...]}. Slice ids
    absent from the file are skipped. Returns the number written; writes nothing if none."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no curated paper: {citekey}")
    doc = _yaml_rt.load(path.read_text()) or {}
    by_id: dict = {}
    for group in _SLICE_GROUPS:
        for s in doc.get(group, []) or []:
            by_id[s.get("id")] = s
    n = 0
    for sid, loc in locs.items():
        s = by_id.get(sid)
        if s is None:
            continue
        s["quote_loc"] = _loc_cm(loc["page"], loc["rects"])
        n += 1
    if n:
        with path.open("w") as fh:
            _yaml_rt.dump(doc, fh)
    return n


def rename_pdf(pdf_path: Path, citekey: str, dry_run: bool) -> Path | None:
    """Rename the source PDF to <dir>/<citekey>.pdf. Never clobber a different file."""
    pdf_path = Path(pdf_path)
    target = pdf_path.with_name(f"{citekey}.pdf")
    if target == pdf_path:
        return target
    if target.exists():
        return None  # refuse to clobber; caller warns
    if not dry_run:
        pdf_path.rename(target)
    return target


def write_fulltext(pdf_path: Path, citekey: str, markdown: str, dry_run: bool) -> Path:
    """Write <citekey>.md beside the (renamed) PDF."""
    target = Path(pdf_path).with_name(f"{citekey}.md")
    if not dry_run:
        target.write_text(markdown)
    return target
