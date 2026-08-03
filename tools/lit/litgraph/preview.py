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
    aim_from_raw,
    compute_emergent,
    load_programme,
    load_repo,
    paper_from_raw,
    validate,
)

_yaml = YAML(typ="safe")


def build_preview_graph(root: Path, citekey: str, scratch: Path | None = None) -> Graph:
    """Load the repo, optionally overlay a scratch container under `citekey`, validate the
    whole (so the proposition's refs are checked against the real graph), and compute.
    Raises BuildError if `citekey` names no curated paper / aim, or on any SCHEMA §6
    violation.

    A key starting with "@" is an **aim** (programme design §5): it overlays into the
    programme tree instead, so the same propose-before-tokenizing loop works on proposed
    work as it does on a paper."""
    root = Path(root)
    papers, broad = load_repo(root)
    aims = load_programme(root)
    if citekey.startswith("@"):
        if scratch is not None:
            raw = _yaml.load(Path(scratch).read_text(encoding="utf-8")) or {}
            aims[citekey] = aim_from_raw(citekey, raw)
        if citekey not in aims:
            raise BuildError(f"no aim {citekey!r} to preview "
                             "(pass --scratch to overlay a proposition)")
    else:
        if scratch is not None:
            raw = _yaml.load(Path(scratch).read_text(encoding="utf-8")) or {}
            papers[citekey] = paper_from_raw(citekey, raw)   # overlay/replace the focal paper
        focal = papers.get(citekey)
        if focal is None or not focal.curated:
            raise BuildError(f"no curated paper {citekey!r} to preview "
                             "(pass --scratch to overlay a proposition)")
    validate(papers, broad, aims)
    return compute_emergent(papers, broad, aims)


def _stub_entry(full: dict, key: str) -> dict | None:
    """A minimal stub-shaped entry for an outward edge target, whether the target is a real
    stub or another curated paper (isolation collapses every neighbour to a labelled chip)."""
    if key in full["stubs"]:
        return full["stubs"][key]
    p = full["papers"].get(key)
    if p is not None:
        return {"title": p["title"], "year": p["year"], "type": p["type"], "doi": None}
    return None


def _cited_neighbour(full: dict, key: str, ids: set[str]) -> dict | None:
    """A curated neighbour trimmed to the slices this container actually cites.

    An aim's join to the literature *is* its content — "what does this rest on, and what did
    that paper actually report" — so a source may not collapse to a citekey chip the way it
    does for a paper proposition. But a whole neighbour card would drown the focal one, so the
    paper is kept with only its cited slices, and its own edges are cleared: it is here as
    evidence for the focal container, not to spawn a generation of its own."""
    p = full["papers"].get(key)
    if p is None:
        return None
    keep = [s for s in p["slices"] if s["id"] in ids]
    if not keep:
        return None
    return {**p, "slices": keep, "cited": [s["id"] for s in keep],
            "grounds": [], "lateral": [], "cons": [], "ans": [], "builds": []}


def isolate(full: dict, citekey: str) -> dict:
    """Reduce a full graph.json dict to just `citekey`: its paper card, only the stubs/broad
    nodes its edges point at, and `order=[citekey]`. Outward `builds` (papers that build on
    this one) are dropped — that is other papers' context, not this paper's proposition.

    For an **aim**, curated sources survive as trimmed neighbour cards rather than chips
    (`_cited_neighbour`): a programme is read against the literature it leans on, and a
    collapsed "5 sources" stack was the whole of what one said about 53 curated papers. A
    wildcard ref (no `tid`) still degrades to a chip — it names a container, not a finding."""
    focal = {**full["papers"][citekey], "builds": []}
    is_aim = bool(focal.get("aim"))

    keys: set[str] = set()
    slugs: set[str] = set()
    cited: dict[str, set[str]] = {}             # neighbour citekey -> the slice ids we point at
    for g in focal.get("grounds", []):
        keys.add(g["key"])
        if g.get("tid"):
            cited.setdefault(g["key"], set()).add(g["tid"])
    for edges in (focal.get("lateral", []), focal.get("ans", [])):
        for e in edges:
            if e.get("slug"):
                slugs.add(e["slug"])
            elif e.get("key"):
                keys.add(e["key"])
                if e.get("tid"):
                    cited.setdefault(e["key"], set()).add(e["tid"])
    for c in focal.get("cons", []):
        slugs.add(c["slug"])
    keys.discard(citekey)                       # a within-paper lateral targets the focal itself
    cited.pop(citekey, None)

    papers = {citekey: focal}
    if is_aim:
        for k, ids in cited.items():
            n = _cited_neighbour(full, k, ids)
            if n is not None:
                papers[k] = n
    stubs = {}
    for k in keys:
        if k in papers:
            continue                            # promoted to a real card — not also a chip
        entry = _stub_entry(full, k)
        if entry is not None:
            stubs[k] = entry
    broad = {s: full["broad"][s] for s in slugs if s in full["broad"]}
    # `order` stays the focal container alone: it drives the LANDING column, and a neighbour
    # belongs in the grounds column that the focal card spawns, not beside it.
    return {"papers": papers, "broad": broad, "stubs": stubs, "order": [citekey]}


def emit_preview(g: Graph, citekey: str, out: Path) -> Path:
    """Write an isolated single-paper `preview.html` (self-contained) into `out`, returning
    its path. Reuses the real viewer template via build.render_html."""
    mini = isolate(to_json_dict(g, include_aims=True), citekey)
    payload = json.dumps(mini, ensure_ascii=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    html = out / "preview.html"
    html.write_text(render_html(payload), encoding="utf-8")
    return html
