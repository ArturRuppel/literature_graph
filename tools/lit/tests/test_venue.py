import pytest

from litgraph.venue import venue_token


@pytest.mark.parametrize(
    "display, expected",
    [
        ("eLife", "eLife"),
        ("Biophysical Journal", "BiophysJ"),
        ("Developmental Cell", "DevCell"),
        ("Nature Physics", "NatPhys"),
        ("Physical Review Letters", "PhysRevLett"),
        ("Biochimica et Biophysica Acta (BBA) - Molecular Cell Research", "BBA"),
        ("Proceedings of the National Academy of Sciences", "Pnas"),
    ],
)
def test_venue_token(display, expected):
    assert venue_token(display) == expected


def test_venue_token_empty():
    assert venue_token(None) == ""
    assert venue_token("   ") == ""
