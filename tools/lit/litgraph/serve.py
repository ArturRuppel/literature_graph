# litgraph/serve.py
"""`lit serve`: the viewer over HTTP — live rebuild + PDF preview/open.

`lit build` emits a self-contained file for sharing; serving adds the two things a static
file can't do. (1) Every page load re-reads the data repo's YAML and rebuilds the graph,
so refresh-after-edit is the curation loop — an edit that breaks validation returns the
BuildError as a 500 (the server survives; fix the YAML and refresh). (2) The curated PDFs
(`<citekey>.pdf` in `pdf_dir`) are exposed as `pdfs.json` (which citekeys have one),
`/pdf/<citekey>.pdf` (the file) and `/preview/<citekey>.png` (its first page rendered
server-side — an <img> previews everywhere, unlike embedding a PDF), which the viewer
tooltip upgrades on: hover previews the paper, click opens it. A loopback convenience
for one curator, not a deployment server."""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import fitz  # pymupdf — already a hard dependency (litgraph.pdf)

from litgraph.build import render_html, to_json_dict
from litgraph.graph import BuildError, build_graph
from litgraph.quotes import polish_graph

# strictly <citekey>.<ext> — one flat name, no separators, so /pdf/ can't traverse out
_PDF_NAME = re.compile(r"^[A-Za-z0-9]+\.pdf$")
_PNG_NAME = re.compile(r"^[A-Za-z0-9]+\.png$")

_PREVIEW_WIDTH = 552  # px (2x the ~276px tooltip box — crisp on retina, still tiny)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root: Path, pdf_dir: Path):
        self.root = Path(root)
        self.pdf_dir = Path(pdf_dir)
        self._previews: dict[str, tuple[float, bytes]] = {}  # name -> (pdf mtime, png)
        super().__init__(address, _Handler)

    def preview(self, pdf: Path) -> bytes:
        """First page of `pdf` as a PNG, cached until the file's mtime changes."""
        mtime = pdf.stat().st_mtime
        hit = self._previews.get(pdf.name)
        if hit and hit[0] == mtime:
            return hit[1]
        with fitz.open(pdf) as doc:
            page = doc[0]
            png = page.get_pixmap(matrix=fitz.Matrix(_PREVIEW_WIDTH / page.rect.width,
                                                     _PREVIEW_WIDTH / page.rect.width)
                                  ).tobytes("png")
        self._previews[pdf.name] = (mtime, png)
        return png


class _Handler(BaseHTTPRequestHandler):
    server_version = "litserve"

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")  # live rebuild: never cache
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _payload(self) -> str:
        """graph.json, rebuilt from the repo's YAML on every request (may raise BuildError).
        Quotes are polished against the `.md` full text in pdf_dir (falls back to the raw
        anchor when a paper's `.md` is absent)."""
        graph = build_graph(self.server.root)
        polish_graph(graph, self.server.pdf_dir)
        return json.dumps(to_json_dict(graph), ensure_ascii=False)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                body = render_html(self._payload()).encode()
                return self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            if path == "/graph.json":
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  self._payload().encode())
            if path == "/pdfs.json":
                keys = (sorted(f.stem for f in self.server.pdf_dir.glob("*.pdf"))
                        if self.server.pdf_dir.is_dir() else [])
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(keys).encode())
            if path.startswith("/pdf/"):
                name = path[len("/pdf/"):]
                f = self.server.pdf_dir / name
                if not _PDF_NAME.match(name) or not f.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {name}\n".encode())
                return self._send(HTTPStatus.OK, "application/pdf", f.read_bytes())
            if path.startswith("/preview/"):
                name = path[len("/preview/"):]
                pdf = self.server.pdf_dir / (name[:-4] + ".pdf")
                if not _PNG_NAME.match(name) or not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no preview: {name}\n".encode())
                try:
                    png = self.server.preview(pdf)
                except Exception:
                    return self._send(HTTPStatus.INTERNAL_SERVER_ERROR,
                                      "text/plain; charset=utf-8",
                                      f"preview failed: {name}\n".encode())
                return self._send(HTTPStatus.OK, "image/png", png)
            return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                              b"not found\n")
        except BuildError as e:
            # a mid-edit repo is a normal state — report, keep serving
            return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8",
                              f"build error: {e}\n".encode())

    do_HEAD = do_GET


def make_server(root: Path, pdf_dir: Path, host: str = "127.0.0.1",
                port: int = 0) -> _Server:
    """Bind (port 0 = ephemeral) but don't serve yet — the caller runs serve_forever()."""
    return _Server((host, port), root=root, pdf_dir=pdf_dir)


def serve(root: Path, pdf_dir: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve until interrupted, announcing the URL. Raises OSError if the port is taken."""
    srv = make_server(root, pdf_dir, host=host, port=port)
    bound = srv.server_address
    print(f"serving {Path(root).resolve()} at http://{bound[0]}:{bound[1]}/")
    print(f"PDFs from {Path(pdf_dir).resolve()} — Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
