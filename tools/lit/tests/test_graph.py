from pathlib import Path

from litgraph.graph import classify_ref


def test_classify_ref_forms():
    assert classify_ref("c1") == "local"
    assert classify_ref("m12") == "local"
    assert classify_ref("q3") == "local"
    assert classify_ref("Liu2010Pnas") == "container"
    assert classify_ref("Ruppel2023eLife") == "container"
    assert classify_ref("Liu2010Pnas:c3") == "sharpened"
    assert classify_ref("force-propagation-is-active") == "broad"
    assert classify_ref("jamming") == "broad"


from litgraph.graph import load_repo, Paper, Slice

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def test_load_repo_reads_curated_and_stubs():
    papers, broad = load_repo(EXAMPLE)
    assert "Ruppel2023NatPhys" in papers
    p = papers["Ruppel2023NatPhys"]
    assert isinstance(p, Paper)
    assert p.curated is True
    assert p.type == "original" and p.year == 2023 and p.pass_ == 3
    assert ("Ruppel, Artur", "first", False) in p.authors
    # stubs load as un-sliced containers
    assert papers["Ramms2013Pnas"].curated is False
    assert papers["Ramms2013Pnas"].slices == []
    # a curated claim parses its edges
    c1 = next(s for s in p.slices if s.id == "c1")
    assert c1.kind == "claim"
    assert "traction-scales-with-stiffness" in c1.leads_to
    # broad nodes load
    assert "traction-scales-with-stiffness" in broad
    assert broad["traction-scales-with-stiffness"].kind == "broad claim"


def test_load_repo_rejects_curated_stub_collision(tmp_path):
    import pytest
    from litgraph.graph import load_repo, BuildError
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Dup2020Jrnl.yaml").write_text(
        'title: t\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n')
    (tmp_path / "stubs.yaml").write_text("Dup2020Jrnl:\n  title: t\n  year: 2020\n")
    with pytest.raises(BuildError, match="Dup2020Jrnl"):
        load_repo(tmp_path)


from litgraph.graph import method_is_floor


def test_method_floor_vs_model():
    # floor: grounds only in containers (its source papers)
    floor = Slice(id="m2", kind="method", text="TFM",
                  grounded_in=["Sabass2007BiophysJ", "Bauer2021PloComputBiology"])
    assert method_is_floor(floor) is True
    # floor: no grounding at all still bottoms out
    assert method_is_floor(Slice(id="m1", kind="method", text="x")) is True
    # model: layers on another method (a local m-ref)
    model = Slice(id="m3", kind="method", text="MSM", grounded_in=["m2", "Tambe2011NatMater"])
    assert method_is_floor(model) is False


from litgraph.graph import claim_is_borrowed, reaches_floor


def test_claim_borrowed():
    borrowed = Slice(id="c4", kind="claim", text="borrowed", grounded_in=["Ramms2013Pnas"])
    assert claim_is_borrowed(borrowed) is True
    original = Slice(id="c1", kind="claim", text="orig", grounded_in=["m1"])
    assert claim_is_borrowed(original) is False
    sharp = Slice(id="c5", kind="claim", text="x", grounded_in=["Liu2010Pnas:c3"])
    assert claim_is_borrowed(sharp) is True


def test_reaches_floor():
    m1 = Slice(id="m1", kind="method", text="floor", is_floor=True)
    m3 = Slice(id="m3", kind="method", text="model", grounded_in=["m1"], is_floor=False)
    c1 = Slice(id="c1", kind="claim", text="grounded", grounded_in=["m3"])
    c3 = Slice(id="c3", kind="claim", text="theory", grounded_in=["c1"])
    c9 = Slice(id="c9", kind="claim", text="plausible", grounded_in=["Some2010Paper"])
    by_id = {s.id: s for s in (m1, m3, c1, c3, c9)}
    assert reaches_floor(c1, by_id) is True          # c1 -> m3 -> m1 (floor)
    assert reaches_floor(c3, by_id) is True           # c3 -> c1 -> ... -> floor
    assert reaches_floor(c9, by_id) is False          # grounds only in a citation


from litgraph.graph import answered_question_ids, broad_meter


def _paper(citekey, *slices):
    return Paper(citekey=citekey, curated=True, title="", type="original", year=2023,
                 slices=list(slices))


def test_answered_question_ids():
    p = _paper("P1",
               Slice(id="q1", kind="question", text="?"),
               Slice(id="q2", kind="question", text="?"),
               Slice(id="c1", kind="claim", text="ans", answers=["q1"]))
    assert answered_question_ids({"P1": p}) == {"P1:q1"}


def test_broad_meter_counts_support_and_contradict():
    # c1 generalizes into the broad claim (support); c2 contradicts the slug directly
    p1 = _paper("P1", Slice(id="c1", kind="claim", text="x", leads_to=["b-claim"]))
    p2 = _paper("P2", Slice(id="c2", kind="claim", text="y", contradicts=["b-claim"]))
    s, c = broad_meter("b-claim", {"P1": p1, "P2": p2})
    assert s == 1          # one claim generalizes into it (leads_to)
    assert c == 1          # one claim contradicts the slug directly


import pytest
from litgraph.graph import validate, BuildError, BroadNode


def test_validate_passes_clean_repo():
    p = _paper("P1",
               Slice(id="m1", kind="method", text="f"),
               Slice(id="c1", kind="claim", text="x", grounded_in=["m1"],
                     leads_to=["b-claim"]))
    broad = {"b-claim": BroadNode(slug="b-claim", kind="broad claim", text="b")}
    validate({"P1": p}, broad)   # no raise


def test_validate_flags_dangling_ref():
    p = _paper("P1", Slice(id="c1", kind="claim", text="x", grounded_in=["m9"]))
    with pytest.raises(BuildError, match="m9"):
        validate({"P1": p}, {})


def test_validate_flags_duplicate_local_id():
    p = _paper("P1",
               Slice(id="c1", kind="claim", text="a"),
               Slice(id="c1", kind="claim", text="b"))
    with pytest.raises(BuildError, match="c1"):
        validate({"P1": p}, {})


from litgraph.graph import build_graph, Graph


def test_build_graph_example():
    g = build_graph(EXAMPLE)
    assert isinstance(g, Graph)
    p = g.papers["Ruppel2023NatPhys"]
    by_id = {s.id: s for s in p.slices}
    # m1 is a floor (grounds only in a container)
    assert by_id["m1"].is_floor is True and by_id["m1"].color == "floor"
    # c1 grounds in m1 -> grounded + original
    assert by_id["c1"].grounded is True and by_id["c1"].borrowed is False
    assert by_id["c1"].color == "grounded"
    # c4 grounds in a citation -> borrowed
    assert by_id["c4"].borrowed is True and by_id["c4"].color == "borrowed"
    # q2 answered (c4 answers it), q1 open
    assert by_id["q2"].answered is True
    assert by_id["q1"].answered is False
    # top-altitude claims become the head (no outgoing leads_to) -- c3 has only contradicts
    assert p.head  # non-empty
    # broad-claim meter (example: 1 support via c1 leads_to, 1 contradict via c3)
    b = g.broad["traction-scales-with-stiffness"]
    assert (b.support, b.contradict) == (1, 1)
    # landing order: curated before stubs
    assert g.order[0] == "Ruppel2023NatPhys"
    assert g.order.index("Ruppel2023NatPhys") < g.order.index("Ramms2013Pnas")


def test_build_graph_handles_skeleton_paper(tmp_path):
    # a curated paper with no slices and no `pass` is valid and sorts after passed papers
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Bare2020Jrnl.yaml").write_text(
        'title: "x"\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n')
    (tmp_path / "stubs.yaml").write_text("Old1990Jrnl:\n  title: t\n  year: 1990\n")
    g = build_graph(tmp_path)
    assert g.papers["Bare2020Jrnl"].slices == []
    assert g.order == ["Bare2020Jrnl", "Old1990Jrnl"]  # curated before stub
