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


# tests/test_graph.py  (add)
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
