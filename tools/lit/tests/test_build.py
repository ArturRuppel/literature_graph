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
    p = d["papers"]["Chen2021Sys"]
    assert p["cur"] is True and p["pass"] == 4
    assert p["authors"][0] == ["Chen, Mei", "first", False]
    c1 = next(s for s in p["slices"] if s["id"] == "c1")
    assert c1["color"] == "grounded" and c1["kind"] == "claim"
    # each slice carries its within-paper support refs (local grounded_in only)
    assert c1["up"] == ["m1"]          # c1 builds on the floor m1 (substructure)
    m1 = next(s for s in p["slices"] if s["id"] == "m1")
    assert m1["up"] == []              # the floor builds on nothing local (grounds in a citation)
    assert all(ref.startswith(("c", "q", "m")) and ":" not in ref
               for s in p["slices"] for ref in s["up"])   # local refs only
    assert any(g["via"] == "m1" for g in p["grounds"])          # grounds -> left
    # container (unsharpened) grounds carry tid=None — the wildcard "some slice in here"
    assert all(g["tid"] is None for g in p["grounds"])
    assert any(co["slug"] == "throughput-scales-with-batching" for co in p["cons"])
    assert any(l["sign"] in ("corr", "contra") for l in p["lateral"])
    # a lateral ref to a broad slug routes to the synthesis band ({slug}), not a paper ({key})
    broad_lat = [l for l in p["lateral"] if "slug" in l]
    assert broad_lat == [{"slug": "throughput-scales-with-batching",
                          "sign": "contra", "via": "c3"}]
    assert all("key" not in l for l in broad_lat)
    # sharpened lateral refs keep the specific target slice (Kumar -> Chen2021Sys:c1/:c2)
    k = d["papers"]["Kumar2020Net"]
    assert {"key": "Chen2021Sys", "tid": "c1", "sign": "corr", "via": "c1"} in k["lateral"]
    assert {"key": "Chen2021Sys", "tid": "c2", "sign": "contra", "via": "c2"} in k["lateral"]
    # stubs are separated out (one-line cards), not under papers' slices
    assert "Patel2017Vldb" in d["stubs"]
    assert d["stubs"]["Patel2017Vldb"]["year"] == 2017
    # broad claim carries its meter
    assert "meter" in d["broad"]["throughput-scales-with-batching"]
    # order is papers (curated + stubs), curated first
    assert d["order"][0] == "Chen2021Sys"


def test_emit_writes_self_contained_viewer(tmp_path):
    g = build_graph(EXAMPLE)
    emit(g, tmp_path)
    gj = tmp_path / "graph.json"
    html = tmp_path / "index.html"
    assert gj.exists() and html.exists()
    # graph.json round-trips
    data = json.loads(gj.read_text())
    assert "Chen2021Sys" in data["papers"]
    # index.html has the JSON inlined (self-contained) and no leftover token
    text = html.read_text()
    assert "Chen2021Sys" in text
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
