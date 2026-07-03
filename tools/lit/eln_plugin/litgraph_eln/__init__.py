"""litgraph-eln — the literature graph as a tab in the electronic lab notebook.

The labbook's plugin system (``eln.plugins``) auto-discovers this package through the
``eln.plugins`` entry point and mounts one nav link plus the litgraph viewer's routes under
``/litgraph/``. Those routes are a thin adapter over litgraph's own building blocks — the
graph is rebuilt from the litgraph data repo's YAML on every page load, PDFs render through
the shared :mod:`litgraph.pdfview`, and quotes resolve through the same ``locate_quote`` the
``lit locate`` command uses — all served by the labbook's own process, reading from the
litgraph *data* repo (not the labbook's).

Every HTTP route here mirrors one in :mod:`litgraph.serve`; the rendering/resolving logic is
imported, never re-implemented, so this viewer can't drift from ``lit serve`` / ``lit build``.

Why routes rather than a generated ``*.html`` page: the labbook splices PWA + edit-overlay
snippets into every ``.html`` page it serves (``eln/server/app.py``), which we must not do to
litgraph's self-contained viewer. A route returns the viewer HTML verbatim. And because the
viewer fetches its endpoints with *relative* URLs (``pdfs.json``, ``pdf/<key>.pdf``,
``page/<key>/<n>.png``, ``pages/<key>.json``, ``resolve`` …), the viewer must live at a URL
ending in ``/`` — hence ``/litgraph/`` — so those resolve under ``/litgraph/``.

The litgraph data repo is located via the ``LITGRAPH_ROOT`` env var, falling back to
``~/Projects/literature_graph_database``. Its ``config.toml`` (if present) supplies the PDF
directory, exactly as the ``lit`` CLI resolves it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from eln.plugins import NavLink, Plugin

# litgraph's own building blocks — reused verbatim so this viewer can never drift from what
# `lit build` / `lit serve` ship.
from litgraph import store
from litgraph.build import render_html, to_json_dict
from litgraph.config import load_config
from litgraph.graph import BuildError, build_graph
from litgraph.pdfview import PAGE_WIDTH, page_sizes, page_words, preview, render_page
from litgraph.preview import isolate
from litgraph.quotes import polish_graph
from litgraph.serve import _CITEKEY, _PDF_NAME, _PNG_NAME, _SLICE_ID, _valid_rects, locate_quote

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


def _payload_dict(root: Path, pdf_dir: Path) -> dict:
    """graph.json as a dict, rebuilt from the repo's YAML, quotes polished against the ``.md``
    full text. Mirrors ``litgraph.serve._Handler._payload_dict``; may raise ``BuildError``. The
    manual in-progress list (``[curation] active`` in config.toml) is re-read per request too, so
    editing it is live — the same edit-then-refresh rhythm as the YAML rebuild."""
    graph = build_graph(root)
    polish_graph(graph, pdf_dir)
    return to_json_dict(graph, active=load_config(root).active)


def register_litgraph_routes(app, root) -> None:
    """Register the ``/litgraph/`` viewer routes on the labbook's Flask ``app``.

    ``root`` is the *labbook* data root and is intentionally unused: litgraph reads its own
    repo (see :func:`_resolve_paths`). Every handler is defensive — a missing/broken litgraph
    repo returns a readable error and never takes the labbook server down with it.
    """
    from flask import Response, request

    def _err(msg: str, status: int = 500) -> Response:
        return Response(msg + "\n", status=status, mimetype="text/plain; charset=utf-8")

    def _pdf_for(key: str) -> Path:
        _, pdf_dir = _resolve_paths()
        return pdf_dir / (key + ".pdf")

    # ── the viewer page + its data ──────────────────────────────────────────────────────────
    # Flask canonicalises the trailing slash: a request to `/litgraph` 308-redirects here, so
    # relative fetches from the viewer resolve under `/litgraph/`.
    @app.route("/litgraph/")
    def litgraph_index():  # noqa: ANN202
        try:
            root_, pdf_dir = _resolve_paths()
            html = render_html(json.dumps(_payload_dict(root_, pdf_dir), ensure_ascii=False))
        except BuildError as e:
            return _err(f"build error: {e}")
        except Exception as e:  # noqa: BLE001 — a broken repo/path must not 500 the whole app
            return _err(f"litgraph unavailable: {e}")
        return Response(html, mimetype="text/html; charset=utf-8")

    @app.route("/litgraph/graph.json")
    def litgraph_graph_json():  # noqa: ANN202
        try:
            root_, pdf_dir = _resolve_paths()
            payload = json.dumps(_payload_dict(root_, pdf_dir), ensure_ascii=False)
        except BuildError as e:
            return _err(f"build error: {e}")
        except Exception as e:  # noqa: BLE001
            return _err(f"litgraph unavailable: {e}")
        return Response(payload, mimetype="application/json; charset=utf-8")

    @app.route("/litgraph/preview.html")
    def litgraph_preview_html():  # noqa: ANN202
        # one curated paper's local subgraph in isolation — the in-progress review lens
        key = request.args.get("key", "")
        try:
            root_, pdf_dir = _resolve_paths()
            full = _payload_dict(root_, pdf_dir)
        except BuildError as e:
            return _err(f"build error: {e}")
        except Exception as e:  # noqa: BLE001
            return _err(f"litgraph unavailable: {e}")
        if key not in full["papers"]:
            return _err(f"no curated paper to preview: {key}", status=404)
        mini = json.dumps(isolate(full, key), ensure_ascii=False)
        return Response(render_html(mini), mimetype="text/html; charset=utf-8")

    # ── PDFs: manifest, whole file, first-page thumbnail ────────────────────────────────────
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
            png = preview(pdf)
        except Exception:  # noqa: BLE001
            return _err(f"preview failed: {name}")
        return Response(png, mimetype="image/png")

    # ── the floating quote window: full-page renders, page manifest, text overlay ───────────
    @app.route("/litgraph/page/<key>/<int:n>.png")
    def litgraph_page(key, n):  # noqa: ANN202
        pdf = _pdf_for(key)
        if not _CITEKEY.match(key) or not pdf.is_file():
            return _err(f"no PDF: {key}", status=404)
        try:
            png = render_page(pdf, n, PAGE_WIDTH)
        except Exception:  # noqa: BLE001 — out-of-range page etc.
            return _err("no such page", status=404)
        return Response(png, mimetype="image/png")

    @app.route("/litgraph/pages/<key>.json")
    def litgraph_pages(key):  # noqa: ANN202
        pdf = _pdf_for(key)
        if not _CITEKEY.match(key) or not pdf.is_file():
            return _err(f"no PDF: {key}", status=404)
        try:
            sizes = page_sizes(pdf)
        except Exception:  # noqa: BLE001
            return _err(f"page manifest failed: {key}")
        return Response(json.dumps(sizes), mimetype="application/json; charset=utf-8")

    @app.route("/litgraph/words/<key>/<int:n>.json")
    def litgraph_words(key, n):  # noqa: ANN202
        pdf = _pdf_for(key)
        if not _CITEKEY.match(key) or not pdf.is_file():
            return _err(f"no PDF: {key}", status=404)
        try:
            words = page_words(pdf, n)
        except Exception:  # noqa: BLE001
            return _err("no such page", status=404)
        return Response(json.dumps(words), mimetype="application/json; charset=utf-8")

    # ── quote location: resolve live, persist an anchor back to the YAML ─────────────────────
    @app.route("/litgraph/resolve", methods=["POST"])
    def litgraph_resolve():  # noqa: ANN202
        body = request.get_json(silent=True) or {}
        key, anchor = body.get("citekey", ""), body.get("quote", "")
        pdf = _pdf_for(key)
        if not _CITEKEY.match(key) or not pdf.is_file() or not anchor:
            return Response("null", mimetype="application/json")
        return Response(json.dumps(locate_quote(pdf, anchor)),
                        mimetype="application/json; charset=utf-8")

    @app.route("/litgraph/quote_loc", methods=["POST"])
    def litgraph_quote_loc():  # noqa: ANN202
        root_, _ = _resolve_paths()
        body = request.get_json(silent=True) or {}
        key, sid = body.get("citekey", ""), body.get("slice_id", "")
        page, rects = body.get("page"), body.get("rects")
        if not (_CITEKEY.match(key) and _SLICE_ID.match(sid)
                and isinstance(page, int) and _valid_rects(rects)):
            return _err("bad quote_loc payload", status=400)
        try:
            store.write_quote_loc(root_, key, sid, page, rects)
        except (FileNotFoundError, KeyError) as e:
            return _err(str(e), status=404)
        return Response('{"ok":true}', mimetype="application/json")


plugin = Plugin(
    name="litgraph",
    nav=NavLink("Literature", "/litgraph/"),  # trailing slash: viewer's relative fetches
    register_routes=register_litgraph_routes,
)
