# tests/test_build.py
from pathlib import Path
from litgraph.graph import build_graph
from litgraph.build import to_json_dict

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def test_to_json_dict_shape():
    d = to_json_dict(build_graph(EXAMPLE))
    assert set(d) == {"papers", "broad", "stubs", "order"}
    # curated paper carries computed slices + edge lists
    p = d["papers"]["Ruppel2023NatPhys"]
    assert p["cur"] is True and p["pass"] == 3
    assert p["authors"][0] == ["Ruppel, Artur", "first", False]
    c1 = next(s for s in p["slices"] if s["id"] == "c1")
    assert c1["color"] == "grounded" and c1["kind"] == "claim"
    assert any(g["via"] == "m1" for g in p["grounds"])          # grounds -> left
    assert any(co["slug"] == "traction-scales-with-stiffness" for co in p["cons"])
    assert any(l["sign"] in ("corr", "contra") for l in p["lateral"])
    # stubs are separated out (one-line cards), not under papers' slices
    assert "Ramms2013Pnas" in d["stubs"]
    assert d["stubs"]["Ramms2013Pnas"]["year"] == 2013
    # broad claim carries its meter
    assert "meter" in d["broad"]["traction-scales-with-stiffness"]
    # order is papers (curated + stubs), curated first
    assert d["order"][0] == "Ruppel2023NatPhys"
