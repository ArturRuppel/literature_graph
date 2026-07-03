"""litgraph-eln — the literature graph as a tab in the electronic lab notebook.

The labbook's plugin system (``eln.plugins``) auto-discovers this package through the
``eln.plugins`` entry point and mounts one nav link plus a handful of Flask routes under
``/litgraph/``. Those routes are a faithful port of ``litgraph.serve`` (the ``lit serve``
loopback viewer): the graph is rebuilt from the litgraph data repo's YAML on every page
load, and the curated PDFs get the same hover-preview / click-to-open upgrade — all served
by the labbook's own process, reading from the litgraph *data* repo (not the labbook's).

Why routes rather than a generated ``*.html`` page: the labbook splices PWA + edit-overlay
snippets into every ``.html`` page it serves (``eln/server/app.py``), which we must not do
to litgraph's self-contained viewer. A route returns the viewer HTML verbatim. And because
the viewer fetches its PDF endpoints with *relative* URLs (``pdfs.json``, ``pdf/<key>.pdf``,
``preview/<key>.png``), the viewer must live at a URL ending in ``/`` — hence ``/litgraph/``
— so those resolve to ``/litgraph/pdfs.json`` etc.

The litgraph data repo is located via the ``LITGRAPH_ROOT`` env var, falling back to
``~/Projects/literature_graph_database``. Its ``config.toml`` (if present) supplies the PDF
directory, exactly as the ``lit`` CLI resolves it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from eln.plugins import NavLink, Plugin

# litgraph's own building blocks — reused verbatim so this viewer can never drift from
# what `lit build` / `lit serve` ship.
from litgraph.build import render_html, to_json_dict
from litgraph.config import load_config
from litgraph.graph import BuildError, build_graph
from litgraph.quotes import polish_graph
from litgraph.serve import _PDF_NAME, _PNG_NAME, _PREVIEW_WIDTH

_DEFAULT_ROOT = "~/Projects/literature_graph_database"


def _resolve_paths():
    """(root, pdf_dir) for the litgraph data repo, from ``LITGRAPH_ROOT`` (or the default).

    ``load_config`` reads ``<root>/config.toml`` when present and otherwise falls back to the
    root itself; ``pdf_dir`` mirrors the ``lit build``/``lit serve`` default of ``<root>/pdfs``.
    Resolved per request so a root that appears (or moves) after startup is picked up on the
    next refresh — the same edit-then-refresh rhythm as the live YAML rebuild.
    """
    raw = os.environ.get("LITGRAPH_ROOT", _DEFAULT_ROOT)
    cfg = load_config(Path(raw).expanduser())
    pdf_dir = cfg.pdf_dir or cfg.root / "pdfs"
    return cfg.root, pdf_dir


def _payload(root: Path, pdf_dir: Path) -> str:
    """graph.json rebuilt from the repo's YAML, quotes polished against the ``.md`` full text.

    Mirrors ``litgraph.serve._Handler._payload``. May raise ``BuildError`` on a mid-edit repo.
    """
    graph = build_graph(root)
    polish_graph(graph, pdf_dir)
    return json.dumps(to_json_dict(graph), ensure_ascii=False)


# First-page PNG previews, cached by (path, mtime) — a plain port of
# litgraph.serve._Server.preview, kept here so the plugin owns no socket/server object.
_PREVIEW_CACHE: dict[str, tuple[float, bytes]] = {}


def _preview_png(pdf: Path) -> bytes:
    import fitz  # pymupdf — a litgraph hard dependency, so always importable here

    mtime = pdf.stat().st_mtime
    hit = _PREVIEW_CACHE.get(pdf.name)
    if hit and hit[0] == mtime:
        return hit[1]
    with fitz.open(pdf) as doc:
        page = doc[0]
        scale = _PREVIEW_WIDTH / page.rect.width
        png = page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")
    _PREVIEW_CACHE[pdf.name] = (mtime, png)
    return png


def register_litgraph_routes(app, root) -> None:
    """Register the ``/litgraph/`` viewer routes on the labbook's Flask ``app``.

    ``root`` is the *labbook* data root and is intentionally unused: litgraph reads its own
    repo (see :func:`_resolve_paths`). Every handler is defensive — a missing/broken litgraph
    repo returns a readable 500 and never takes the labbook server down with it.
    """
    from flask import Response

    def _err(msg: str, status: int = 500) -> Response:
        return Response(msg + "\n", status=status, mimetype="text/plain; charset=utf-8")

    # Flask canonicalises the trailing slash: a request to `/litgraph` 308-redirects here, so
    # relative fetches from the viewer resolve under `/litgraph/`.
    @app.route("/litgraph/")
    def litgraph_index():  # noqa: ANN202
        try:
            root_, pdf_dir = _resolve_paths()
            html = render_html(_payload(root_, pdf_dir))
        except BuildError as e:
            return _err(f"build error: {e}")
        except Exception as e:  # noqa: BLE001 — a broken repo/path must not 500 the whole app
            return _err(f"litgraph unavailable: {e}")
        return Response(html, mimetype="text/html; charset=utf-8")

    @app.route("/litgraph/graph.json")
    def litgraph_graph_json():  # noqa: ANN202
        try:
            root_, pdf_dir = _resolve_paths()
            payload = _payload(root_, pdf_dir)
        except BuildError as e:
            return _err(f"build error: {e}")
        except Exception as e:  # noqa: BLE001
            return _err(f"litgraph unavailable: {e}")
        return Response(payload, mimetype="application/json; charset=utf-8")

    @app.route("/litgraph/pdfs.json")
    def litgraph_pdfs_json():  # noqa: ANN202
        try:
            _, pdf_dir = _resolve_paths()
            keys = sorted(f.stem for f in pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else []
        except Exception:  # noqa: BLE001 — no PDFs is a normal, non-fatal state
            keys = []
        return Response(json.dumps(keys), mimetype="application/json; charset=utf-8")

    @app.route("/litgraph/pdf/<name>")
    def litgraph_pdf(name):  # noqa: ANN202
        _, pdf_dir = _resolve_paths()
        f = pdf_dir / name
        if not _PDF_NAME.match(name) or not f.is_file():
            return _err(f"no PDF: {name}", status=404)
        return Response(f.read_bytes(), mimetype="application/pdf")

    @app.route("/litgraph/preview/<name>")
    def litgraph_preview(name):  # noqa: ANN202
        _, pdf_dir = _resolve_paths()
        pdf = pdf_dir / (name[:-4] + ".pdf") if name.endswith(".png") else pdf_dir / name
        if not _PNG_NAME.match(name) or not pdf.is_file():
            return _err(f"no preview: {name}", status=404)
        try:
            png = _preview_png(pdf)
        except Exception:  # noqa: BLE001
            return _err(f"preview failed: {name}")
        return Response(png, mimetype="image/png")


plugin = Plugin(
    name="litgraph",
    nav=NavLink("Literature", "/litgraph/"),  # trailing slash: viewer's relative PDF fetches
    register_routes=register_litgraph_routes,
)
