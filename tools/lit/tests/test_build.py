# tests/test_build.py
import json
from pathlib import Path
from litgraph.graph import build_graph
from litgraph.build import to_json_dict, emit

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


def test_emit_writes_self_contained_viewer(tmp_path):
    g = build_graph(EXAMPLE)
    emit(g, tmp_path)
    gj = tmp_path / "graph.json"
    html = tmp_path / "index.html"
    assert gj.exists() and html.exists()
    # graph.json round-trips
    data = json.loads(gj.read_text())
    assert "Ruppel2023NatPhys" in data["papers"]
    # index.html has the JSON inlined (self-contained) and no leftover token
    text = html.read_text()
    assert "Ruppel2023NatPhys" in text
    assert "__GRAPH_JSON__" not in text


from litgraph.cli import main


def test_cli_build_writes_dist(tmp_path, capsys):
    rc = main(["build", "--root", str(EXAMPLE), "--out", str(tmp_path / "dist")])
    assert rc == 0
    assert (tmp_path / "dist" / "index.html").exists()
    out = capsys.readouterr().out
    assert "dist" in out  # reports where it wrote


def test_cli_build_reports_validation_error(tmp_path, capsys):
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Bad2020Jrnl.yaml").write_text(
        'title: t\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n'
        'claims:\n  - {id: c1, text: x, grounded_in: [m9]}\n')
    rc = main(["build", "--root", str(tmp_path), "--out", str(tmp_path / "dist")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "m9" in err


def test_emit_escapes_script_close_in_inlined_json(tmp_path):
    # a paper whose text contains "</script>" must not break the self-contained page
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Evil2020Jrnl.yaml").write_text(
        'title: "danger </script><b>x</b>"\ntype: original\nyear: 2020\n'
        'authors: [{name: "A, B"}]\n')
    out = tmp_path / "dist"
    emit(build_graph(tmp_path), out)
    html = (out / "index.html").read_text()
    # the only literal </script> is the real closing tag (data occurrence is escaped)
    assert html.count("</script>") == 1
    assert "\\u003c/script>" in html
    # graph.json keeps the raw (unescaped) value and round-trips
    data = json.loads((out / "graph.json").read_text())
    assert data["papers"]["Evil2020Jrnl"]["title"] == "danger </script><b>x</b>"
