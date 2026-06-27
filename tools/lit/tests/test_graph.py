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
