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
import os
import re
import shutil
import subprocess
import unicodedata
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import fitz  # pymupdf — already a hard dependency (litgraph.pdf)

from litgraph import config, pdfview, store
from litgraph.build import render_html, to_json_dict
from litgraph.config import load_config
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

    def __init__(self, address, root: Path, pdf_dir: Path, terminal: bool = False,
                 term_port: int = 7682):
        self.root = Path(root)
        self.pdf_dir = Path(pdf_dir)
        self.terminal = terminal        # a ttyd is up → the in-progress zone can embed a terminal
        self.term_port = term_port      # port that ttyd runs on (injected into the viewer)
        # the focus channel: the one "what should the PDF pane be aimed at" record, driven by
        # `lit focus` (the agent) or a card click and polled by the viewer. Serve-only, ephemeral
        # — never persisted. `seq` is the poll's change-detector; `loc` is the resolved {page,
        # rects} or None (the graceful floor: switch paper, no highlight).
        self.focus = {"seq": 0, "citekey": None, "quote": None, "loc": None}
        super().__init__(address, _Handler)


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
        the raw anchor when a paper's `.md` is absent). The manual in-progress list
        (`[curation] active` in config.toml) is re-read per request too, so editing it is live —
        no restart — like every other refresh-after-edit in the curation loop."""
        graph = build_graph(self.server.root)
        polish_graph(graph, self.server.pdf_dir)
        # cockpit = "terminal features available" (a ttyd is up), not "the whole window is curate
        # mode": the in-progress zone embeds a per-paper terminal, the browse view stays the graph.
        cockpit = {"term_port": self.server.term_port} if self.server.terminal else None
        return to_json_dict(graph, active=load_config(self.server.root).active, cockpit=cockpit)

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
            if path == "/focus":
                # the focus wire — what the viewer's PDF pane should aim at right now. Set by
                # POST /focus (the `lit focus` CLI or a card click); the viewer polls this.
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(self.server.focus).encode())
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
                    png = pdfview.preview(pdf)
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
                    png = pdfview.render_page(pdf, int(m.group(2)), pdfview.PAGE_WIDTH)
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
                    sizes = pdfview.page_sizes(pdf)
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
                    words = pdfview.page_words(pdf, int(m.group(2)))
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
                loc = locate_quote(pdf, anchor)
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
            if path == "/focus":
                # aim the wire at a quote: resolve its geometry (like /resolve), store it, bump
                # seq. Quote optional — omit to just switch the pane to a paper (loc stays None,
                # the graceful floor). A missing PDF is a 404; an unresolvable quote is not (the
                # focus still lands, sans highlight).
                body = self._read_json()
                key, quote = body.get("citekey", ""), body.get("quote", "") or ""
                pdf = self.server.pdf_dir / (key + ".pdf")
                if not _CITEKEY.match(key) or not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "application/json", b"null")
                loc = locate_quote(pdf, quote) if quote.strip() else None
                self.server.focus = {"seq": self.server.focus["seq"] + 1,
                                     "citekey": key, "quote": quote, "loc": loc}
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(self.server.focus).encode())
            if path == "/active":
                # the move: add/remove a paper from the in-progress worklist (`[curation] active`
                # in config.toml). Curated-only for now — a stub has no local subgraph to curate
                # (stub promotion is a later item). The write is picked up on the next rebuild.
                body = self._read_json()
                key, active = body.get("citekey", ""), body.get("active")
                curated = self.server.root / "curated" / f"{key}.yaml"
                if not _CITEKEY.match(key) or not isinstance(active, bool):
                    return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                                      b"bad active payload\n")
                if active and not curated.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"not a curated paper: {key}\n".encode())
                new_active = config.set_active(self.server.root, key, active)
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps({"ok": True, "active": list(new_active)}).encode())
            return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                              b"not found\n")
        except (ValueError, json.JSONDecodeError):
            return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                              b"bad request\n")

    do_HEAD = do_GET


def make_server(root: Path, pdf_dir: Path, host: str = "127.0.0.1",
                port: int = 0, terminal: bool = False, term_port: int = 7682) -> _Server:
    """Bind (port 0 = ephemeral) but don't serve yet — the caller runs serve_forever()."""
    return _Server((host, port), root=root, pdf_dir=pdf_dir, terminal=terminal, term_port=term_port)


def _spawn_ttyd(term_port: int, data_root: Path) -> "subprocess.Popen | None":
    """Spawn the cockpit's embedded terminal: ttyd on loopback running the seed-or-resume wrapper
    (design §5). Returns the process, or None if ttyd isn't installed — the rest of the cockpit
    still works, the pane just shows a connection error. CURATION.md lives in the code repo while
    curation runs against the data repo (`--root`), so the wrapper gets both via the environment."""
    ttyd = shutil.which("ttyd")
    if not ttyd:
        print("  ⚠ ttyd not found — terminal pane disabled (install ttyd to enable it)")
        return None
    code_root = Path(__file__).resolve().parents[3]     # literature_graph repo (CLAUDE.md, CURATION.md)
    env = {**os.environ, "LIT_SESSIONS": str(code_root / ".sessions"),
           "LIT_DATA_ROOT": str(Path(data_root).resolve()), "LIT_DOCS": str(code_root)}
    wrapper = Path(__file__).parent / "curate_session.sh"
    proc = subprocess.Popen(
        [ttyd, "-i", "127.0.0.1", "-p", str(term_port), "-W", "--url-arg", "bash", str(wrapper)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  terminal pane: ttyd on http://127.0.0.1:{term_port} (per-paper Claude sessions)")
    return proc


def serve(root: Path, pdf_dir: Path, host: str = "127.0.0.1", port: int = 8000,
          term_port: int = 7682) -> None:
    """Serve until interrupted, announcing the URL. Raises OSError if the port is taken. Always
    spawns a loopback ttyd (when installed) so the in-progress zone can embed a per-paper terminal;
    if ttyd is absent the zone still works, just without its terminal pane. ttyd is terminated on
    exit."""
    ttyd_proc = _spawn_ttyd(term_port, root)
    srv = make_server(root, pdf_dir, host=host, port=port,
                      terminal=ttyd_proc is not None, term_port=term_port)
    bound = srv.server_address
    print(f"serving {Path(root).resolve()} at http://{bound[0]}:{bound[1]}/")
    print(f"PDFs from {Path(pdf_dir).resolve()} — Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
        if ttyd_proc:
            ttyd_proc.terminate()
