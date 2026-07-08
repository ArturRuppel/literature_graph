# tests/test_serve.py
"""`lit serve` — loopback only: every request hits 127.0.0.1, no external network."""
import http.client
import json
import shutil
import threading
from pathlib import Path

import fitz
import pytest

from litgraph.serve import make_server

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def _tiny_pdf() -> bytes:
    """A real one-page PDF, generated offline — /preview must be able to render it."""
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 100), "fixture paper")
        return doc.tobytes()


FAKE_PDF = _tiny_pdf()


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(EXAMPLE, root)
    (root / "pdfs").mkdir()
    (root / "pdfs" / "Chen2021Sys.pdf").write_bytes(FAKE_PDF)
    return root


@pytest.fixture()
def srv(repo):
    s = make_server(repo, repo / "pdfs")            # port 0 -> ephemeral
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s
    s.shutdown()
    s.server_close()


def get(srv, path, method="GET"):
    """Raw request (no client-side path normalization — traversal reaches the server)."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    conn.request(method, path)
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, dict(r.getheaders()), body


def post(srv, path, obj):
    """POST a JSON body to the loopback server; return (status, parsed-or-bytes)."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    conn.request("POST", path, json.dumps(obj))
    r = conn.getresponse()
    body = r.read()
    conn.close()
    ctype = r.getheader("Content-Type", "")
    return r.status, (json.loads(body) if ctype.startswith("application/json") else body)


def test_index_serves_viewer_with_live_rebuild_headers(srv):
    status, headers, body = get(srv, "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Cache-Control"] == "no-store"    # refresh must re-read the YAML
    text = body.decode()
    assert "Chen2021Sys" in text and "__GRAPH_JSON__" not in text


def test_graph_json_endpoint(srv):
    status, headers, body = get(srv, "/graph.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "Chen2021Sys" in json.loads(body)["papers"]


def test_preview_html_isolates_one_curated_paper(srv):
    status, headers, body = get(srv, "/preview.html?key=Chen2021Sys")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    # the same viewer template, inlined with the isolate()'d single-paper payload
    assert b'"order": ["Chen2021Sys"]' in body


def test_preview_html_rejects_unknown_and_stub_keys(srv):
    # a citekey with no curated file
    assert get(srv, "/preview.html?key=NoSuchPaper2099")[0] == 404
    # a stub (uncurated container) is not previewable — only curated papers isolate
    assert get(srv, "/preview.html?key=Bench2016Tools")[0] == 404


def test_pdf_manifest_and_fetch(srv):
    status, _, body = get(srv, "/pdfs.json")
    assert status == 200
    assert json.loads(body) == ["Chen2021Sys"]       # only papers with a PDF on disk
    status, headers, body = get(srv, "/pdf/Chen2021Sys.pdf")
    assert status == 200
    assert headers["Content-Type"] == "application/pdf"
    assert body == FAKE_PDF
    # HEAD: headers only
    status, headers, body = get(srv, "/pdf/Chen2021Sys.pdf", method="HEAD")
    assert status == 200 and body == b""
    assert headers["Content-Length"] == str(len(FAKE_PDF))


def test_preview_renders_first_page_png_and_caches(srv):
    status, headers, body = get(srv, "/preview/Chen2021Sys.png")
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG\r\n")            # real pixels, not a stub
    assert get(srv, "/preview/Chen2021Sys.png")[2] == body   # mtime-cached


def test_preview_missing_or_corrupt(srv, repo):
    assert get(srv, "/preview/Nope2020Xyz.png")[0] == 404
    (repo / "pdfs" / "Bad2020Jrnl.pdf").write_bytes(b"not a pdf at all")
    assert get(srv, "/preview/Bad2020Jrnl.png")[0] == 500    # named, server survives
    assert get(srv, "/pdfs.json")[0] == 200


def test_pdf_missing_is_404(srv):
    status, _, _ = get(srv, "/pdf/Nope2020Xyz.pdf")
    assert status == 404


def test_pdf_traversal_is_rejected(srv):
    # only a flat <citekey>.<ext> name is servable — separators and dotfiles never resolve
    for path in ("/pdf/../stubs.yaml", "/pdf/..%2fstubs.yaml",
                 "/pdf/%2e%2e/curated/Chen2021Sys.yaml", "/pdf/sub/dir.pdf",
                 "/pdf/.hidden.pdf", "/preview/../stubs.yaml", "/preview/a/b.png"):
        status, _, _ = get(srv, path)
        assert status == 404, path


def test_unknown_path_is_404(srv):
    assert get(srv, "/etc/passwd")[0] == 404


def test_refresh_rebuilds_from_yaml(srv, repo):
    f = repo / "curated" / "Chen2021Sys.yaml"
    f.write_text(f.read_text().replace(
        "Batching improves throughput", "Batching improves LIVE-EDITED throughput"))
    status, _, body = get(srv, "/")
    assert status == 200 and "LIVE-EDITED" in body.decode()


def test_broken_edit_returns_500_and_recovers(srv, repo):
    f = repo / "curated" / "Chen2021Sys.yaml"
    good = f.read_text()
    f.write_text(good.replace("grounded_in:  [m1]", "grounded_in:  [m99]", 1))
    status, _, body = get(srv, "/")
    assert status == 500 and "m99" in body.decode()   # names the offender, server survives
    f.write_text(good)
    assert get(srv, "/")[0] == 200


# ── PDF quote windows: any-page render, search_for resolver, quote_loc write-back ─────────

from litgraph.serve import _needles


def test_needles_prefers_long_then_backs_off_with_hyphen_variant():
    ns = _needles("Fast and long- ranged propagation of mechanical force here")
    # the full phrase (whitespace-normalized) leads; a hyphen-glued variant appears
    assert ns[0] == "Fast and long- ranged propagation of mechanical force here"
    assert "Fast and long-ranged propagation of mechanical force here" in ns
    # leading-window backoff, longest → shortest, down to two words
    assert ns[-1] == "Fast and"
    assert ns.index("Fast and long-") < ns.index("Fast and") or "Fast and long-" not in ns


def test_locate_quote_covers_a_hyphenated_line_break(tmp_path):
    # the word-geometry matcher must cover the WHOLE quote even where a word is hyphenated
    # across a line break — exactly where `search_for` fails and the old resolver boxed only a
    # leading fragment (SCHEMA §6 full-coverage anchors)
    from litgraph.serve import locate_quote
    p = tmp_path / "hyph.pdf"
    with fitz.open() as doc:
        pg = doc.new_page()
        pg.insert_text((72, 100), "mechano-")        # a word split across the line break …
        pg.insert_text((72, 120), "structural coupling")
        doc.save(str(p))
    loc = locate_quote(p, "mechanostructural coupling")   # … re-joined in the .md-derived quote
    assert loc and loc["page"] == 0
    assert len(loc["rects"]) == 2                    # both lines boxed, head + tail
    assert fitz.open(p)[0].search_for("mechanostructural coupling") == []  # search_for alone can't


def test_page_render_any_page_and_out_of_range(srv):
    status, headers, body = get(srv, "/page/Chen2021Sys/0.png")
    assert status == 200 and headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG\r\n")
    assert get(srv, "/page/Chen2021Sys/9.png")[0] == 404   # one-page fixture: page 9 absent
    assert get(srv, "/page/Nope2020Xyz/0.png")[0] == 404


def test_words_endpoint_serves_page_fraction_boxes(srv):
    # the selectable text overlay is fed by per-page word geometry, same page.rect normalization
    # as the highlight rects so it registers on the raster
    status, headers, body = get(srv, "/words/Chen2021Sys/0.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "max-age" in headers["Cache-Control"]            # immutable until the PDF's mtime changes
    words = json.loads(body)
    assert [w["t"] for w in words][:2] == ["fixture", "paper"]   # reading order, whitespace dropped
    for w in words:
        assert set(w) == {"t", "x0", "y0", "x1", "y1", "ln"}
        assert all(0 <= w[k] <= 1 for k in ("x0", "y0", "x1", "y1"))
    assert get(srv, "/words/Chen2021Sys/9.json")[0] == 404   # one-page fixture: page 9 absent
    assert get(srv, "/words/Nope2020Xyz/0.json")[0] == 404


def test_pages_manifest_lists_every_page_size(srv):
    # the pinned viewer lays out the whole document from this per-page point-size manifest
    status, headers, body = get(srv, "/pages/Chen2021Sys.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "max-age" in headers["Cache-Control"]
    sizes = json.loads(body)
    assert len(sizes) == 1                                   # one-page fixture
    assert all(len(s) == 2 and s[0] > 0 and s[1] > 0 for s in sizes)
    assert get(srv, "/pages/Nope2020Xyz.json")[0] == 404


def test_page_and_preview_are_browser_cacheable_but_html_is_not(srv):
    # live-rebuilt HTML must never cache; immutable page/preview images should, so reopening a
    # quote window doesn't refetch/redecode
    assert get(srv, "/")[1]["Cache-Control"] == "no-store"
    assert "max-age" in get(srv, "/page/Chen2021Sys/0.png")[1]["Cache-Control"]
    assert "max-age" in get(srv, "/preview/Chen2021Sys.png")[1]["Cache-Control"]


def test_resolve_hits_and_misses(srv):
    status, loc = post(srv, "/resolve", {"citekey": "Chen2021Sys", "quote": "fixture paper"})
    assert status == 200 and loc["page"] == 0
    assert len(loc["rects"]) >= 1
    assert all(len(r) == 4 and all(0 <= v <= 1 for v in r) for r in loc["rects"])
    # absent text → null (curator then draws the box by hand)
    assert post(srv, "/resolve", {"citekey": "Chen2021Sys", "quote": "no such sentence here"})[1] is None
    assert post(srv, "/resolve", {"citekey": "Nope2020Xyz", "quote": "x"}) == (404, None)


def test_quote_loc_writeback_persists_and_shows_in_graph(srv, repo):
    rects = [[0.1, 0.2, 0.5, 0.23]]
    status, res = post(srv, "/quote_loc",
                       {"citekey": "Chen2021Sys", "slice_id": "c1", "page": 0, "rects": rects})
    assert status == 200 and res == {"ok": True}
    # written into the YAML, round-tripped
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((repo / "curated" / "Chen2021Sys.yaml").read_text())
    c1 = next(s for s in doc["claims"] if s["id"] == "c1")
    assert c1["quote_loc"] == {"page": 0, "rects": rects}
    # and surfaced in the rebuilt graph.json
    g = json.loads(get(srv, "/graph.json")[2])
    s = next(x for x in g["papers"]["Chen2021Sys"]["slices"] if x["id"] == "c1")
    assert s["loc"] == {"page": 0, "rects": rects}


def test_quote_loc_rejects_bad_payloads(srv):
    assert post(srv, "/quote_loc",                       # rect out of [0,1]
                {"citekey": "Chen2021Sys", "slice_id": "c1", "page": 0, "rects": [[0, 0, 2, 1]]})[0] == 400
    assert post(srv, "/quote_loc",                       # empty rects
                {"citekey": "Chen2021Sys", "slice_id": "c1", "page": 0, "rects": []})[0] == 400
    assert post(srv, "/quote_loc",                       # unknown slice
                {"citekey": "Chen2021Sys", "slice_id": "c9", "page": 0, "rects": [[0, 0, 1, 1]]})[0] == 404
    assert post(srv, "/quote_loc",                       # bad slice-id form
                {"citekey": "Chen2021Sys", "slice_id": "../x", "page": 0, "rects": [[0, 0, 1, 1]]})[0] == 400


# ── focus channel: the shared "aim the PDF pane here" wire ────────────────────────────────


def test_focus_starts_empty(srv):
    status, _, body = get(srv, "/focus")
    assert status == 200
    assert json.loads(body) == {"seq": 0, "citekey": None, "quote": None, "loc": None}


def test_focus_set_resolves_quote_bumps_seq_and_reads_back(srv):
    status, rec = post(srv, "/focus", {"citekey": "Chen2021Sys", "quote": "fixture paper"})
    assert status == 200
    assert rec["citekey"] == "Chen2021Sys" and rec["quote"] == "fixture paper"
    assert rec["seq"] == 1 and rec["loc"]["page"] == 0 and len(rec["loc"]["rects"]) >= 1
    assert json.loads(get(srv, "/focus")[2]) == rec        # GET returns the same record
    # each set bumps seq — the poll's change-detector
    _, rec2 = post(srv, "/focus", {"citekey": "Chen2021Sys", "quote": "fixture paper"})
    assert rec2["seq"] == 2


def test_focus_unlocated_quote_is_graceful_floor(srv):
    # quote absent from the page → loc null, but the focus still lands (switch paper, no highlight)
    status, rec = post(srv, "/focus", {"citekey": "Chen2021Sys", "quote": "no such words here"})
    assert status == 200 and rec["citekey"] == "Chen2021Sys" and rec["loc"] is None


def test_focus_without_quote_just_opens_the_paper(srv):
    status, rec = post(srv, "/focus", {"citekey": "Chen2021Sys"})
    assert status == 200 and rec["citekey"] == "Chen2021Sys"
    assert rec["quote"] == "" and rec["loc"] is None


def test_focus_rejects_missing_pdf_and_traversal(srv):
    assert post(srv, "/focus", {"citekey": "Nope2020Xyz", "quote": "x"}) == (404, None)
    assert post(srv, "/focus", {"citekey": "../etc", "quote": "x"})[0] == 404


def test_default_serve_has_no_cockpit(srv):
    # a plain `lit serve` (and every static build) must not carry the curate-mode payload
    assert "cockpit" not in json.loads(get(srv, "/graph.json")[2])


def test_curate_mode_injects_cockpit_term_port(repo):
    s = make_server(repo, repo / "pdfs", curate=True, term_port=7690)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        assert json.loads(get(s, "/graph.json")[2])["cockpit"] == {"term_port": 7690}
    finally:
        s.shutdown()
        s.server_close()


def test_spawn_ttyd_argv_binds_loopback_and_passes_env(repo, monkeypatch):
    # offline: no real ttyd — assert we'd launch it loopback-bound, writable, with the wrapper and
    # the three roots the wrapper needs (data root for lit, code root for CURATION.md)
    from litgraph import serve as sm
    cap = {}

    class FakePopen:
        def __init__(self, argv, env=None, **kw):
            cap["argv"], cap["env"] = argv, env
    monkeypatch.setattr(sm.shutil, "which", lambda _: "/usr/bin/ttyd")
    monkeypatch.setattr(sm.subprocess, "Popen", FakePopen)
    assert sm._spawn_ttyd(7690, repo) is not None
    argv = cap["argv"]
    assert argv[0] == "/usr/bin/ttyd"
    assert argv[argv.index("-i") + 1] == "127.0.0.1"        # never 0.0.0.0
    assert argv[argv.index("-p") + 1] == "7690"
    assert "-W" in argv and "--url-arg" in argv             # writable + ?arg=<citekey>
    assert argv[-1].endswith("curate_session.sh")
    assert cap["env"]["LIT_DATA_ROOT"] == str(repo.resolve())
    assert cap["env"]["LIT_SESSIONS"].endswith(".sessions") and cap["env"]["LIT_DOCS"]


def test_spawn_ttyd_missing_is_graceful(monkeypatch, capsys):
    from litgraph import serve as sm
    monkeypatch.setattr(sm.shutil, "which", lambda _: None)
    assert sm._spawn_ttyd(7690, Path(".")) is None          # no crash — the rest of the cockpit works
    assert "ttyd not found" in capsys.readouterr().out


# ── CLI wiring ───────────────────────────────────────────────────────────────────────────

from litgraph import cli


def test_cli_serve_wires_root_port_and_pdf_dir(repo, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "serve", lambda root, pdf_dir, port, curate, term_port: calls.update(
        root=Path(root), pdf_dir=Path(pdf_dir), port=port, curate=curate, term_port=term_port))
    rc = cli.main(["serve", "--root", str(repo), "--port", "0"])
    assert rc == 0
    # no config.toml + no --pdf-dir -> <root>/pdfs; not curating by default
    assert calls == {"root": repo, "pdf_dir": repo / "pdfs", "port": 0,
                     "curate": False, "term_port": 7682}
    rc = cli.main(["serve", "--root", str(repo), "--pdf-dir", str(repo / "elsewhere")])
    assert rc == 0 and calls["pdf_dir"] == repo / "elsewhere" and calls["port"] == 8000


def test_cli_serve_curate_flag_wires_through(repo, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "serve", lambda root, pdf_dir, port, curate, term_port: calls.update(
        curate=curate, term_port=term_port))
    rc = cli.main(["serve", "--root", str(repo), "--port", "0", "--curate", "--term-port", "7690"])
    assert rc == 0 and calls == {"curate": True, "term_port": 7690}


def test_cli_focus_posts_to_running_server(srv, capsys):
    port = srv.server_address[1]
    rc = cli.main(["focus", "Chen2021Sys", "--quote", "fixture paper", "--port", str(port)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Chen2021Sys" in out and "p.1" in out
    rec = json.loads(get(srv, "/focus")[2])              # the server now holds that focus
    assert rec["citekey"] == "Chen2021Sys" and rec["loc"]["page"] == 0


def test_cli_focus_errors_cleanly_when_no_server(capsys):
    # nothing listening → clean message, nonzero exit (not a traceback)
    rc = cli.main(["focus", "Chen2021Sys", "--port", "1"])
    assert rc == 1
    assert "no lit serve" in capsys.readouterr().err


def test_cli_focus_errors_on_unknown_pdf(srv, capsys):
    port = srv.server_address[1]
    rc = cli.main(["focus", "Nope2020Xyz", "--quote", "x", "--port", str(port)])
    assert rc == 1
    assert "Nope2020Xyz" in capsys.readouterr().err


def test_cli_serve_fails_fast_on_broken_repo(repo, monkeypatch, capsys):
    monkeypatch.setattr(cli, "serve", lambda *a, **k: pytest.fail("must not serve"))
    f = repo / "curated" / "Chen2021Sys.yaml"
    f.write_text(f.read_text().replace("grounded_in:  [m1]", "grounded_in:  [m99]", 1))
    rc = cli.main(["serve", "--root", str(repo)])
    assert rc == 1
    assert "m99" in capsys.readouterr().err
