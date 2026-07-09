"""Deployment-local config (config.toml at the data root): paths + polite-pool mailto."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    root: Path  # holds curated/, stubs.yaml
    pdf_dir: Path | None  # external PDF dir (informational; rename happens beside the PDF)
    mailto: str  # OpenAlex/Crossref polite pool
    active: tuple[str, ...] = ()  # citekeys under active curation — the manual WIP list
    # (`[curation] active` in config.toml). Deployment-local curator state, not graph data:
    # it stays out of the shared YAML and only surfaces in the serve-only in-progress panel.


def load_config(root: str | Path) -> Config:
    """Load `<root>/config.toml` if present; otherwise sensible defaults."""
    root = Path(root)
    cfg_path = root / "config.toml"
    data: dict = {}
    if cfg_path.exists():
        data = tomllib.loads(cfg_path.read_text())
    pdf_dir = data.get("pdf_dir")
    curation = data.get("curation", {})
    active = curation.get("active", []) if isinstance(curation, dict) else []
    return Config(
        root=Path(data.get("root", root)),
        pdf_dir=Path(pdf_dir) if pdf_dir else None,
        mailto=data.get("mailto", ""),
        active=tuple(str(k) for k in active),
    )


def set_active(root: str | Path, citekey: str, active: bool) -> tuple[str, ...]:
    """Add or remove `citekey` from `[curation] active` in `<root>/config.toml`, round-tripped
    so the human's comments and formatting survive (the TOML analog of store.py's ruamel writes).
    Idempotent: adding an already-active key or removing an absent one is a no-op. Creates the
    file / the `[curation]` table / the `active` array as needed. Returns the new active tuple.

    This is the one writer both the in-browser right-click ("Curate this paper" → POST /active)
    and the `lit curate` CLI go through, so the move has a single source of truth. `lit serve`
    re-reads config.toml per request, so an edit here is picked up live on the next refresh."""
    import tomlkit

    root = Path(root)
    cfg_path = root / "config.toml"
    doc = tomlkit.parse(cfg_path.read_text()) if cfg_path.exists() else tomlkit.document()

    curation = doc.get("curation")
    if not isinstance(curation, dict):
        curation = tomlkit.table()
        doc["curation"] = curation
    if "active" not in curation:
        curation["active"] = tomlkit.array()

    arr = curation["active"]
    present = citekey in list(arr)
    if active and not present:
        arr.append(citekey)
    elif not active and present:
        # rebuild without the key (tomlkit arrays have no stable .remove by value)
        kept = [k for k in list(arr) if k != citekey]
        curation["active"] = tomlkit.array()
        for k in kept:
            curation["active"].append(k)

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(tomlkit.dumps(doc))
    return tuple(str(k) for k in curation["active"])
