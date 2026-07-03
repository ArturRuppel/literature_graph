# tests/test_preview.py
"""Isolated single-paper preview (litgraph.preview): reduction to one paper, the scratch
overlay, and the self-contained emit. Offline — reads the example/ fixture repo, no network."""

from pathlib import Path

import pytest

from litgraph.build import to_json_dict
from litgraph.graph import BuildError
from litgraph.preview import build_preview_graph, emit_preview, isolate

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def _mini(citekey: str):
    g = build_preview_graph(EXAMPLE, citekey, None)
    return isolate(to_json_dict(g), citekey)


# --- isolation ---------------------------------------------------------------

def test_isolate_reduces_to_one_paper():
    m = _mini("Chen2021Sys")
    assert m["order"] == ["Chen2021Sys"]
    assert list(m["papers"]) == ["Chen2021Sys"]
    # every outward edge endpoint is present as a stub chip or a broad node — nothing dangles
    f = m["papers"]["Chen2021Sys"]
    keys = {g["key"] for g in f["grounds"]}
    keys |= {e["key"] for e in f["lateral"] + f["ans"] if e.get("key")}
    keys.discard("Chen2021Sys")                       # a within-paper lateral targets the focal
    assert keys and all(k in m["stubs"] for k in keys)
    slugs = {c["slug"] for c in f["cons"]}
    slugs |= {e["slug"] for e in f["lateral"] + f["ans"] if e.get("slug")}
    assert all(s in m["broad"] for s in slugs)


def test_isolate_carries_only_referenced_neighbours():
    m = _mini("Chen2021Sys")
    f = m["papers"]["Chen2021Sys"]
    referenced = {g["key"] for g in f["grounds"]}
    referenced |= {e["key"] for e in f["lateral"] + f["ans"] if e.get("key")}
    referenced.discard("Chen2021Sys")
    # the isolated payload holds exactly the neighbours its edges point at — no more
    assert set(m["stubs"]) == referenced


def test_isolate_drops_builds_on():
    # Lopez has a builds-on edge in the full graph (Chen grounds in it); isolation drops it
    full = to_json_dict(build_preview_graph(EXAMPLE, "Lopez2019Arch", None))
    assert full["papers"]["Lopez2019Arch"]["builds"]          # non-empty in the full graph
    m = isolate(full, "Lopez2019Arch")
    assert m["papers"]["Lopez2019Arch"]["builds"] == []       # ...empty in isolation


# --- scratch overlay ---------------------------------------------------------

_SCRATCH = """\
title: "Scratch proposition"
type: original
year: 2026
pass: 2
methods:
  - id: m1
    text: "a floor method"
    quote: "we ran the harness"
    grounded_in: [Bench2016Tools]
claims:
  - id: c1
    text: "a proposed grounded claim"
    quote: "throughput rose with batch size"
    grounded_in: [m1]
    corroborates: [throughput-scales-with-batching]
"""


def test_scratch_overlay_replaces_focal(tmp_path: Path):
    sf = tmp_path / "Chen2021Sys.yaml"
    sf.write_text(_SCRATCH, encoding="utf-8")
    g = build_preview_graph(EXAMPLE, "Chen2021Sys", sf)
    m = isolate(to_json_dict(g), "Chen2021Sys")
    f = m["papers"]["Chen2021Sys"]
    # the focal paper is the scratch content, not the repo's real Chen2021Sys
    assert f["title"] == "Scratch proposition"
    assert {s["text"] for s in f["slices"]} == {"a floor method", "a proposed grounded claim"}
    # its edges resolve against the real repo: the container stub + the broad claim ride along
    assert "Bench2016Tools" in m["stubs"]
    assert "throughput-scales-with-batching" in m["broad"]
    # emergent props still compute: c1 reaches the floor m1 -> grounded
    assert next(s for s in f["slices"] if s["id"] == "c1")["color"] == "grounded"


def test_scratch_can_introduce_a_new_paper(tmp_path: Path):
    sf = tmp_path / "New2026Jour.yaml"
    sf.write_text(_SCRATCH, encoding="utf-8")
    g = build_preview_graph(EXAMPLE, "New2026Jour", sf)      # citekey absent from the repo
    m = isolate(to_json_dict(g), "New2026Jour")
    assert m["order"] == ["New2026Jour"]
    assert m["papers"]["New2026Jour"]["title"] == "Scratch proposition"


def test_scratch_dangling_ref_raises(tmp_path: Path):
    sf = tmp_path / "Bad2026Jour.yaml"
    sf.write_text(
        'title: "x"\ntype: original\nyear: 2026\n'
        'claims:\n  - id: c1\n    text: "t"\n    corroborates: [no-such-broad-node]\n',
        encoding="utf-8")
    with pytest.raises(BuildError):
        build_preview_graph(EXAMPLE, "Bad2026Jour", sf)


def test_missing_citekey_raises():
    with pytest.raises(BuildError):
        build_preview_graph(EXAMPLE, "Ghost2020Jour", None)


# --- emit --------------------------------------------------------------------

def test_emit_preview_is_self_contained(tmp_path: Path):
    g = build_preview_graph(EXAMPLE, "Chen2021Sys", None)
    html = emit_preview(g, "Chen2021Sys", tmp_path)
    assert html == tmp_path / "preview.html"
    text = html.read_text(encoding="utf-8")
    assert "Chen2021Sys" in text
    # self-contained: no external script/style/img sources
    assert "src=\"http" not in text and "href=\"http" not in text
    # only the focal paper is inlined — a sibling curated paper is not a column here
    assert "Kumar2020Net" not in text
