# tests/test_preview.py
"""Isolated single-paper preview (litgraph.preview): reduction to one paper, the scratch
overlay, and the self-contained emit. Offline — reads the example/ fixture repo, no network."""

from pathlib import Path

import pytest

from litgraph.build import to_json_dict
from litgraph.graph import BuildError
from litgraph.preview import (
    build_preview_graph,
    emit_preview,
    isolate,
    isolate_proposal,
)

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def _mini(citekey: str):
    g = build_preview_graph(EXAMPLE, citekey, None)
    return isolate(to_json_dict(g), citekey)


# --- isolation ---------------------------------------------------------------

def _outward(mini: dict, citekey: str) -> set[str]:
    """The citekeys the focal card points at, which the payload must account for one way or
    the other: a curated one as a neighbour card, an uncurated one as a stub chip."""
    f = mini["papers"][citekey]
    keys = {g["key"] for g in f["grounds"]}
    keys |= {e["key"] for e in f["lateral"] + f["ans"] if e.get("key")}
    keys.discard(citekey)                             # a within-paper lateral targets the focal
    return keys


def test_isolate_reduces_to_one_landing_paper():
    m = _mini("Chen2021Sys")
    assert m["order"] == ["Chen2021Sys"]              # the landing column is the focal alone
    # every outward edge endpoint is present, as a neighbour card or a stub chip — nothing dangles
    keys = _outward(m, "Chen2021Sys")
    assert keys and all(k in m["stubs"] or k in m["papers"] for k in keys)
    f = m["papers"]["Chen2021Sys"]
    slugs = {c["slug"] for c in f["cons"]}
    slugs |= {e["slug"] for e in f["lateral"] + f["ans"] if e.get("slug")}
    assert all(s in m["broad"] for s in slugs)


def test_isolate_carries_only_referenced_neighbours():
    m = _mini("Chen2021Sys")
    referenced = _outward(m, "Chen2021Sys")
    # the isolated payload holds exactly the neighbours its edges point at — no more
    assert set(m["stubs"]) | (set(m["papers"]) - {"Chen2021Sys"}) == referenced
    assert not (set(m["stubs"]) & set(m["papers"]))   # a neighbour is a card or a chip, never both


def test_a_curated_neighbour_cited_by_citekey_alone_is_still_a_card():
    """The promotion gate is curation, not sharpening. A pass-2 container cites by citekey with
    no `tid`, and its sources are no less curated for it — the card stands with no row marked."""
    full = to_json_dict(build_preview_graph(EXAMPLE, "Chen2021Sys", None))
    for g in full["papers"]["Chen2021Sys"]["grounds"]:
        if g["key"] == "Lopez2019Arch":
            g["tid"] = None                           # blunt the one sharpened ground
    m = isolate(full, "Chen2021Sys")
    assert "Lopez2019Arch" not in m["stubs"]
    n = m["papers"]["Lopez2019Arch"]
    assert n["cur"] is True and n["slices"]           # the whole card, as everywhere else
    assert n["cited"] == []                           # …with nothing marked inside it


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


# --- the proposal page -------------------------------------------------------
# A narrative and the aims under it, isolated together. This is where the programme layer is
# read now: it used to stand as a lane on the main board, with the narrative's citations as
# inert chips because a static panel had nothing to draw an arrow to.


def _proposal(grant: str = "~synth-grant"):
    g = build_preview_graph(EXAMPLE, grant, None)
    return isolate_proposal(to_json_dict(g, include_aims=True), grant)


def test_the_proposal_is_the_narrative_with_its_aims_under_it():
    m = _proposal()
    assert m["order"] == ["~synth-grant", "@adaptive-batching"]     # introduction first
    assert m["proposal"] == "~synth-grant"
    assert m["papers"]["~synth-grant"]["narr"] is True
    assert m["papers"]["@adaptive-batching"]["aim"] is True


def test_a_bullets_curated_sources_land_as_cards_not_chips():
    """The whole point of the change: a cited slice is a card with an edge to it. A wildcard
    ref still degrades to a chip — it names a container, not a finding."""
    m = _proposal()
    # the whole card, with what this page cites marked: the narrative's c1 + the aim's own m1
    assert set(m["papers"]["Chen2021Sys"]["cited"]) == {"c1", "m1"}
    assert m["papers"]["Chen2021Sys"]["title"]
    assert "Chen2021Sys" not in m["stubs"]
    assert m["broad"]["throughput-scales-with-batching"]            # the broad ref rides too


def test_a_paper_cited_by_both_the_narrative_and_an_aim_is_one_card():
    """One grounds column serves the whole page, so a source both cite is a single card marking
    the union of what they cite — not two cards disagreeing about the same paper."""
    full = to_json_dict(build_preview_graph(EXAMPLE, "~synth-grant", None), include_aims=True)
    aim_cited = {g["tid"] for g in full["papers"]["@adaptive-batching"]["grounds"]
                 if g["key"] == "Chen2021Sys" and g["tid"]}
    m = isolate_proposal(full, "~synth-grant")
    assert aim_cited <= set(m["papers"]["Chen2021Sys"]["cited"])


def test_naming_the_grant_without_the_sigil_works():
    """`~` is the payload key's sigil, not something a caller should have to spell."""
    full = to_json_dict(build_preview_graph(EXAMPLE, "~synth-grant", None), include_aims=True)
    assert isolate_proposal(full, "synth-grant") == isolate_proposal(full, "~synth-grant")


def test_unknown_grant_raises():
    with pytest.raises(BuildError, match="no narrative"):
        build_preview_graph(EXAMPLE, "~nope", None)
    full = to_json_dict(build_preview_graph(EXAMPLE, "~synth-grant", None), include_aims=True)
    with pytest.raises(KeyError):
        isolate_proposal(full, "~nope")


def test_a_proposal_cannot_be_scratched(tmp_path: Path):
    """--scratch overlays one container; a proposal is a whole narrative file."""
    f = tmp_path / "x.yaml"; f.write_text("title: x\n", encoding="utf-8")
    with pytest.raises(BuildError, match="--scratch"):
        build_preview_graph(EXAMPLE, "~synth-grant", f)


def test_emit_preview_writes_the_proposal_page(tmp_path: Path):
    g = build_preview_graph(EXAMPLE, "~synth-grant", None)
    html = emit_preview(g, "~synth-grant", tmp_path).read_text(encoding="utf-8")
    assert '"~synth-grant"' in html and '"@adaptive-batching"' in html
    assert "renderNarrative" in html                    # the card's own renderer is inlined
