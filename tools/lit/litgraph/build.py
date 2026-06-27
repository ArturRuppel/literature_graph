# litgraph/build.py
"""Emit layer: serialize a Graph to inlined JSON and write the self-contained viewer."""

from __future__ import annotations

import json
from pathlib import Path

from litgraph.graph import Graph, Paper, classify_ref


def _grounds(p: Paper) -> list[dict]:
    """Left-column targets: each grounded_in ref that points at a container (a source paper)."""
    out = []
    for s in p.slices:
        for r in s.grounded_in:
            if classify_ref(r) in ("container", "sharpened"):
                out.append({"key": r.split(":", 1)[0], "via": s.id})
    return out


def _lateral(p: Paper) -> list[dict]:
    out = []
    for s in p.slices:
        for r in s.corroborates:
            out.append({"key": r.split(":", 1)[0], "sign": "corr", "via": s.id})
        for r in s.contradicts:
            out.append({"key": r.split(":", 1)[0], "sign": "contra", "via": s.id})
    return out


def _cons(p: Paper) -> list[dict]:
    """Right-band targets: each leads_to broad slug."""
    out = []
    for s in p.slices:
        for slug in s.leads_to:
            out.append({"slug": slug, "via": s.id})
    return out


def _paper_json(p: Paper) -> dict:
    return {
        "cur": p.curated, "pass": p.pass_, "type": p.type, "year": p.year,
        "title": p.title, "authors": [[n, pos, corr] for n, pos, corr in p.authors],
        "note": p.note, "head": p.head,
        "slices": [{"id": s.id, "kind": s.kind, "text": s.text, "color": s.color,
                    "is_floor": s.is_floor, "grounded": s.grounded,
                    "borrowed": s.borrowed, "answered": s.answered}
                   for s in p.slices],
        "grounds": _grounds(p), "lateral": _lateral(p), "cons": _cons(p),
    }


def to_json_dict(g: Graph) -> dict:
    curated = {ck: _paper_json(p) for ck, p in g.papers.items() if p.curated}
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

    template = _TEMPLATE.read_text(encoding="utf-8")
    start = template.index(_TOKEN_START)
    end = template.index(_TOKEN_END) + len(_TOKEN_END)
    html = template[:start] + payload + template[end:]
    (out / "index.html").write_text(html, encoding="utf-8")
