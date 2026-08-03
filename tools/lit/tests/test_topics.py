"""The topic axis (SCHEMA §9): loading, validation, derived membership, coverage report.

Offline and deterministic — inline fixtures only. The point these tests defend is that a
topic is *not* graph: membership is derived from paper tags, and nothing about a topic can
reach into the slice model.
"""

from pathlib import Path

import pytest

from litgraph.graph import Paper, build_graph
from litgraph.topics import (
    TopicError,
    children,
    coverage,
    keyword_closure,
    load_topics,
    papers_in,
    roots,
    validate_topics,
)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "topics").mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (tmp_path / "topics" / f"{name}.yaml").write_text(body)
    return tmp_path


def _paper(ck: str, *tags: str) -> Paper:
    return Paper(citekey=ck, curated=True, title=ck, type="original", year=2020,
                 tags=list(tags))


# --- loading ----------------------------------------------------------------

def test_absent_topics_tree_is_empty_not_an_error(tmp_path):
    assert load_topics(tmp_path) == {}


def test_load_reads_fields_and_defaults(tmp_path):
    root = _repo(tmp_path, {"cancer": 'title: "Cancer"\nnote: "n"\nkeywords: [a, b]\n',
                            "bare": 'title: "Bare"\nkeywords: []\n'})
    t = load_topics(root)
    assert t["cancer"].title == "Cancer" and t["cancer"].note == "n"
    assert t["cancer"].keywords == ["a", "b"] and t["cancer"].broader == []
    assert t["bare"].keywords == [] and t["bare"].broader == []


# --- validation (SCHEMA §9.1, §9.2) ----------------------------------------

def test_dangling_broader_raises(tmp_path):
    t = load_topics(_repo(tmp_path, {"a": 'title: "A"\nbroader: [nope]\nkeywords: []\n'}))
    with pytest.raises(TopicError, match="unknown topic"):
        validate_topics(t)


def test_broader_cycle_raises_and_names_the_path(tmp_path):
    t = load_topics(_repo(tmp_path, {
        "a": 'title: "A"\nbroader: [b]\nkeywords: []\n',
        "b": 'title: "B"\nbroader: [a]\nkeywords: []\n'}))
    with pytest.raises(TopicError, match="cycle"):
        validate_topics(t)


def test_self_parent_is_a_cycle(tmp_path):
    t = load_topics(_repo(tmp_path, {"a": 'title: "A"\nbroader: [a]\nkeywords: []\n'}))
    with pytest.raises(TopicError, match="cycle"):
        validate_topics(t)


def test_slug_colliding_with_a_broad_slice_raises(tmp_path):
    """A topic must never share a name with a claim/question/method: bare slugs resolve
    against those, so an overlap would read as a claim in an edge and a topic here."""
    t = load_topics(_repo(tmp_path, {"jamming": 'title: "J"\nkeywords: []\n'}))
    with pytest.raises(TopicError, match="also names a broad"):
        validate_topics(t, {"jamming"})
    validate_topics(t, {"something-else"})          # no clash -> fine


def test_a_topic_may_have_several_parents(tmp_path):
    """The axis is a DAG, not a tree — two parents is legal and must not read as a cycle."""
    t = load_topics(_repo(tmp_path, {
        "top1": 'title: "T1"\nkeywords: []\n',
        "top2": 'title: "T2"\nkeywords: []\n',
        "leaf": 'title: "L"\nbroader: [top1, top2]\nkeywords: [k]\n'}))
    validate_topics(t)
    assert children(t)["top1"] == ["leaf"] and children(t)["top2"] == ["leaf"]
    assert sorted(roots(t)) == ["top1", "top2"]


# --- derived membership (SCHEMA §9) ----------------------------------------

def test_keywords_roll_up_through_broader(tmp_path):
    t = load_topics(_repo(tmp_path, {
        "head": 'title: "H"\nkeywords: [own]\n',
        "leaf": 'title: "L"\nbroader: [head]\nkeywords: [below]\n'}))
    assert keyword_closure(t, "head") == {"own", "below"}
    assert keyword_closure(t, "leaf") == {"below"}       # closure runs down, never up


def test_membership_is_derived_from_tags_only(tmp_path):
    t = load_topics(_repo(tmp_path, {
        "head": 'title: "H"\nkeywords: []\n',
        "leaf": 'title: "L"\nbroader: [head]\nkeywords: [jamming]\n'}))
    papers = {"A": _paper("A", "jamming"), "B": _paper("B", "vimentin")}
    assert papers_in(t, "leaf", papers) == ["A"]
    assert papers_in(t, "head", papers) == ["A"]         # reached through the child
    assert papers_in(t, "leaf", {"B": papers["B"]}) == []


def test_matching_is_case_insensitive(tmp_path):
    t = load_topics(_repo(tmp_path, {"a": 'title: "A"\nkeywords: [Jamming]\n'}))
    assert papers_in(t, "a", {"P": _paper("P", "JAMMING")}) == ["P"]


def test_stubs_are_never_in_a_topic(tmp_path):
    """Topics file the curated library. Tagged with a matching keyword anyway, so this
    pins the `curated` gate rather than merely the fact that stubs carry no tags."""
    t = load_topics(_repo(tmp_path, {"a": 'title: "A"\nkeywords: [k]\n'}))
    stub = Paper(citekey="S", curated=False, title="S", type="original", year=2020,
                 tags=["k"])
    assert papers_in(t, "a", {"S": stub}) == []


def test_a_keyword_may_belong_to_several_topics(tmp_path):
    t = load_topics(_repo(tmp_path, {
        "cancer": 'title: "C"\nkeywords: [glioblastoma]\n',
        "neuro": 'title: "N"\nkeywords: [glioblastoma]\n'}))
    papers = {"G": _paper("G", "glioblastoma")}
    assert papers_in(t, "cancer", papers) == ["G"] == papers_in(t, "neuro", papers)


# --- coverage report (SCHEMA §9.3) -----------------------------------------

def test_coverage_reports_unfiled_dead_and_stranded(tmp_path):
    t = load_topics(_repo(tmp_path, {"a": 'title: "A"\nkeywords: [filed, ghost]\n'}))
    papers = {"A": _paper("A", "filed"), "B": _paper("B", "loose"), "C": _paper("C")}
    unfiled, dead, stranded = coverage(t, papers)
    assert unfiled == ["loose"]         # on a paper, in no topic
    assert dead == ["ghost"]            # in a topic, on no paper
    assert stranded == ["B", "C"]       # reached by nothing


def test_clean_library_reports_nothing(tmp_path):
    t = load_topics(_repo(tmp_path, {"a": 'title: "A"\nkeywords: [k]\n'}))
    assert coverage(t, {"A": _paper("A", "k")}) == ([], [], [])


# --- integration: the axis rides along on build, and stays out of the graph --

def test_build_graph_loads_and_validates_topics(tmp_path):
    (tmp_path / "curated").mkdir()
    (tmp_path / "claims").mkdir()
    _repo(tmp_path, {"a": 'title: "A"\nkeywords: [k]\n'})
    g = build_graph(tmp_path)
    assert set(g.topics) == {"a"}
    assert g.topics["a"].keywords == ["k"]


def test_build_graph_rejects_a_broken_topic_tree(tmp_path):
    (tmp_path / "curated").mkdir()
    _repo(tmp_path, {"a": 'title: "A"\nbroader: [missing]\nkeywords: []\n'})
    with pytest.raises(TopicError):
        build_graph(tmp_path)


def test_worked_example_tree_is_valid(tmp_path):
    """SCHEMA §9 is defined by this spec *plus* the example/ tree, so the tree must hold:
    a heading with no keywords of its own, roll-up through `broader`, and one keyword
    (`batching`) shared by two topics."""
    example = Path(__file__).resolve().parents[3] / "example"
    t = load_topics(example)
    validate_topics(t)
    assert roots(t) == ["performance"]
    assert t["performance"].keywords == []
    assert keyword_closure(t, "performance") == {"throughput", "batching", "queueing-model"}
    assert "batching" in keyword_closure(t, "throughput")
    assert "batching" in keyword_closure(t, "modelling")


def test_a_topic_slug_is_not_a_valid_edge_target(tmp_path):
    """SCHEMA §9.4 — the axis is invisible to the slice model, so a claim pointing at a
    topic is a dangling ref, not a quiet cross-axis link."""
    from litgraph.graph import BuildError
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "X2020Jour.yaml").write_text(
        'title: "X"\ntype: original\nyear: 2020\nauthors: [{name: A}]\n'
        'claims:\n  - id: c1\n    text: "t"\n    quote: "q"\n    leads_to: [cancer]\n')
    _repo(tmp_path, {"cancer": 'title: "C"\nkeywords: [k]\n'})
    with pytest.raises(BuildError, match="dangling ref"):
        build_graph(tmp_path)
