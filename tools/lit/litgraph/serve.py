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
import unicodedata
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import fitz  # pymupdf — already a hard dependency (litgraph.pdf)

from litgraph import store
from litgraph.build import render_html, to_json_dict
from litgraph.graph import BuildError, build_graph
from litgraph.preview import isolate
from litgraph.quotes import polish_graph

# strictly <citekey>.<ext> — one flat name, no separators, so /pdf/ can't traverse out
_PDF_NAME = re.compile(r"^[A-Za-z0-9]+\.pdf$")
_PNG_NAME = re.compile(r"^[A-Za-z0-9]+\.png$")
_CITEKEY = re.compile(r"^[A-Za-z0-9]+$")
_SLICE_ID = re.compile(r"^[cqm]\d+$")
_PAGE_REQ = re.compile(r"^/page/([A-Za-z0-9]+)/(\d+)\.png$")
_WORDS_REQ = re.compile(r"^/words/([A-Za-z0-9]+)/(\d+)\.json$")
_PAGES_REQ = re.compile(r"^/pages/([A-Za-z0-9]+)\.json$")

_PREVIEW_WIDTH = 552  # px (2x the ~276px tooltip box — crisp on retina, still tiny)
_PAGE_WIDTH = 1600    # px — full-page render for the floating quote window (crisp under zoom)
_MAX_PX = 4_000_000   # cap rasterized pixels (oversized-mediabox guard)
_IMG_CACHE = "max-age=600"  # page/preview PNGs are immutable until the PDF's mtime changes


def _needles(anchor: str) -> list[str]:
    """Search strings for an anchor, longest → shortest, so a precise full-phrase match is
    always preferred over a short ambiguous one. Two robustness moves: a hyphen-seam variant
    (`"long- ranged"` → `"long-ranged"`, undoing a line-break hyphenation the PDF keeps
    glued) and leading-window backoff (the tail of a sentence often line-wraps or column-
    breaks where `search_for` can't follow)."""
    a = re.sub(r"\s+", " ", anchor).strip()
    variants = [a]
    glued = re.sub(r"-\s+", "-", a)
    if glued != a:
        variants.append(glued)
    maxw = max(len(v.split(" ")) for v in variants)
    out: list[str] = []
    seen: set[str] = set()
    for n in [maxw, 16, 12, 10, 8, 6, 5, 4, 3, 2]:
        if n > maxw:
            continue
        for v in variants:
            words = v.split(" ")
            if n > len(words):
                continue
            needle = " ".join(words[:n])
            if needle not in seen:
                seen.add(needle)
                out.append(needle)
    return out


def _norm_search(s: str) -> str:
    """Fold text for the resolver's page prefilter: NFKD (splits ligatures), lowercase, then
    keep only alphanumerics — dropping whitespace, hyphens and punctuation. Deliberately
    *looser* than `search_for` (which ignores case and line breaks), so a page this prunes can
    never be one `search_for` would have matched. A false keep just costs one extra search."""
    s = unicodedata.normalize("NFKD", s).lower()
    return re.sub(r"[^0-9a-z]+", "", s)


def _match_words(page: "fitz.Page", anchor: str) -> list[list[float]]:
    """Locate the *whole* anchor on a page via word geometry and return one rect per line it
    spans (page-point coords). Builds a folded character stream from the page's words (each
    char tagged with its source word), finds the folded anchor as a contiguous substring, then
    unions the bboxes of the covered words per layout line. Folding drops case/space/hyphens/
    punctuation, so a line-wrapped or hyphenated sentence still matches in full — unlike
    `search_for`, which often only matches a leading fragment. Empty if the anchor isn't found
    as one run (e.g. an embedded citation marker splits it)."""
    words = page.get_text("words")  # (x0, y0, x1, y1, text, block, line, word_no)
    if not words:
        return []
    stream, char_word = [], []
    for wi, w in enumerate(words):
        folded = _norm_search(w[4])
        stream.append(folded)
        char_word.extend([wi] * len(folded))
    qn = _norm_search(anchor)
    if not qn:
        return []
    i = "".join(stream).find(qn)
    if i < 0:
        return []
    lines: dict = {}
    for wi in sorted(set(char_word[i:i + len(qn)])):
        x0, y0, x1, y1, _txt, block, line, _wn = words[wi]
        lines.setdefault((block, line), []).append((x0, y0, x1, y1))
    return [[min(b[0] for b in bs), min(b[1] for b in bs),
             max(b[2] for b in bs), max(b[3] for b in bs)] for bs in lines.values()]


def locate_quote(pdf: "Path | str", anchor: str) -> dict | None:
    """Best PDF location of `anchor` as {page, rects} with rects page fractions (0..1). Prefers
    the full-coverage word-geometry match; only if that fails on every page does it fall back to
    the `search_for` needle backoff (which may cover just a leading fragment)."""
    with fitz.open(pdf) as doc:
        pages = list(doc)
        for n, page in enumerate(pages):
            rects = _match_words(page, anchor)
            if rects:
                w, h = page.rect.width, page.rect.height
                return {"page": n, "rects": [[r[0] / w, r[1] / h, r[2] / w, r[3] / h] for r in rects]}
        for needle in _needles(anchor):            # fragment fallback — rare, better than nothing
            for n, page in enumerate(pages):
                hits = page.search_for(needle)
                if hits:
                    w, h = page.rect.width, page.rect.height
                    return {"page": n, "rects": [[r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h] for r in hits]}
    return None


def _search_page(page: "fitz.Page", anchor: str) -> list:
    """`search_for` an anchor on one page with the needle backoff. Returns a list of Rects
    (one per line the phrase spans), empty if nothing hits."""
    for needle in _needles(anchor):
        hits = page.search_for(needle)
        if hits:
            return hits
    return []


def _valid_rects(rects) -> bool:
    """A non-empty list of 4-number boxes, each coordinate a fraction in [0, 1]."""
    if not isinstance(rects, list) or not rects:
        return False
    for r in rects:
        if not (isinstance(r, list) and len(r) == 4):
            return False
        if not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in r):
            return False
    return True


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root: Path, pdf_dir: Path):
        self.root = Path(root)
        self.pdf_dir = Path(pdf_dir)
        self._pages: dict[tuple, tuple[float, bytes]] = {}  # (name, n, width) -> (mtime, png)
        self._words: dict[tuple, tuple[float, list]] = {}   # (name, n) -> (mtime, [word,...])
        self._sizes: dict[str, tuple[float, list]] = {}     # name -> (mtime, [[w,h],...])
        super().__init__(address, _Handler)

    def render_page(self, pdf: Path, n: int, width: int) -> bytes:
        """Page `n` of `pdf` rendered to a `width`-px PNG, cached until the file's mtime
        changes. n=0 + _PREVIEW_WIDTH is the tooltip thumbnail; any page at _PAGE_WIDTH
        feeds the floating quote window."""
        mtime = pdf.stat().st_mtime
        key = (pdf.name, n, width)
        hit = self._pages.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
        with fitz.open(pdf) as doc:
            page = doc[n]
            zoom = width / page.rect.width
            # clamp total pixels so an oversized mediabox (poster/foldout) can't blow up into a
            # multi-second render — cap the raster, the window still zooms into the bitmap
            px = (width) * (page.rect.height * zoom)
            if px > _MAX_PX:
                zoom *= (_MAX_PX / px) ** 0.5
            png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
        self._pages[key] = (mtime, png)
        return png

    def page_sizes(self, pdf: Path) -> list[list[float]]:
        """Per-page point sizes `[[w, h], ...]` — the whole-document manifest the viewer uses to
        lay out (and lazily fill) one stacked page box per page. Cached until the PDF's mtime
        changes."""
        mtime = pdf.stat().st_mtime
        hit = self._sizes.get(pdf.name)
        if hit and hit[0] == mtime:
            return hit[1]
        with fitz.open(pdf) as doc:
            sizes = [[p.rect.width, p.rect.height] for p in doc]
        self._sizes[pdf.name] = (mtime, sizes)
        return sizes

    def page_words(self, pdf: Path, n: int) -> list[dict]:
        """Words of page `n` as page-fraction boxes for the selectable text overlay:
        `[{t, x0,y0,x1,y1, ln}, ...]` in reading order, `ln` a per-line ordinal so the client
        can keep line breaks. Same page.rect normalization as the highlight rects (`_match_words`
        / `resolve_quote`), so the overlay registers on the raster without re-derivation. Cached
        until the PDF's mtime changes."""
        mtime = pdf.stat().st_mtime
        key = (pdf.name, n)
        hit = self._words.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
        with fitz.open(pdf) as doc:
            page = doc[n]                         # IndexError on an out-of-range page → 404 upstream
            w, h = page.rect.width, page.rect.height
            raw = page.get_text("words")          # (x0, y0, x1, y1, text, block, line, word_no)
        out = []
        for x0, y0, x1, y1, t, block, line, _wn in sorted(raw, key=lambda o: (o[5], o[6], o[7])):
            t = "".join(c for c in t if not unicodedata.category(c).startswith("C"))  # strip control/zero-width (e.g. ﻿) from copied text
            if not t.strip():                     # nothing visible left → not a selectable word
                continue
            out.append({"t": t, "x0": x0 / w, "y0": y0 / h, "x1": x1 / w, "y1": y1 / h,
                        "ln": block * 10000 + line})
        self._words[key] = (mtime, out)
        return out

    def preview(self, pdf: Path) -> bytes:
        """First page of `pdf` as a PNG for the tooltip thumbnail."""
        return self.render_page(pdf, 0, _PREVIEW_WIDTH)

    def resolve_quote(self, pdf: Path, anchor: str) -> dict | None:
        """Full-coverage PDF location of `anchor` (module-level `locate_quote`, shared with the
        `lit locate` batch command)."""
        return locate_quote(pdf, anchor)


class _Handler(BaseHTTPRequestHandler):
    server_version = "litserve"

    def _send(self, status: int, ctype: str, body: bytes, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # HTML/JSON are live-rebuilt → never cache; page/preview images are immutable until the
        # PDF changes → let the browser reuse them so reopening a window doesn't refetch/redecode
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _payload_dict(self) -> dict:
        """graph.json as a dict, rebuilt from the repo's YAML on every request (may raise
        BuildError). Quotes are polished against the `.md` full text in pdf_dir (falls back to
        the raw anchor when a paper's `.md` is absent)."""
        graph = build_graph(self.server.root)
        polish_graph(graph, self.server.pdf_dir)
        return to_json_dict(graph)

    def _payload(self) -> str:
        """`_payload_dict` serialized — the graph.json body served at `/` and `/graph.json`."""
        return json.dumps(self._payload_dict(), ensure_ascii=False)

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                body = render_html(self._payload()).encode()
                return self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            if path == "/graph.json":
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  self._payload().encode())
            if path == "/preview.html":
                # one paper's local subgraph in isolation — the exact `lit preview` view
                # (real `isolate()` + the shared template), for reviewing an in-progress paper
                # from the main viewer. `.html` (not `/preview/…`, taken by PNG thumbnails)
                # keeps the base dir at `/` so the isolated page's own live PDF features resolve.
                key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
                full = self._payload_dict()
                if key not in full["papers"]:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no curated paper to preview: {key}\n".encode())
                mini = json.dumps(isolate(full, key), ensure_ascii=False)
                return self._send(HTTPStatus.OK, "text/html; charset=utf-8",
                                  render_html(mini).encode())
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
                return self._send(HTTPStatus.OK, "image/png", png, cache=_IMG_CACHE)
            m = _PAGE_REQ.match(path)
            if m:
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                try:
                    png = self.server.render_page(pdf, int(m.group(2)), _PAGE_WIDTH)
                except Exception:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      b"no such page\n")
                return self._send(HTTPStatus.OK, "image/png", png, cache=_IMG_CACHE)
            m = _PAGES_REQ.match(path)
            if m:
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                try:
                    sizes = self.server.page_sizes(pdf)
                except Exception:
                    return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8",
                                      f"page manifest failed: {m.group(1)}\n".encode())
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(sizes).encode(), cache=_IMG_CACHE)
            m = _WORDS_REQ.match(path)
            if m:
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                try:
                    words = self.server.page_words(pdf, int(m.group(2)))
                except Exception:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      b"no such page\n")
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(words).encode(), cache=_IMG_CACHE)
            return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                              b"not found\n")
        except BuildError as e:
            # a mid-edit repo is a normal state — report, keep serving
            return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8",
                              f"build error: {e}\n".encode())

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/resolve":
                body = self._read_json()
                key, anchor = body.get("citekey", ""), body.get("quote", "")
                pdf = self.server.pdf_dir / (key + ".pdf")
                if not _CITEKEY.match(key) or not pdf.is_file() or not anchor:
                    return self._send(HTTPStatus.NOT_FOUND, "application/json", b"null")
                loc = self.server.resolve_quote(pdf, anchor)
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(loc).encode())
            if path == "/quote_loc":
                body = self._read_json()
                key, sid = body.get("citekey", ""), body.get("slice_id", "")
                page, rects = body.get("page"), body.get("rects")
                if not (_CITEKEY.match(key) and _SLICE_ID.match(sid)
                        and isinstance(page, int) and _valid_rects(rects)):
                    return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                                      b"bad quote_loc payload\n")
                try:
                    store.write_quote_loc(self.server.root, key, sid, page, rects)
                except (FileNotFoundError, KeyError) as e:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"{e}\n".encode())
                return self._send(HTTPStatus.OK, "application/json", b'{"ok":true}')
            return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                              b"not found\n")
        except (ValueError, json.JSONDecodeError):
            return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                              b"bad request\n")

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
