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
