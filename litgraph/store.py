"""Filesystem I/O: existing-key index, curated write, stubs merge, PDF rename (spec §4 D).

stubs.yaml is round-tripped with ruamel so the human's comments/formatting survive; merges
are additive and never delete.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML

from .citekey import _norm_doi
from .model import CuratedPaper, Stub

_yaml_rt = YAML()  # round-trip (preserves comments)
_yaml_rt.preserve_quotes = True
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


def _to_commented(mapping: dict):
    from ruamel.yaml.comments import CommentedMap

    cm = CommentedMap()
    for k, v in mapping.items():
        cm[k] = v
    return cm


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
