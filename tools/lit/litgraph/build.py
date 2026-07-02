# litgraph/build.py
"""Emit layer: serialize a Graph to inlined JSON and write the self-contained viewer."""

from __future__ import annotations

import json
from pathlib import Path

from litgraph.graph import Graph, Paper, Slice, classify_ref


def _up(s: Slice) -> list[str]:
    """Within-paper support refs: the local slices this one is built on (grounded_in).
    These draw the substructure skeleton inside an expanded card (e.g. m3 builds on m2)."""
    return [r for r in s.grounded_in if classify_ref(r) == "local"]


def _grounds(p: Paper) -> list[dict]:
    """Left-column targets: each grounded_in ref that points at a container (a source paper).
    A sharpened ref keeps its target slice id in `tid` so the viewer can anchor the edge on
    that specific slice; a plain container ref carries tid=None (the wildcard, CONCEPT §2)."""
    out = []
    for s in p.slices:
        for r in s.grounded_in:
            if classify_ref(r) in ("container", "sharpened"):
                key, _, tid = r.partition(":")
                out.append({"key": key, "tid": tid or None, "via": s.id})
    return out


def _lateral(p: Paper) -> list[dict]:
    """Lateral stance edges. Paper targets emit {key, tid, sign, via} (tid = the specific
    slice for sharpened refs, else None); broad-slug targets emit {slug, sign, via} so the
    viewer routes them to the synthesis band, not a phantom paper card."""
    out = []
    for s in p.slices:
        for sign, refs in (("corr", s.corroborates), ("contra", s.contradicts)):
            for r in refs:
                kind = classify_ref(r)
                if kind == "broad":
                    out.append({"slug": r, "sign": sign, "via": s.id})
                elif kind == "local":
                    out.append({"key": p.citekey, "tid": r, "sign": sign, "via": s.id})
                else:
                    key, _, tid = r.partition(":")
                    out.append({"key": key, "tid": tid or None, "sign": sign, "via": s.id})
    return out


def _cons(p: Paper) -> list[dict]:
    """Right-band targets: each leads_to *broad slug*. A local leads_to is a same-paper
    generalization ladder that nests in place, not a synthesis node — skip it here."""
    out = []
    for s in p.slices:
        for slug in s.leads_to:
            if classify_ref(slug) == "broad":
                out.append({"slug": slug, "via": s.id})
    return out


def _answers(p: Paper) -> list[dict]:
    """Cross-paper answers edges: a claim answering a question in another container.
    Local refs are omitted (they nest in place via the slice's own `answers` list).
    A sharpened ref keeps the target question id in `tid`; a plain container ref is the
    wildcard (tid=None); a broad-question slug routes to the synthesis band ({slug})."""
    out = []
    for s in p.slices:
        for r in s.answers:
            kind = classify_ref(r)
            if kind == "broad":
                out.append({"slug": r, "via": s.id})
            elif kind in ("container", "sharpened"):
                key, _, tid = r.partition(":")
                out.append({"key": key, "tid": tid or None, "via": s.id})
    return out


def _builds(g: Graph) -> dict[str, list[dict]]:
    """Invert cross-paper grounding: for each curated paper, the (newer) curated papers
    that build on it — the viewer's rightward "builds-on" column. Each entry names the
    building paper (`key`), its building slice (`via`), and — for a sharpened ref — the
    grounded slice of *this* paper (`tid`)."""
    idx: dict[str, list[dict]] = {}
    for q in g.papers.values():
        if not q.curated:
            continue
        for s in q.slices:
            for r in s.grounded_in:
                if classify_ref(r) not in ("container", "sharpened"):
                    continue
                key, _, tid = r.partition(":")
                target = g.papers.get(key)
                if target is not None and target.curated:
                    idx.setdefault(key, []).append(
                        {"key": q.citekey, "tid": tid or None, "via": s.id})
    return idx


def _paper_json(p: Paper, builds: list[dict]) -> dict:
    return {
        "cur": p.curated, "pass": p.pass_, "type": p.type, "year": p.year,
        "title": p.title, "authors": [[n, pos, corr] for n, pos, corr in p.authors],
        "note": p.note, "head": p.head,
        "slices": [{"id": s.id, "kind": s.kind, "text": s.text, "color": s.color,
                    "is_floor": s.is_floor, "grounded": s.grounded,
                    "borrowed": s.borrowed, "answered": s.answered, "up": _up(s),
                    "quote": s.quote, "answers": list(s.answers)}
                   for s in p.slices],
        "grounds": _grounds(p), "lateral": _lateral(p), "cons": _cons(p),
        "ans": _answers(p), "builds": builds,
    }


def to_json_dict(g: Graph) -> dict:
    builds = _builds(g)
    curated = {ck: _paper_json(p, builds.get(ck, [])) for ck, p in g.papers.items() if p.curated}
    stubs = {ck: {"title": p.title, "year": p.year, "type": p.type, "doi": p.doi}
             for ck, p in g.papers.items() if not p.curated}
    broad = {slug: {"kind": b.kind, "text": b.text,
                    "meter": ({"s": b.support, "c": b.contradict}
                              if b.kind == "broad claim" else None)}
             for slug, b in g.broad.items()}
    return {"papers": curated, "broad": broad, "stubs": stubs, "order": g.order}


_TEMPLATE = Path(__file__).parent / "viewer" / "template.html"
_TOKEN_START = "/*__GRAPH_JSON__*/"
_TOKEN_END = "/*__END__*/"


def emit(g: Graph, out: Path) -> None:
    """Write graph.json and a self-contained index.html (JSON inlined) into `out`."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = to_json_dict(g)
    payload = json.dumps(data, ensure_ascii=False)
    (out / "graph.json").write_text(payload, encoding="utf-8")

    # Inline into the <script>; escape "<" so a "</script>" inside any paper's text
    # can't close the tag. < is a valid JS string escape that parses back to "<".
    inline = payload.replace("<", "\\u003c")
    template = _TEMPLATE.read_text(encoding="utf-8")
    start = template.index(_TOKEN_START)
    end = template.index(_TOKEN_END) + len(_TOKEN_END)
    html = template[:start] + inline + template[end:]
    (out / "index.html").write_text(html, encoding="utf-8")
