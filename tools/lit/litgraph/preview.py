"""Isolated single-paper preview for the curation loop.

During curation the agent *proposes* a paper's local subgraph in prose, then tokenizes it
into `curated/<citekey>.yaml` only once the human agrees. Prose is hard to parse. This
module renders a proposition the way it will actually look in the viewer — but **in
isolation**: one paper's card, its slices, and every edge it participates in, with each
cross-paper endpoint shown as its stub chip / synthesis band rather than a neighbouring
column. It reuses the real emit layer (`build.to_json_dict` + `build.render_html`), so a
preview can never drift from what `lit build` produces.

The proposition source is a **scratch YAML in the real `curated/` schema** — so it doubles
as the staging draft: when the human agrees, "tokenizing" is just promoting the scratch
slices into `curated/<citekey>.yaml`. The scratch paper is overlaid onto the loaded repo
(replacing the real paper of the same citekey), so its edges resolve against the real
stubs/broad nodes and are validated exactly as a build would validate them.
"""

from __future__ import annotations

import json
from pathlib import Path

from ruamel.yaml import YAML

from .build import render_html, to_json_dict
from .graph import (
    BuildError,
    Graph,
    compute_emergent,
    load_repo,
    paper_from_raw,
    validate,
)

_yaml = YAML(typ="safe")


def build_preview_graph(root: Path, citekey: str, scratch: Path | None = None) -> Graph:
    """Load the repo, optionally overlay a scratch paper under `citekey`, validate the whole
    (so the proposition's refs are checked against the real graph), and compute. Raises
    BuildError if `citekey` names no curated paper, or on any SCHEMA §6 violation."""
    papers, broad = load_repo(Path(root))
    if scratch is not None:
        raw = _yaml.load(Path(scratch).read_text(encoding="utf-8")) or {}
        papers[citekey] = paper_from_raw(citekey, raw)   # overlay/replace the focal paper
    focal = papers.get(citekey)
    if focal is None or not focal.curated:
        raise BuildError(f"no curated paper {citekey!r} to preview "
                         "(pass --scratch to overlay a proposition)")
    validate(papers, broad)
    return compute_emergent(papers, broad)


def _stub_entry(full: dict, key: str) -> dict | None:
    """A minimal stub-shaped entry for an outward edge target, whether the target is a real
    stub or another curated paper (isolation collapses every neighbour to a labelled chip)."""
    if key in full["stubs"]:
        return full["stubs"][key]
    p = full["papers"].get(key)
    if p is not None:
        return {"title": p["title"], "year": p["year"], "type": p["type"], "doi": None}
    return None


def isolate(full: dict, citekey: str) -> dict:
    """Reduce a full graph.json dict to just `citekey`: its paper card, only the stubs/broad
    nodes its edges point at, and `order=[citekey]`. Outward `builds` (papers that build on
    this one) are dropped — that is other papers' context, not this paper's proposition."""
    focal = {**full["papers"][citekey], "builds": []}

    keys: set[str] = set()
    slugs: set[str] = set()
    for g in focal.get("grounds", []):
        keys.add(g["key"])
    for edges in (focal.get("lateral", []), focal.get("ans", [])):
        for e in edges:
            if e.get("slug"):
                slugs.add(e["slug"])
            elif e.get("key"):
                keys.add(e["key"])
    for c in focal.get("cons", []):
        slugs.add(c["slug"])
    keys.discard(citekey)                       # a within-paper lateral targets the focal itself

    stubs = {}
    for k in keys:
        entry = _stub_entry(full, k)
        if entry is not None:
            stubs[k] = entry
    broad = {s: full["broad"][s] for s in slugs if s in full["broad"]}
    return {"papers": {citekey: focal}, "broad": broad, "stubs": stubs, "order": [citekey]}


def emit_preview(g: Graph, citekey: str, out: Path) -> Path:
    """Write an isolated single-paper `preview.html` (self-contained) into `out`, returning
    its path. Reuses the real viewer template via build.render_html."""
    mini = isolate(to_json_dict(g), citekey)
    payload = json.dumps(mini, ensure_ascii=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    html = out / "preview.html"
    html.write_text(render_html(payload), encoding="utf-8")
    return html
