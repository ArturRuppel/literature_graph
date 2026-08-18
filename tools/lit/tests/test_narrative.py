"""The narrative layer (programme design §7, extended): loading, ref validation, and its
non-interference with the graph — deleting it must not move a single computed property.

Offline and deterministic — the worked `example/programme/narrative/` tree plus inline
fixtures, exactly like test_programme.py / test_topics.py.
"""

import json
from pathlib import Path

import pytest

from litgraph.build import to_json_dict
from litgraph.graph import BuildError, build_graph
from litgraph.narrative import load_narratives

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def _repo(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / "programme" / "narrative").mkdir(parents=True, exist_ok=True)
    (tmp_path / "programme" / "narrative" / f"{name}.yaml").write_text(body)
    return tmp_path


def _aim_repo(tmp_path: Path, body: str = "title: A\nclaims:\n  - {id: c1, text: one}\n") -> Path:
    (tmp_path / "programme" / "aims").mkdir(parents=True, exist_ok=True)
    (tmp_path / "programme" / "aims" / "a.yaml").write_text(body)
    return tmp_path


# --- loading ------------------------------------------------------------------


def test_absent_narrative_tree_is_empty_not_an_error(tmp_path):
    assert load_narratives(tmp_path) == {}


def test_load_reads_sections_bullets_and_page_budget(tmp_path):
    root = _repo(tmp_path, "g", """
title: "Placeholder grant"
page_budget: 6
sections:
  - title: "Aim 1"
    bullets:
      - {text: "one sentence", refs: [c1]}
      - {text: "no refs yet"}
""")
    n = load_narratives(root)["g"]
    assert n.title == "Placeholder grant" and n.page_budget == 6
    assert len(n.sections) == 1 and n.sections[0].title == "Aim 1"
    assert n.sections[0].bullets[0].text == "one sentence"
    assert n.sections[0].bullets[0].refs == ["c1"]
    assert n.sections[0].bullets[1].refs == []          # absent `refs` -> empty, not an error


def test_load_programme_narrative_from_example():
    n = load_narratives(EXAMPLE)["synth-grant"]
    assert n.title == "Adaptive batching — placeholder application"
    assert n.page_budget == 6
    assert len(n.sections) == 2
    all_refs = [r for sec in n.sections for b in sec.bullets for r in b.refs]
    assert "@adaptive-batching:t1" in all_refs
    assert "Chen2021Sys:c1" in all_refs


# --- ref resolution (programme design §5, extended) ----------------------------


def test_dangling_ref_raises_with_a_clear_message(tmp_path):
    root = _aim_repo(tmp_path)
    _repo(root, "g", """
sections:
  - title: "S"
    bullets:
      - {text: "nope", refs: ["@a:nope"]}
""")
    with pytest.raises(BuildError, match="dangling ref"):
        build_graph(root)


def test_dangling_message_names_the_file_and_bullet(tmp_path):
    root = _aim_repo(tmp_path)
    _repo(root, "g", """
sections:
  - title: "Feasibility"
    bullets:
      - {text: "the missing thing", refs: ["@a:nope"]}
""")
    with pytest.raises(BuildError) as e:
        build_graph(root)
    msg = str(e.value)
    assert "programme/narrative/g.yaml" in msg
    assert "Feasibility" in msg and "the missing thing" in msg and "'@a:nope'" in msg


def test_bare_local_ref_is_ambiguous_not_dangling(tmp_path):
    """A narrative file is not itself a container — SCHEMA's `local` form (`c1`) has no 'this
    file' to resolve against, so it gets its own message rather than reading as a typo."""
    root = _aim_repo(tmp_path)
    _repo(root, "g", """
sections:
  - title: "S"
    bullets:
      - {text: "x", refs: [c1]}
""")
    with pytest.raises(BuildError, match="ambiguous ref"):
        build_graph(root)


def test_sharpened_ref_must_name_a_real_slice_not_just_an_existing_container(tmp_path):
    """Stricter than a curated slice's own edges: an aim/paper container existing is not
    enough — narrative.py's _resolves docstring is explicit that this axis cites finished
    arguments, not the frontier wildcard a curated `grounded_in` may still be resting on."""
    root = _aim_repo(tmp_path, "title: A\nclaims:\n  - {id: c1, text: one}\n")
    _repo(root, "g", """
sections:
  - title: "S"
    bullets:
      - {text: "x", refs: ["@a:c9"]}
""")
    with pytest.raises(BuildError, match="dangling ref"):
        build_graph(root)


def test_container_ref_resolves(tmp_path):
    root = _aim_repo(tmp_path)
    _repo(root, "g", """
sections:
  - title: "S"
    bullets:
      - {text: "cites the aim as a whole", refs: ["@a"]}
""")
    g = build_graph(root)                    # must not raise
    assert "g" in g.narrative


def test_broad_slug_ref_resolves(tmp_path):
    root = _aim_repo(tmp_path)
    (root / "claims").mkdir()
    (root / "claims" / "the-broad-thing.yaml").write_text('text: "broad"\n')
    _repo(root, "g", """
sections:
  - title: "S"
    bullets:
      - {text: "x", refs: [the-broad-thing]}
""")
    build_graph(root)                        # must not raise


def test_stub_container_ref_resolves_but_sharpened_into_a_stub_dangles(tmp_path):
    """A stub is un-sliced by definition — citing it as a container (the wildcard) is fine;
    sharpening into it names a slice that cannot exist yet."""
    root = _aim_repo(tmp_path)
    (root / "stubs.yaml").write_text(
        "West2015Sigmod:\n  title: t\n  year: 2015\n")
    _repo(root, "ok", """
sections:
  - title: "S"
    bullets:
      - {text: "x", refs: [West2015Sigmod]}
""")
    build_graph(root)
    _repo(root, "bad", """
sections:
  - title: "S"
    bullets:
      - {text: "x", refs: ["West2015Sigmod:c1"]}
""")
    with pytest.raises(BuildError, match="dangling ref"):
        build_graph(root)


# --- non-interference: deleting the narrative changes nothing above it ---------


def test_worked_example_narrative_is_valid():
    g = build_graph(EXAMPLE)
    assert set(g.narrative) == {"synth-grant"}


def test_deleting_narrative_leaves_the_graph_byte_identical(tmp_path):
    """The design's own invariant (§7): narrative carries no edges and derives nothing, so
    the graph with it and without it must compute identically everywhere except the
    narrative axis itself."""
    import shutil
    with_n = tmp_path / "with"
    shutil.copytree(EXAMPLE, with_n)
    without_n = tmp_path / "without"
    shutil.copytree(EXAMPLE, without_n)
    shutil.rmtree(without_n / "programme" / "narrative")

    g_with = build_graph(with_n)
    g_without = build_graph(without_n)
    assert g_with.narrative and not g_without.narrative     # sanity: the fixture actually differs

    d_with = to_json_dict(g_with, include_aims=True)
    d_without = to_json_dict(g_without, include_aims=True)
    del d_with["narrative"]                                  # the one key allowed to differ
    assert json.dumps(d_with, sort_keys=True) == json.dumps(d_without, sort_keys=True)

    # and lit programme's report reads nothing from it at all
    from litgraph.programme import report
    assert report(g_with) == report(g_without)


# --- the emit layer: a narrative is a CARD, and its refs are edges --------------


def test_narrative_absent_from_json_by_default():
    d = to_json_dict(build_graph(EXAMPLE))
    assert "narrative" not in d


def test_narrative_rides_with_include_aims():
    d = to_json_dict(build_graph(EXAMPLE), include_aims=True)
    assert "~synth-grant" in d["narrative"]          # `~` sigil, as an aim carries `@`
    n = d["narrative"]["~synth-grant"]
    assert n["narr"] is True and n["cur"] is True and n["type"] == "narrative"
    assert n["budget"] == 6
    assert [s["title"] for s in n["sections"]][0] == "Aim 1 — placeholder headline"


def test_a_bullet_is_a_slice_and_its_section_orders_it():
    """The narrative's only structure is which section a sentence stands in — bullets have no
    edges to each other — so `sections` carries slice ids and the slices carry the prose."""
    n = to_json_dict(build_graph(EXAMPLE), include_aims=True)["narrative"]["~synth-grant"]
    ids = [s["id"] for s in n["slices"]]
    assert ids == ["s1b1", "s1b2", "s1b3", "s2b1", "s2b2"]
    assert n["sections"][0]["bullets"] == ["s1b1", "s1b2", "s1b3"]
    assert n["slices"][0]["text"] == "Placeholder sentence stating the central hypothesis."
    assert n["slices"][0]["kind"] == "bullet"


def test_bullet_refs_become_the_ordinary_edges():
    """The change this axis' rendering turns on: a ref is a drawn edge, not an inert chip.
    Container and sharpened refs are `grounds` (the card to the left), broad slugs are `cons`
    (the synthesis band) — the exact split every paper and aim already emits."""
    n = to_json_dict(build_graph(EXAMPLE), include_aims=True)["narrative"]["~synth-grant"]
    assert {"key": "@adaptive-batching", "tid": "c2", "via": "s1b1"} in n["grounds"]
    assert {"key": "Chen2021Sys", "tid": "c1", "via": "s1b2"} in n["grounds"]
    assert n["cons"] == [{"slug": "throughput-scales-with-batching", "via": "s1b2"}]
    # a bullet with nothing behind it emits no edge and says so on its own row
    assert [s["nref"] for s in n["slices"]] == [1, 2, 1, 1, 0]
    assert not [g for g in n["grounds"] if g["via"] == "s2b2"]


def test_narrative_key_omitted_when_repo_has_none(tmp_path):
    (tmp_path / "curated").mkdir()
    d = to_json_dict(build_graph(tmp_path), include_aims=True)
    assert "narrative" not in d
