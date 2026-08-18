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
    build_graph,
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
    work as it does on a paper. A key starting with "~" is a **narrative** — the whole
    proposal page (isolate_proposal); there is nothing to overlay, so --scratch is refused."""
    root = Path(root)
    papers, broad = load_repo(root)
    aims = load_programme(root)
    if citekey.startswith("~"):
        if scratch is not None:
            raise BuildError("--scratch overlays one container; a proposal is a whole "
                             "narrative — edit programme/narrative/<grant>.yaml and re-run")
        # the FULL build, not the papers/aims core above: a narrative is loaded and validated
        # last of all (graph.build_graph), against the resolved graph its refs point into.
        g = build_graph(root)
        if citekey.lstrip("~") not in g.narrative:
            raise BuildError(f"no narrative {citekey!r} to preview "
                             f"(programme/narrative/{citekey.lstrip('~')}.yaml)")
        return g
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
    """A curated neighbour, **whole** — the same card the main board draws, with `cited` naming
    the slices this page points at so the cited rows can be marked inside it.

    A programme container's join to the literature *is* its content — "what does this rest on,
    and what did that paper actually report" — so a source may not collapse to a citekey chip
    the way it does for a paper proposition. It used to be trimmed to the cited slices alone,
    because every one of these cards opened automatically and a full neighbour would drown the
    focal one. They land collapsed now (viewer/js/07-expand.js), so length costs nothing and
    trimming only made the card disagree with the same paper's card everywhere else. One
    rendering of one paper, wherever it stands.

    Outward edges stay cleared: this page is an isolation, and a neighbour is here as evidence
    for the focal container, not to spawn a generation of its own."""
    p = full["papers"].get(key)
    if p is None or not ids:
        return None
    return {**p, "cited": sorted(ids),
            "grounds": [], "lateral": [], "cons": [], "ans": [], "builds": []}


def isolate(full: dict, citekey: str) -> dict:
    """Reduce a full graph.json dict to just `citekey` — its card, only the stubs/broad nodes its
    edges point at, and `order=[citekey]`. Outward `builds` (papers that build on this one) are
    dropped: that is other papers' context, not this paper's proposition.

    For a **programme container** (an aim, or a narrative — see isolate_proposal) curated sources
    survive as full neighbour cards rather than chips (`_cited_neighbour`): a programme is read
    against the literature it leans on, and a collapsed "5 sources" stack was the whole of what one
    said about 53 curated papers. A wildcard ref (no `tid`) still degrades to a chip — it names a
    container, not a finding."""
    return _isolate(full, [citekey])


def _isolate(full: dict, keys: list[str]) -> dict:
    """`isolate` over a LIST of focal containers, which is the only thing a proposal needs that a
    single-paper preview did not: an introduction and the aims it leads into stand on one page,
    in one column, sharing one grounds column of cited papers (so a paper cited by both is one
    card marking the union of what they cite, not two cards)."""
    focals = {k: {**full["papers"][k], "builds": []} for k in keys}
    prog = any(f.get("aim") or f.get("narr") for f in focals.values())

    outward: set[str] = set()
    slugs: set[str] = set()
    cited: dict[str, set[str]] = {}             # neighbour citekey -> the slice ids we point at
    for citekey, focal in focals.items():
        for g in focal.get("grounds", []):
            outward.add(g["key"])
            if g.get("tid"):
                cited.setdefault(g["key"], set()).add(g["tid"])
        for edges in (focal.get("lateral", []), focal.get("ans", [])):
            for e in edges:
                if e.get("slug"):
                    slugs.add(e["slug"])
                elif e.get("key"):
                    outward.add(e["key"])
                    if e.get("tid"):
                        cited.setdefault(e["key"], set()).add(e["tid"])
        for c in focal.get("cons", []):
            slugs.add(c["slug"])
    for k in focals:                            # a within-container lateral targets a focal itself
        outward.discard(k)
        cited.pop(k, None)

    papers = dict(focals)
    if prog:
        for k, ids in cited.items():
            n = _cited_neighbour(full, k, ids)
            if n is not None:
                papers[k] = n
    stubs = {}
    for k in outward:
        if k in papers:
            continue                            # promoted to a real card — not also a chip
        entry = _stub_entry(full, k)
        if entry is not None:
            stubs[k] = entry
    broad = {s: full["broad"][s] for s in slugs if s in full["broad"]}
    # `order` is the focal containers alone, in the order given: it drives the LANDING column, and
    # a cited neighbour belongs in the grounds column the focal spawns, not beside it.
    return {"papers": papers, "broad": broad, "stubs": stubs, "order": list(keys)}


def _proposal_keys(full: dict, narr_key: str) -> list[str]:
    """The proposal's landing column, top to bottom: the narrative first, then its aims.

    The narrative IS the introduction — it is the linearization that says what the proposal
    argues — so it leads, and the aims it hands off to stand under it. Aims are ordered by where
    the narrative first cites them (its own running order is the only ordering that exists here),
    with any aim the narrative never mentions after them so nothing in `programme/aims/` can go
    missing from the page just because a draft has not reached it yet."""
    aims = {k for k, p in full["papers"].items() if p.get("aim")}
    seen: list[str] = []
    for g in full["papers"][narr_key].get("grounds", []):
        if g["key"] in aims and g["key"] not in seen:
            seen.append(g["key"])
    return [narr_key, *seen, *sorted(aims - set(seen))]


def narrative_key(grant: str) -> str:
    """`~<grant>` — the payload key for a narrative card, from a bare grant name or itself."""
    return grant if grant.startswith("~") else f"~{grant}"


def isolate_proposal(full: dict, grant: str) -> dict:
    """The **proposal page**: one narrative and its aims, isolated together.

    This is where the programme layer is read now. It used to render as a standing lane on the
    main board — every reader who opened the graph to browse the literature got a grant's
    argument in the leftmost column whether they asked for it or not, and the narrative's
    citations were inert chips because a static panel had nothing to draw an arrow *to*. Both
    problems dissolve here: the proposal is a page you click into, and on it the narrative is an
    ordinary container, so its bullets ground into real paper cards through the machinery every
    other card already uses.

    Raises KeyError if `grant` names no narrative."""
    key = narrative_key(grant)
    card = (full.get("narrative") or {}).get(key)
    if card is None:
        raise KeyError(key)
    merged = {**full, "papers": {**full["papers"], key: card}}
    out = _isolate(merged, _proposal_keys(merged, key))
    out["proposal"] = key                       # the viewer titles the column from this
    return out


def emit_preview(g: Graph, citekey: str, out: Path) -> Path:
    """Write an isolated single-paper `preview.html` (self-contained) into `out`, returning
    its path. Reuses the real viewer template via build.render_html."""
    full = to_json_dict(g, include_aims=True)
    mini = (isolate_proposal(full, citekey) if citekey.startswith("~")
            else isolate(full, citekey))
    payload = json.dumps(mini, ensure_ascii=False)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    html = out / "preview.html"
    html.write_text(render_html(payload), encoding="utf-8")
    return html
