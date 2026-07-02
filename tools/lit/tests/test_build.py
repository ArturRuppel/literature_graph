# tests/test_build.py
import json
from pathlib import Path
from litgraph.graph import build_graph, Paper, Slice
from litgraph.build import to_json_dict, emit, _cons

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
    # the weld (exact quote) and answers edges ride along for the viewer's drill-down
    assert c1["quote"].startswith("throughput increased monotonically")
    c4 = next(s for s in p["slices"] if s["id"] == "c4")
    assert c4["answers"] == ["q2"]
    m1_q = next(s for s in p["slices"] if s["id"] == "m1")["quote"]
    assert m1_q is None                                   # methods' quotes are optional
    assert any(g["via"] == "m1" for g in p["grounds"])          # grounds -> left
    # container (unsharpened) grounds carry tid=None — the wildcard "some slice in here";
    # a sharpened ground keeps its target slice (Chen m2 extends Lopez2019Arch:m2)
    assert {"key": "Lopez2019Arch", "tid": "m2", "via": "m2"} in p["grounds"]
    assert all(g["tid"] is None for g in p["grounds"] if g["key"] != "Lopez2019Arch")
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
    # cross-paper answers edges are emitted separately (local ones nest via slice "answers")
    assert k["ans"] == [{"key": "Lopez2019Arch", "tid": "q1", "via": "c2"}]
    assert p["ans"] == []                                 # Chen's c4->q2 answer is local
    # inverted grounds: Lopez's builds-on lists Chen (m2 grounds in Lopez2019Arch:m2)
    lo = d["papers"]["Lopez2019Arch"]
    assert lo["builds"] == [{"key": "Chen2021Sys", "tid": "m2", "via": "m2"}]
    assert p["builds"] == []                              # nothing grounds in Chen (yet)
    # the cross-paper answer flips Lopez q1 to answered (emergent, SCHEMA §7)
    assert next(s for s in lo["slices"] if s["id"] == "q1")["answered"] is True
    # stubs are separated out (one-line cards), not under papers' slices
    assert "Patel2017Vldb" in d["stubs"]
    assert d["stubs"]["Patel2017Vldb"]["year"] == 2017
    # broad claim carries its meter
    assert "meter" in d["broad"]["throughput-scales-with-batching"]
    # order is papers (curated + stubs), curated first
    assert d["order"][0] == "Chen2021Sys"


def test_cons_skips_local_generalization():
    # a local leads_to is a same-paper ladder (nests in place); only broad slugs are
    # right-band synthesis nodes, so a phantom "c3" node must not be emitted.
    p = Paper(citekey="P1", curated=True, title="", type="original", year=2023,
              slices=[Slice(id="c1", kind="claim", text="x", leads_to=["c3", "b-claim"]),
                      Slice(id="c3", kind="claim", text="broader")])
    cons = _cons(p)
    assert {"slug": "b-claim", "via": "c1"} in cons
    assert all(co["slug"] != "c3" for co in cons)


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


from litgraph.graph import Graph, Paper, Slice
from litgraph.build import _answers, _builds


def _paper(citekey, *slices, curated=True):
    return Paper(citekey=citekey, curated=curated, title="", type="original",
                 year=2023, slices=list(slices))


def test_answers_emits_cross_paper_forms_only():
    p = _paper("P1",
               Slice(id="q1", kind="question", text="?"),
               Slice(id="c1", kind="claim", text="x",
                     answers=["q1", "Other2020Jrnl:q2", "Stub2019Conf", "broad-q"]))
    out = _answers(p)
    # local q1 nests in place; sharpened keeps tid; container is the wildcard (tid=None);
    # a broad question slug routes to the synthesis band
    assert out == [{"key": "Other2020Jrnl", "tid": "q2", "via": "c1"},
                   {"key": "Stub2019Conf", "tid": None, "via": "c1"},
                   {"slug": "broad-q", "via": "c1"}]


def test_builds_inverts_grounds_between_curated_papers_only():
    old = _paper("Old2019Jrnl", Slice(id="m1", kind="method", text="f"))
    new = _paper("New2021Jrnl",
                 Slice(id="m1", kind="method", text="g",
                       grounded_in=["Old2019Jrnl:m1", "Stub2016Conf"]),
                 Slice(id="c1", kind="claim", text="x", grounded_in=["Old2019Jrnl"]))
    stub = _paper("Stub2016Conf", curated=False)
    g = Graph(papers={"Old2019Jrnl": old, "New2021Jrnl": new, "Stub2016Conf": stub},
              broad={}, order=[])
    idx = _builds(g)
    # both the sharpened and the container ground invert onto the curated source;
    # the stub target gets no builds entry (stubs cannot be focused)
    assert idx == {"Old2019Jrnl": [
        {"key": "New2021Jrnl", "tid": "m1", "via": "m1"},
        {"key": "New2021Jrnl", "tid": None, "via": "c1"}]}


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
