"""Programme layer: ref grammar, loading, validation rules, emergent properties, report.

Offline and deterministic — the worked `example/programme/` tree plus inline fixtures.
"""

from pathlib import Path

import pytest

from litgraph.graph import (
    BuildError,
    build_graph,
    classify_ref,
    load_programme,
    paper_from_raw,
)
from litgraph.programme import format_report, report

EXAMPLE = Path(__file__).resolve().parents[3] / "example"
AIM = "@adaptive-batching"


def _aim_repo(tmp_path: Path, body: str, name: str = "a.yaml") -> Path:
    """A minimal repo holding one aim — enough for build_graph to run."""
    (tmp_path / "programme" / "aims").mkdir(parents=True)
    (tmp_path / "programme" / "aims" / name).write_text(body)
    return tmp_path


def _slice(g, aim: str, sid: str):
    return next(s for s in g.aims[aim].slices if s.id == sid)


# --- ref grammar (programme design §5) --------------------------------------


def test_sigil_distinguishes_aim_from_broad_slug():
    # both are kebab-case; only the sigil tells them apart
    assert classify_ref("adaptive-batching") == "broad"
    assert classify_ref("@adaptive-batching") == "container"
    assert classify_ref("@adaptive-batching:c1") == "sharpened"
    # the literature forms are untouched
    assert classify_ref("Chen2021Sys") == "container"
    assert classify_ref("Chen2021Sys:c3") == "sharpened"


def test_new_local_id_prefixes_classify_as_local():
    assert classify_ref("t1") == "local"
    assert classify_ref("k2") == "local"


# --- loading -----------------------------------------------------------------


def test_load_programme_reads_every_kind():
    aims = load_programme(EXAMPLE)
    assert set(aims) == {AIM}
    kinds = sorted({s.kind for s in aims[AIM].slices})
    assert kinds == ["capability", "claim", "method", "question", "test"]
    assert aims[AIM].title == "Adaptive batch-size control"


def test_load_programme_absent_is_empty():
    assert load_programme(EXAMPLE / "curated") == {}


def test_paper_may_not_hold_tests_or_capabilities():
    with pytest.raises(BuildError, match="belongs to an aim"):
        paper_from_raw("X2020Jrnl", {"title": "t", "tests": [{"id": "t1", "text": "x"}]})


# --- validation (programme design §9) ---------------------------------------


def test_discriminates_needs_two_alternatives(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
claims:
  - {id: c1, text: one}
tests:
  - {id: t1, text: solo, discriminates: [c1]}
""")
    with pytest.raises(BuildError, match="separates nothing"):
        build_graph(root)


def test_discriminates_only_on_a_test(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
claims:
  - {id: c1, text: one, discriminates: [c2]}
  - {id: c2, text: two}
""")
    with pytest.raises(BuildError, match="authored on a test"):
        build_graph(root)


def test_enabled_by_must_target_a_capability(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
claims:
  - {id: c1, text: one}
tests:
  - {id: t1, text: x, enabled_by: [c1]}
""")
    with pytest.raises(BuildError, match="not a capability"):
        build_graph(root)


def test_no_broad_tier_for_tests(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
tests:
  - {id: t1, text: x, leads_to: [some-broad-test]}
""")
    with pytest.raises(BuildError, match="not valid on a test"):
        build_graph(root)


def test_dangling_programme_ref_fails_the_build(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
claims:
  - {id: c1, text: one, grounded_in: ["@nope:c1"]}
""")
    with pytest.raises(BuildError, match="dangling"):
        build_graph(root)


def test_cross_aim_ref_resolves(tmp_path):
    (tmp_path / "programme" / "aims").mkdir(parents=True)
    (tmp_path / "programme" / "aims" / "one.yaml").write_text(
        "title: One\nclaims:\n  - {id: c1, text: base}\n")
    (tmp_path / "programme" / "aims" / "two.yaml").write_text(
        'title: Two\nclaims:\n  - {id: c1, text: derived, grounded_in: ["@one:c1"]}\n')
    g = build_graph(tmp_path)
    assert set(g.aims) == {"@one", "@two"}


# --- emergent properties (programme design §8) ------------------------------


def test_modality_reads_off_the_grounding():
    g = build_graph(EXAMPLE)
    assert _slice(g, AIM, "c1").modality == "established"   # cites Chen2021Sys
    assert _slice(g, AIM, "c2").modality == "proposed"      # t1 discriminates it
    assert _slice(g, AIM, "c3").modality == "proposed"      # the rival, same test
    assert _slice(g, AIM, "c4").modality == "speculation"   # nothing at all
    assert _slice(g, AIM, "c6").modality == "proposed"      # downstream of c2, so t1 settles it


def test_one_planned_test_anywhere_underneath_wins(tmp_path):
    """A claim co-grounded in a citation and in a hypothesis is *proposed*: a conjunction is
    only as established as its weakest link. Without this the payoff claim of an aim — which
    always cites something — would read as already known."""
    root = _aim_repo(tmp_path, """
title: A
claims:
  - {id: c1, text: cited fact, grounded_in: ["Chen2021Sys:c1"]}
  - {id: c2, text: the hypothesis}
  - {id: c3, text: the payoff, grounded_in: [c1, c2]}
  - {id: c4, text: the rival}
tests:
  - {id: t1, text: settles it, discriminates: [c2, c4]}
""")
    (root / "curated").mkdir()
    (root / "curated" / "Chen2021Sys.yaml").write_text(
        "title: T\ntype: original\nyear: 2021\nclaims:\n  - {id: c1, text: known}\n")
    g = build_graph(root)
    assert _slice(g, "@a", "c1").modality == "established"
    assert _slice(g, "@a", "c3").modality == "proposed"
    # and the assumption detector stays quiet on it — its support *is* checked, by t1
    assert _slice(g, "@a", "c3").load_bearing is False


def test_the_programme_cannot_ground_itself(tmp_path):
    """A ref into another aim is not evidence — only the literature or a floor is."""
    (tmp_path / "programme" / "aims").mkdir(parents=True)
    (tmp_path / "programme" / "aims" / "one.yaml").write_text(
        "title: One\nclaims:\n  - {id: c1, text: itself ungrounded}\n")
    (tmp_path / "programme" / "aims" / "two.yaml").write_text(
        'title: Two\nclaims:\n  - {id: c1, text: leans on the other aim, grounded_in: ["@one:c1"]}\n')
    g = build_graph(tmp_path)
    assert _slice(g, "@two", "c1").modality == "speculation"


def test_a_test_is_a_hollow_floor(tmp_path):
    """A claim resting on a planned experiment is *proposed*, however well-cited the
    experiment's methods are. Inheriting the test's citations would let the central
    hypothesis of a grant read as already established."""
    root = _aim_repo(tmp_path, """
title: A
methods:
  - {id: m1, text: a technique, grounded_in: [Chen2021Sys]}
claims:
  - {id: c1, text: rests only on a planned test, grounded_in: [t1]}
tests:
  - {id: t1, text: the planned experiment, grounded_in: [m1]}
""")
    # the literature the method cites has to exist, so build against the example repo's
    (root / "curated").mkdir()
    (root / "curated" / "Chen2021Sys.yaml").write_text(
        "title: T\ntype: original\nyear: 2021\nmethods:\n  - {id: m1, text: harness}\n")
    c1 = _slice(build_graph(root), "@a", "c1")
    assert c1.modality == "proposed" and c1.grounded is False


def test_load_bearing_assumption_and_blast_radius():
    g = build_graph(EXAMPLE)
    c4 = _slice(g, AIM, "c4")
    assert c4.load_bearing is True
    assert c4.blast_radius == 2          # c2, and c6 transitively through it
    # the hypothesis itself is not an assumption: a test is aimed at it
    assert _slice(g, AIM, "c2").load_bearing is False
    # nor is an established claim
    assert _slice(g, AIM, "c1").load_bearing is False


def test_capability_and_test_feasibility():
    g = build_graph(EXAMPLE)
    assert _slice(g, AIM, "k1").aspirational is False     # grounded in a published method
    assert _slice(g, AIM, "k2").aspirational is True      # no grounding
    assert _slice(g, AIM, "t1").at_risk is True           # because of k2


def test_a_discriminated_rival_is_not_an_orphan():
    """c3 has no dependents by design; the test aimed at it is what makes it live."""
    g = build_graph(EXAMPLE)
    assert _slice(g, AIM, "c3").orphan is False
    assert _slice(g, AIM, "c6").orphan is True


def test_a_test_that_separates_nothing_is_an_orphan(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
tests:
  - {id: t1, text: aimless}
""")
    g = build_graph(root)
    assert _slice(g, "@a", "t1").orphan is True


def test_question_answered_within_an_aim():
    g = build_graph(EXAMPLE)
    assert _slice(g, AIM, "q2").answered is True     # c1 answers it
    assert _slice(g, AIM, "q1").answered is False


# --- the report --------------------------------------------------------------


def test_report_collects_and_ranks():
    g = build_graph(EXAMPLE)
    r = report(g)
    assert r.aims == 1
    assert [f.node for f in r.assumptions] == [f"{AIM}:c4"]
    assert "2 dependents" in r.assumptions[0].detail
    assert [f.node for f in r.at_risk] == [f"{AIM}:t1"]
    assert r.at_risk[0].detail == "needs k2"          # names only the blocking capability
    assert [f.node for f in r.aspirational] == [f"{AIM}:k2"]
    assert [f.node for f in r.open_questions] == [f"{AIM}:q1"]
    assert not r.clean


def test_report_ranks_assumptions_by_blast_radius(tmp_path):
    root = _aim_repo(tmp_path, """
title: A
claims:
  - {id: c1, text: small}
  - {id: c2, text: big}
  - {id: c3, text: rests on c1, grounded_in: [c1]}
  - {id: c4, text: rests on c2, grounded_in: [c2]}
  - {id: c5, text: rests on c4, grounded_in: [c4]}
""")
    r = report(build_graph(root))
    assert [f.node for f in r.assumptions][:2] == ["@a:c2", "@a:c1"]


def test_clean_programme_reports_nothing():
    r = report(build_graph(EXAMPLE / "curated"))    # no programme tree at all
    assert r.aims == 0 and r.clean
    assert "nothing flagged" in format_report(r)


def test_format_report_is_plain_text():
    out = format_report(report(build_graph(EXAMPLE)))
    assert "load-bearing assumptions (1)" in out
    assert f"{AIM}:c4" in out


# --- the card (lit preview) --------------------------------------------------


def test_preview_renders_an_aim_card():
    from litgraph.build import to_json_dict
    from litgraph.preview import build_preview_graph, isolate

    g = build_preview_graph(EXAMPLE, AIM)
    card = isolate(to_json_dict(g, include_aims=True), AIM)["papers"][AIM]
    assert card["aim"] is True and card["type"] == "aim"
    by = {s["id"]: s for s in card["slices"]}
    assert by["c4"]["lb"] is True and by["c4"]["br"] == 2
    assert by["t1"]["disc"] == ["c2", "c3"] and by["t1"]["en"] == ["k1", "k2"]
    assert by["k2"]["asp"] is True
    assert by["t1"]["color"] == "test-at-risk"


def test_preview_aim_keeps_its_literature_cross_links():
    """A capability grounded in a published method must still draw at the paper."""
    from litgraph.build import to_json_dict
    from litgraph.preview import build_preview_graph, isolate

    g = build_preview_graph(EXAMPLE, AIM)
    mini = isolate(to_json_dict(g, include_aims=True), AIM)
    assert {"key": "Chen2021Sys", "tid": "m1", "via": "k1"} in mini["papers"][AIM]["grounds"]


def test_preview_aim_keeps_a_curated_source_as_a_whole_card():
    """An aim's sources are its argument, not a citation wall: a curated source stays a real
    card — never a bare citekey chip. It is the WHOLE card the main board draws, with `cited`
    marking the slices this aim points at; it used to be trimmed to those slices alone, back
    when every one of these cards opened automatically (viewer/js/07-expand.js)."""
    from litgraph.build import to_json_dict
    from litgraph.preview import build_preview_graph, isolate

    g = build_preview_graph(EXAMPLE, AIM)
    full = to_json_dict(g, include_aims=True)
    mini = isolate(full, AIM)

    assert "Chen2021Sys" not in mini["stubs"]          # promoted out of the citation wall
    src = mini["papers"]["Chen2021Sys"]
    assert src["title"] and src["cur"] is True         # a real card, bibliography intact
    # the same paper as everywhere else, minus nothing — one rendering of one paper
    assert src["slices"] == full["papers"]["Chen2021Sys"]["slices"]
    assert "m1" in src["cited"]                        # …and what this aim takes from it, marked
    assert set(src["cited"]) < {s["id"] for s in src["slices"]}
    # a neighbour is evidence for the focal card, not a generation of its own
    assert src["grounds"] == [] and src["lateral"] == [] and src["cons"] == []
    assert mini["order"] == [AIM]                      # …and it stays out of the landing column


def test_preview_paper_still_collapses_its_neighbours_to_chips():
    """The trimmed-neighbour rule is the AIM's; a paper proposition keeps its isolation."""
    from litgraph.build import to_json_dict
    from litgraph.preview import build_preview_graph, isolate

    g = build_preview_graph(EXAMPLE, "Kumar2020Net")
    mini = isolate(to_json_dict(g, include_aims=True), "Kumar2020Net")
    assert list(mini["papers"]) == ["Kumar2020Net"]
    assert "Chen2021Sys" in mini["stubs"]


def test_preview_rejects_an_unknown_aim():
    from litgraph.preview import build_preview_graph
    with pytest.raises(BuildError, match="no aim"):
        build_preview_graph(EXAMPLE, "@nope")


def test_preview_scratch_overlays_an_aim(tmp_path):
    """The propose-before-tokenizing loop, on proposed work."""
    from litgraph.preview import build_preview_graph
    scratch = tmp_path / "draft.yaml"
    scratch.write_text("title: Draft\nclaims:\n  - {id: c1, text: untested}\n")
    g = build_preview_graph(EXAMPLE, "@draft", scratch)
    assert g.aims["@draft"].title == "Draft"
    assert g.aims["@draft"].slices[0].modality == "speculation"


def test_aims_are_off_by_default_in_the_emit_layer():
    from litgraph.build import to_json_dict
    full = to_json_dict(build_graph(EXAMPLE))
    assert AIM not in full["papers"]
    assert AIM not in full["order"]


def test_literature_card_json_carries_no_programme_keys():
    """A paper's serialized slices are unchanged by the programme layer."""
    from litgraph.build import to_json_dict
    full = to_json_dict(build_graph(EXAMPLE))
    for s in full["papers"]["Chen2021Sys"]["slices"]:
        assert not {"mod", "lb", "br", "disc", "en", "risk", "asp"} & set(s)
    assert "aim" not in full["papers"]["Chen2021Sys"]


# --- the literature side is untouched ---------------------------------------


def test_literature_graph_ignores_the_programme_tree():
    g = build_graph(EXAMPLE)
    assert "Chen2021Sys" in g.papers
    assert AIM not in g.papers          # aims never leak into the paper-centric emit layer
    assert g.order == [k for k in g.order if not k.startswith("@")]
