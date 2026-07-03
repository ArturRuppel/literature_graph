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
