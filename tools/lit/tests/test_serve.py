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


# ── CLI wiring ───────────────────────────────────────────────────────────────────────────

from litgraph import cli


def test_cli_serve_wires_root_port_and_pdf_dir(repo, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "serve", lambda root, pdf_dir, port: calls.update(
        root=Path(root), pdf_dir=Path(pdf_dir), port=port))
    rc = cli.main(["serve", "--root", str(repo), "--port", "0"])
    assert rc == 0
    # no config.toml + no --pdf-dir -> <root>/pdfs
    assert calls == {"root": repo, "pdf_dir": repo / "pdfs", "port": 0}
    rc = cli.main(["serve", "--root", str(repo), "--pdf-dir", str(repo / "elsewhere")])
    assert rc == 0 and calls["pdf_dir"] == repo / "elsewhere" and calls["port"] == 8000


def test_cli_serve_fails_fast_on_broken_repo(repo, monkeypatch, capsys):
    monkeypatch.setattr(cli, "serve", lambda *a, **k: pytest.fail("must not serve"))
    f = repo / "curated" / "Chen2021Sys.yaml"
    f.write_text(f.read_text().replace("grounded_in:  [m1]", "grounded_in:  [m99]", 1))
    rc = cli.main(["serve", "--root", str(repo)])
    assert rc == 1
    assert "m99" in capsys.readouterr().err
