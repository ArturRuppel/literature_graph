# tests/test_serve.py
"""`lit serve` — loopback only: every request hits 127.0.0.1, no external network."""
import gzip
import http.client
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

import fitz
import pytest

from litgraph import pdfview
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


def get(srv, path, method="GET", headers=None):
    """Raw request (no client-side path normalization — traversal reaches the server)."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    conn.request(method, path, headers=headers or {})
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


def test_pwa_manifest_and_phone_icons_are_served(srv):
    status, headers, body = get(srv, "/manifest.webmanifest")
    assert status == 200
    assert headers["Content-Type"] == "application/manifest+json"
    manifest = json.loads(body)
    assert manifest["display"] == "standalone" and manifest["start_url"] == "./"
    for name in ("icon-192.png", "icon-512.png", "apple-touch-icon.png"):
        status, headers, body = get(srv, f"/{name}")
        assert status == 200 and headers["Content-Type"] == "image/png"
        assert body.startswith(b"\x89PNG\r\n\x1a\n")


def test_curation_opens_three_surfaces_in_one_click_without_two_popups(srv):
    text = get(srv, "/")[2].decode()
    # The PDF consumes the click's one popup allowance; the existing graph window becomes the
    # card, and the server launches the terminal. Thus all three surfaces still take one click.
    enter = text.split("function enter(k){", 1)[1].split("async function returnToGraph", 1)[0]
    assert enter.count("window.open(") == 1
    assert 'location.assign(cardUrl)' in enter
    assert 'fetch("term"' in enter and "Promise.allSettled([focusRequest, termRequest])" in enter


def test_phone_curation_keeps_card_and_pdf_in_one_window_without_terminal(srv):
    text = get(srv, "/")[2].decode()
    phone_branch = text.split("function enter(k){", 1)[1].split(
        "const pdf = window.open", 1)[0]
    assert "if (PHONE_LAUNCH)" in phone_branch
    assert 'mobile: "1"' in phone_branch and "location.assign(" in phone_branch
    assert "window.open(" not in phone_branch
    assert 'fetch("term"' in phone_branch and "attach: false" in phone_branch
    # the card + PDF share one window, split on that window's long axis — the same layout the
    # browse view gets, not a phone-only special case (which is what this used to assert)
    assert "@media (orientation:portrait){" in text
    assert "body.dock-open #board{right:0;bottom:var(--dock-h)}" in text
    assert "open.add(`0:${key}`); loadDock(key); rebuild()" in text
    assert "aimDock(key, row.dataset.sid)" in text


def test_the_pdf_split_follows_the_window_shape_in_every_mode(srv):
    """Landscape docks the PDF on the right, portrait stacks it underneath, and no rule is scoped
    to a mode class — phone curation and the browse view get the identical split."""
    text = get(srv, "/")[2].decode()
    portrait = text.split("@media (orientation:portrait){", 1)[1].split("\n  }", 1)[0]
    for sel in ("#board", "#dockEmpty", ".pw-side", "#dockGrip"):
        assert f"body.dock-open {sel}" in portrait, sel
    assert "mobile-curate" not in portrait
    # each axis keeps its own persisted fraction, so a rotate restores that shape's ratio
    assert "--dock-w:44%;--dock-h:52%" in text
    assert '{w: "lit.dock.w", h: "lit.dock.h"}' in text
    assert 'const ax = portrait() ? "h" : "w";' in text


def test_the_hud_slides_away_on_scroll_without_moving_the_board(srv):
    """The bar is a transform, not a layout change: #board is full-height and pads its own top by
    the measured bar height, so hiding the bar can't reflow the graph or jump the scroll."""
    text = get(srv, "/")[2].decode()
    assert "body.hud-off #hud{transform:translateY(-100%)}" in text
    assert "#board{position:absolute;inset:0;" in text
    assert "padding:calc(var(--hud-h) + 34px)" in text
    assert "body{--hud-h:46px;--hud-top:var(--hud-h)}" in text
    assert "body.hud-off{--hud-top:0px}" in text          # the dock grows into the space too
    assert "top:var(--hud-top)" in text


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


def test_preview_json_isolates_one_curated_paper(srv):
    # the JSON twin of /preview.html: the DRIVE card fetches it to hot-reload its data in place
    status, headers, body = get(srv, "/preview.json?key=Chen2021Sys")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    mini = json.loads(body)
    assert mini["order"] == ["Chen2021Sys"] and "Chen2021Sys" in mini["papers"]


def test_preview_json_rejects_unknown_and_stub_keys(srv):
    assert get(srv, "/preview.json?key=NoSuchPaper2099")[0] == 404
    assert get(srv, "/preview.json?key=Bench2016Tools")[0] == 404


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


def test_text_bodies_are_gzipped_only_when_the_client_asks(srv):
    # the graph page is ~2 MB of HTML-wrapped JSON on every load — the single biggest thing a
    # phone waits for, and it compresses ~4x
    plain = get(srv, "/")
    assert plain[0] == 200 and "Content-Encoding" not in plain[1]
    gz = get(srv, "/", headers={"Accept-Encoding": "gzip, deflate"})
    assert gz[0] == 200 and gz[1]["Content-Encoding"] == "gzip"
    assert gz[1]["Vary"] == "Accept-Encoding"
    assert gzip.decompress(gz[2]) == plain[2]                # same bytes, fewer on the wire
    assert len(gz[2]) < len(plain[2])
    assert int(gz[1]["Content-Length"]) == len(gz[2])        # length describes the encoded body
    # already-compressed bodies are left alone
    img = get(srv, "/page/Chen2021Sys/0.jpg?w=828", headers={"Accept-Encoding": "gzip"})
    assert img[0] == 200 and "Content-Encoding" not in img[1]


def test_page_render_serves_jpeg_at_a_requested_width(srv):
    # the mobile path: the client asks for the width it will actually paint and gets JPEG, which
    # is ~7x smaller than the old full-width PNG for the same page
    status, headers, jpg = get(srv, "/page/Chen2021Sys/0.jpg?w=828")
    assert status == 200 and headers["Content-Type"] == "image/jpeg"
    assert jpg.startswith(b"\xff\xd8\xff")                   # JPEG SOI
    png = get(srv, "/page/Chen2021Sys/0.png")[2]
    assert len(jpg) < len(png)
    assert get(srv, "/page/Chen2021Sys/9.jpg?w=828")[0] == 404
    assert get(srv, "/page/Nope2020Xyz/0.jpg?w=828")[0] == 404


def test_page_width_snaps_to_a_shared_ladder_rung(srv):
    # every phone viewport in a rung shares one render + one cache entry, so the raster cache
    # can't fragment across the arbitrary widths real devices report
    a = get(srv, "/page/Chen2021Sys/0.jpg?w=390")
    b = get(srv, "/page/Chen2021Sys/0.jpg?w=412")
    assert a[2] == b[2] and a[1]["ETag"] == b[1]["ETag"]     # both snap to the 480 rung
    wide = get(srv, "/page/Chen2021Sys/0.jpg?w=1100")
    assert wide[1]["ETag"] != a[1]["ETag"] and len(wide[2]) > len(a[2])
    # an absurd width is clamped to the top rung rather than honoured
    assert get(srv, "/page/Chen2021Sys/0.jpg?w=99999")[1]["ETag"] == \
        get(srv, f"/page/Chen2021Sys/0.jpg?w={pdfview.WIDTHS[-1]}")[1]["ETag"]
    # no ?w= at all (a static build, or a viewer cached before this existed) still works
    assert get(srv, "/page/Chen2021Sys/0.png")[0] == 200


def test_pdf_derived_bodies_revalidate_with_an_etag(srv):
    # a revisit costs one bodiless 304 instead of re-downloading (and re-rendering) the document
    for path in ("/page/Chen2021Sys/0.jpg?w=828", "/words/Chen2021Sys/0.json",
                 "/pages/Chen2021Sys.json", "/preview/Chen2021Sys.png"):
        status, headers, body = get(srv, path)
        assert status == 200 and body, path
        etag = headers["ETag"]
        assert "max-age=86400" in headers["Cache-Control"], path
        s2, h2, b2 = get(srv, path, headers={"If-None-Match": etag})
        assert (s2, b2) == (304, b""), path
        assert h2["ETag"] == etag, path
        # a stale validator still gets the real body
        assert get(srv, path, headers={"If-None-Match": '"stale"'})[0] == 200, path


def test_etag_changes_when_the_pdf_does(srv, repo):
    before = get(srv, "/page/Chen2021Sys/0.jpg?w=828")[1]["ETag"]
    with fitz.open() as doc:                                 # a different one-page PDF
        doc.new_page().insert_text((72, 100), "revised paper")
        (repo / "pdfs" / "Chen2021Sys.pdf").write_bytes(doc.tobytes())
    after = get(srv, "/page/Chen2021Sys/0.jpg?w=828")
    assert after[1]["ETag"] != before                        # re-ingest invalidates immediately
    assert get(srv, "/page/Chen2021Sys/0.jpg?w=828",
               headers={"If-None-Match": before})[0] == 200  # the old validator no longer matches


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
    rec = json.loads(body)
    assert rec.pop("data_version") >= 0        # rides along on the poll for the card hot-reload
    assert rec == {"seq": 0, "citekey": None, "quote": None, "loc": None}


def test_focus_set_resolves_quote_bumps_seq_and_reads_back(srv):
    status, rec = post(srv, "/focus", {"citekey": "Chen2021Sys", "quote": "fixture paper"})
    assert status == 200
    assert rec["citekey"] == "Chen2021Sys" and rec["quote"] == "fixture paper"
    assert rec["seq"] == 1 and rec["loc"]["page"] == 0 and len(rec["loc"]["rects"]) >= 1
    got = json.loads(get(srv, "/focus")[2])
    assert got.pop("data_version") >= 0                     # GET adds the reload version;
    assert got == rec                                      # the focus record itself is unchanged
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


def test_data_version_bumps_on_curated_edit(srv):
    # the card hot-reload signal: editing a curated YAML must raise data_version so the
    # viewer's focus poll can re-render the cockpit card without a manual refresh.
    v0 = json.loads(get(srv, "/focus")[2])["data_version"]
    f = srv.root / "curated" / "Chen2021Sys.yaml"
    os.utime(f, ns=(v0 + 1_000_000_000, v0 + 1_000_000_000))   # push mtime a second ahead of the max
    v1 = json.loads(get(srv, "/focus")[2])["data_version"]
    assert v1 > v0


def test_focus_rejects_missing_pdf_and_traversal(srv):
    assert post(srv, "/focus", {"citekey": "Nope2020Xyz", "quote": "x"}) == (404, None)
    assert post(srv, "/focus", {"citekey": "../etc", "quote": "x"})[0] == 404


# ── the move: POST /active writes the in-progress worklist ────────────────────────────────


def test_active_move_writes_config_and_shows_in_graph(srv, repo):
    from litgraph.config import load_config
    status, res = post(srv, "/active", {"citekey": "Chen2021Sys", "active": True})
    assert status == 200 and res == {"ok": True, "active": ["Chen2021Sys"]}
    # persisted to config.toml (curator state, deployment-local)
    assert load_config(repo).active == ("Chen2021Sys",)
    # and the rebuilt graph.json carries it (re-read per request), so the viewer filters it out
    assert json.loads(get(srv, "/graph.json")[2])["active"] == ["Chen2021Sys"]
    # symmetric removal
    _, res = post(srv, "/active", {"citekey": "Chen2021Sys", "active": False})
    assert res == {"ok": True, "active": []}
    assert load_config(repo).active == ()


def test_active_move_rejects_non_curated_and_bad_payloads(srv, repo):
    # a stub / unknown key has no local subgraph to curate → 404 (curated-only for now)
    assert post(srv, "/active", {"citekey": "Patel2017Vldb", "active": True})[0] == 404
    assert post(srv, "/active", {"citekey": "Nope2099X", "active": True})[0] == 404
    # malformed: missing / non-bool `active`, or a traversal citekey
    assert post(srv, "/active", {"citekey": "Chen2021Sys"})[0] == 400
    assert post(srv, "/active", {"citekey": "Chen2021Sys", "active": "yes"})[0] == 400
    assert post(srv, "/active", {"citekey": "../etc", "active": True})[0] == 400
    # a non-curated key can still be *removed* (idempotent cleanup — no curated-file check)
    assert post(srv, "/active", {"citekey": "Nope2099X", "active": False})[0] == 200


def test_serve_without_terminal_has_no_cockpit(srv):
    # no terminal/Switchboard integration → no cockpit payload; a static build carries none
    assert "cockpit" not in json.loads(get(srv, "/graph.json")[2])


def test_terminal_available_injects_cockpit_name(repo):
    agent = (["/switchboard/python", "-m", "sb.cli"], Path("/switchboard"))
    s = make_server(repo, repo / "pdfs", term_cmd=["/usr/bin/kitty", "-e"],
                    agent_cmd=agent)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        assert json.loads(get(s, "/graph.json")[2])["cockpit"] == {
            "agent": "Switchboard agent", "terminal": "kitty"}
    finally:
        s.shutdown()
        s.server_close()


def test_post_term_uses_switchboard_agent_spawn_then_attaches(repo):
    from litgraph import serve as sm
    cap = {}

    def fake_run(argv, **kw):
        cap["spawn_argv"], cap["spawn_kw"] = argv, kw
        return subprocess.CompletedProcess(argv, 0, "agents-7\n", "")

    class FakePopen:
        def __init__(self, argv, **kw):
            cap["term_argv"], cap["term_kw"] = argv, kw

    agent = (["/switchboard/python", "-m", "sb.cli"], Path("/switchboard"))
    s = make_server(repo, repo / "pdfs", term_cmd=["/usr/bin/kitty", "-e"],
                    agent_cmd=agent)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        real_run, real_popen = sm.subprocess.run, sm.subprocess.Popen
        sm.subprocess.run, sm.subprocess.Popen = fake_run, FakePopen
        try:
            assert post(s, "/term", {"citekey": "Chen2021Sys"})[0] == 200
        finally:
            sm.subprocess.run, sm.subprocess.Popen = real_run, real_popen
    finally:
        s.shutdown()
        s.server_close()
    assert cap["spawn_argv"][:5] == [
        "/switchboard/python", "-m", "sb.cli", "spawn", "agent"]
    assert cap["spawn_argv"][cap["spawn_argv"].index("--cwd") + 1] == str(repo.resolve())
    prompt = cap["spawn_argv"][cap["spawn_argv"].index("--prompt") + 1]
    assert "Chen2021Sys" in prompt and "CURATION.md" in prompt
    assert "lit focus Chen2021Sys --host 127.0.0.1" in prompt
    assert cap["spawn_kw"]["cwd"] == Path("/switchboard")
    assert cap["term_argv"] == [
        "/usr/bin/kitty", "-e", "tmux", "attach", "-t", "=agents-7"]
    assert cap["term_kw"]["start_new_session"] is True


def test_post_term_can_spawn_agent_detached_without_an_emulator(repo):
    from litgraph import serve as sm
    cap = {}

    def fake_run(argv, **kw):
        cap["spawn_argv"] = argv
        return subprocess.CompletedProcess(argv, 0, "agents-8\n", "")

    agent = (["/switchboard/python", "-m", "sb.cli"], Path("/switchboard"))
    s = make_server(repo, repo / "pdfs", agent_cmd=agent)  # deliberately no emulator
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        real_run, sm.subprocess.run = sm.subprocess.run, fake_run
        try:
            status, result = post(s, "/term", {"citekey": "Chen2021Sys", "attach": False})
        finally:
            sm.subprocess.run = real_run
    finally:
        s.shutdown()
        s.server_close()
    assert status == 200 and result == {"ok": True, "session": "agents-8", "attached": False}
    assert cap["spawn_argv"][:5] == [
        "/switchboard/python", "-m", "sb.cli", "spawn", "agent"]


def test_post_term_rejects_bad_key_and_degrades_without_an_emulator(srv, repo):
    assert post(srv, "/term", {"citekey": "../etc"})[0] == 400
    assert post(srv, "/term", {"citekey": "Nope2099X"})[0] == 404      # not a curated paper
    assert post(srv, "/term", {"citekey": "Chen2021Sys", "attach": "no"})[0] == 400
    # `srv` has term_cmd=None: a curated paper still 503s rather than crashing — the card and
    # paper windows keep working, you just start the session yourself
    assert post(srv, "/term", {"citekey": "Chen2021Sys"})[0] == 503


def test_terminal_cmd_prefers_a_found_emulator_and_honours_the_override(monkeypatch):
    from litgraph import serve as sm
    monkeypatch.delenv("LIT_TERMINAL", raising=False)
    monkeypatch.setattr(sm.shutil, "which", lambda e: None)
    assert sm.terminal_cmd() is None                        # nothing installed — graceful, not a crash
    monkeypatch.setattr(sm.shutil, "which", lambda e: f"/usr/bin/{e}" if e == "foot" else None)
    assert sm.terminal_cmd() == ["/usr/bin/foot", "-e"]
    monkeypatch.setenv("LIT_TERMINAL", "kitty --class litcurate -e")
    monkeypatch.setattr(sm.shutil, "which", lambda e: f"/usr/bin/{e}")
    assert sm.terminal_cmd() == ["kitty", "--class", "litcurate", "-e"]


def test_switchboard_cmd_degrades_cleanly_and_honours_override(monkeypatch):
    from litgraph import serve as sm
    monkeypatch.setenv("LIT_SWITCHBOARD", "custom-sb")
    monkeypatch.setattr(sm.shutil, "which", lambda e: "/usr/bin/custom-sb" if e == "custom-sb" else None)
    argv, cwd = sm.switchboard_cmd()
    assert argv == ["custom-sb"] and cwd == Path.cwd()
    monkeypatch.setenv("LIT_SWITCHBOARD", "missing-sb")
    assert sm.switchboard_cmd() is None


# ── CLI wiring ───────────────────────────────────────────────────────────────────────────

from litgraph import cli


def test_cli_serve_wires_root_port_and_pdf_dir(repo, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "serve", lambda root, pdf_dir, host, port: calls.update(
        root=Path(root), pdf_dir=Path(pdf_dir), host=host, port=port))
    rc = cli.main(["serve", "--root", str(repo), "--host", "100.64.0.1", "--port", "0"])
    assert rc == 0
    assert calls == {"root": repo, "pdf_dir": repo / "pdfs",
                     "host": "100.64.0.1", "port": 0}
    rc = cli.main(["serve", "--root", str(repo), "--pdf-dir", str(repo / "elsewhere")])
    assert (rc == 0 and calls["pdf_dir"] == repo / "elsewhere"
            and calls["host"] == "127.0.0.1" and calls["port"] == 8000)


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


def test_cli_curate_moves_paper_in_and_out(repo, capsys):
    from litgraph.config import load_config
    rc = cli.main(["curate", "Chen2021Sys", "--root", str(repo)])
    assert rc == 0 and "moved into" in capsys.readouterr().out
    assert load_config(repo).active == ("Chen2021Sys",)
    rc = cli.main(["curate", "Chen2021Sys", "--done", "--root", str(repo)])
    assert rc == 0 and "returned to the graph" in capsys.readouterr().out
    assert load_config(repo).active == ()


def test_cli_curate_rejects_non_curated(repo, capsys):
    rc = cli.main(["curate", "Patel2017Vldb", "--root", str(repo)])   # a stub, not curated
    assert rc == 1 and "not a curated paper" in capsys.readouterr().err


def test_cli_serve_fails_fast_on_broken_repo(repo, monkeypatch, capsys):
    monkeypatch.setattr(cli, "serve", lambda *a, **k: pytest.fail("must not serve"))
    f = repo / "curated" / "Chen2021Sys.yaml"
    f.write_text(f.read_text().replace("grounded_in:  [m1]", "grounded_in:  [m99]", 1))
    rc = cli.main(["serve", "--root", str(repo)])
    assert rc == 1
    assert "m99" in capsys.readouterr().err


# ── stub abstracts: live OpenAlex fetch on hover, memoized, never persisted ────────────────
def test_stub_abstract_fetches_and_caches(srv):
    from litgraph.model import Work

    calls = []

    class FakeOA:
        def fetch_work(self, doi):
            calls.append(doi)
            return Work(doi=doi, title="t", year=2016, type_raw="article",
                        venue_display="V", abstract="A synthesized abstract.")

    srv._oa = FakeOA()   # pre-seed so no real network is touched
    status, _, body = get(srv, "/stub-abstract?key=Bench2016Tools")
    assert status == 200 and json.loads(body) == {"abstract": "A synthesized abstract."}
    get(srv, "/stub-abstract?key=Bench2016Tools")       # second hit served from session cache
    assert calls == ["10.0000/synth.bench2016"]          # fetched exactly once


def test_stub_abstract_bad_key_and_no_match(srv):
    assert get(srv, "/stub-abstract?key=../etc")[0] == 400   # malformed citekey

    class NoneOA:
        def fetch_work(self, doi):
            return None

    srv._oa = NoneOA()
    status, _, body = get(srv, "/stub-abstract?key=Zhao2014Nsdi")
    assert status == 200 and json.loads(body) == {"abstract": None}


# --- the programme index (the HUD's "aims" pill) -----------------------------


def test_aims_json_indexes_the_programme(srv):
    status, headers, body = get(srv, "/aims.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    aims = json.loads(body)
    assert [a["slug"] for a in aims] == ["@adaptive-batching"]
    a = aims[0]
    assert a["title"] == "Adaptive batch-size control"
    # the two signals the pill shows without opening the card
    assert a["assumptions"] == 1 and a["at_risk"] == 1 and a["slices"] == 11


def test_preview_html_serves_an_aim_card(srv):
    status, headers, body = get(srv, "/preview.html?key=@adaptive-batching")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b'"order": ["@adaptive-batching"]' in body
    assert b'"aim": true' in body


def test_preview_json_serves_an_aim_card(srv):
    status, _, body = get(srv, "/preview.json?key=@adaptive-batching")
    assert status == 200
    mini = json.loads(body)
    assert mini["papers"]["@adaptive-batching"]["aim"] is True


def test_preview_rejects_an_unknown_aim(srv):
    assert get(srv, "/preview.html?key=@nope")[0] == 404


def test_graph_json_stays_paper_only(srv):
    """The landing board is untouched by the programme layer — aims live behind the pill."""
    graph = json.loads(get(srv, "/graph.json")[2])
    assert not [k for k in graph["papers"] if k.startswith("@")]
    assert not [k for k in graph["order"] if k.startswith("@")]


def test_the_hud_carries_the_aims_pill(srv):
    body = get(srv, "/")[2]
    assert b'id="aims"' in body and b'id="aimPanel"' in body
    assert b'aims.json' in body
