# Maintainability review — `tools/lit` (2026-07-03)

A read-through of the whole `litgraph` package (CLI, graph core, emit/serve layers, sources,
the ELN plugin, and the viewer template) looking for dead code, simplification, bugs, and
architectural leverage. Findings are split into **applied** (already committed on this branch,
all covered by the existing test suite) and **proposed** (bigger moves, left for review — this
repo's own rule is *propose, don't impose*).

The test suite is the safety net throughout: 103 tests pass; the only failures are the 8
`iso4`-dependent cases (`venue` / `ingest`), which fail solely because `iso4` can't build in
this environment, not from any change here.

---

## Applied (this branch)

Small, local, test-covered cleanups. Net **−36 lines**, no behavior change.

| # | File | Change |
|---|------|--------|
| 1 | `serve.py` | **Deleted `_search_page`** — a defined-but-never-called function (the `search_for` needle backoff lives inline in `locate_quote`). |
| 2 | `serve.py` | **Deleted the five `_Server` PDF wrapper methods** (`render_page`, `page_sizes`, `page_words`, `preview`, `resolve_quote`). They were pure pass-throughs to `litgraph.pdfview` / `locate_quote`; the handler now calls those directly. Nothing external consumed the wrappers (the comment claiming "the plugin and tests import them" was stale — they don't). Covered by `test_serve.py`'s `/page`, `/pages`, `/words`, `/preview`, `/resolve` cases. |
| 3 | `serve.py` | **Deleted the `_PREVIEW_WIDTH` / `_PAGE_WIDTH` module aliases** + their stale comment; the one live use now reads `pdfview.PAGE_WIDTH`. |
| 4 | `store.py` | **Removed unused import** `from .citekey import _norm_doi`. |
| 5 | `sources/crossref.py` | **Removed a redundant `import re`** nested inside `_strip_doi` (`re` is already imported at module top). |
| 6 | `model.py` | **Dropped a stray `f` prefix** on a non-interpolated string (`f"# Curated paper skeleton …"`). |
| 7 | `__init__.py` | **Fixed a dead doc path** — the module docstring pointed at `docs/superpowers/specs/…` which doesn't exist; the design doc lives at `tools/lit/docs/2026-06-25-litgraph-ingest-design.md`. |

---

## Proposed — high leverage

### P1. Collapse the two serving layers behind one framework-neutral endpoint core

**The problem.** `serve.py` (`_Handler`, on stdlib `http.server`) and `eln_plugin/…/__init__.py`
(Flask routes) implement the **same ~11 endpoints twice** — same paths, same validation regexes,
same error→status mapping — once in each framework's idiom (~150 lines apiece). The building
blocks (`pdfview`, `build`, `quotes`, `locate_quote`, `store`) are already shared; only the
*routing + validation + status mapping* is duplicated. That's exactly the layer where the two
will silently **drift**: tighten the citekey regex or fix a page-range off-by-one in one file and
forget the other, and the two servers disagree with no test to catch it (the ELN side has no test
coverage in this repo at all).

**The shape (validated with a second opinion).** One module — say `viewer/endpoints.py` — that
imports *neither* framework and owns 100% of the logic:

- Frozen `Request` (method, decoded path, path-params, query, raw body + a `.json()` helper) and
  `Response` (status, content-type, bytes, optional `max_age`) dataclasses.
- A ~15-line `Router` with a `{name:regex}` path-template compiler (no routing dependency). The
  **validation regexes move into the route patterns** — an invalid id or non-numeric page simply
  fails to match and falls through to the shared 404, deleting most of the hand-written guards.
- `dispatch(req)` bakes in the error policy: `HttpError(status, msg)` → that status; any other
  exception → 500 with the error text (the current "mid-edit repo returns the BuildError as a
  500" contract).

Then each server is a thin transport shim:

- **stdlib**: one `_run(method)` that builds a `Request` from `self.path` + body, calls
  `router.dispatch`, and writes `resp` out; `do_GET`/`do_HEAD`/`do_POST` delegate to it.
- **Flask**: a single Blueprint **catch-all** rule (`/viewer/<path:rest>`) that forwards to the
  same `dispatch`. A Blueprint (not `DispatcherMiddleware`) keeps the host app's `before_request`
  hooks wrapping every viewer request.

**Payoff.** ~150 lines of drift-prone duplication → one tested core; every endpoint becomes
**unit-testable with zero sockets** (`router.dispatch(Request("GET", "/page/X/3.png", …))`), so the
offline-deterministic test rule extends to the whole HTTP surface; each adapter needs only a
bytes-in/bytes-out smoke test. Enforce the layering with a one-line test: import `endpoints`,
assert `"flask" not in sys.modules`.

**Watch-outs** (all designable-around): `Response.body: bytes` buffers whole PDFs in memory — fine
for single-user loopback, add a `bytes | Path` escape hatch only if needed; the stdlib adapter must
set `Content-Length` explicitly and `unquote()` the path (the param regexes are what keep `%2F`
from smuggling a separator into `/pdf/`); Flask synthesizes HEAD, stdlib needs an explicit
`do_HEAD`. See P2 for the write-safety point this refactor also lets you fix once.

Scope: a few hundred lines reorganized across `serve.py` + the ELN plugin. Worth it — the endpoint
set is still growing, and the ELN adapter is currently untested.

### P2. Latent write-race + non-atomic YAML write (low severity by design)

`store.write_quote_loc` / `write_quote_locs` do a read → parse → mutate → dump straight onto the
target file, and `_Server` is a `ThreadingHTTPServer`. Two concurrent `POST /quote_loc` for the
same citekey could interleave and lose an update, and a crash mid-`dump` truncates the YAML. In
practice this is **near-impossible** — `lit serve` is explicitly "a loopback convenience for one
curator" clicking in one browser — so this is low priority. If P1 lands, the fix is cheap and lives
in exactly one place: a module-level `threading.Lock` around the read-modify-write, and write via
temp-file + `os.replace` for atomicity.

---

## Proposed — medium leverage

### P3. De-duplicate the viewer's two PDF-window mounts

`template.html` has `mountPage` (single quote page) and `mountDoc` (whole-document scroll) sharing
~40 lines nearly verbatim: the `zoomTo` closure (`H0` vs `H`), the ctrl/⌘-wheel handler, the
pointer-drag **pan** handler, the `.pw-tools` pan/text toggle, the highlight-rect placement loop,
and the transparent selectable-text builder (`ensureTextLayer` vs `buildText`). Extract three
helpers — `wirePanZoom(win, body, view, sizer, stage)`, `addHighlights(target, rects)`,
`buildTextLayer(container, words, W0, H)` — and both mounts shrink to just their layout difference
(one sized stage vs. a stack of lazily-observed page boxes). No behavior change; the risk is that
the viewer has **no automated tests**, so this needs a manual pass in `lit serve`.

### P4. One HTTP-JSON client for OpenAlex + Crossref

`sources/openalex.py` and `sources/crossref.py` carry byte-identical `__init__` and
`_http_get_json` (mailto append, `requests.Session`, 3-try backoff, 404→`{}`, raise on exhaustion)
— differing only in the `RuntimeError` message string. Lift a small `_PoliteJsonClient` base (or a
free `polite_get_json(session, url, mailto, retries)` function) and have both clients use it. ~30
duplicated lines → one. Note this path is `# pragma: no cover` (network), so verify by hand or add
an injected-`get_json` test.

### P5. One DOI-prefix helper

Three near-identical strippers exist: `citekey._norm_doi` (strip + lowercase, for comparison),
`openalex._strip_doi` and `crossref._strip_doi` (strip, preserve case — byte-identical to each
other). Consolidate to a single `doi.strip_prefix()` (case-preserving) with
`normalize = strip_prefix().lower()` layered on top. Small, but removes a "fix it in three places"
trap.

### P6. Centralize the `pdf_dir` default

`cfg.pdf_dir or cfg.root / "pdfs"` is spelled out ~5 times (three in `cli.py`, once in `serve`
wiring, once in the ELN plugin). A `Config.pdf_dir_or_default` property puts that policy in one
place.

---

## Not a problem (considered, left alone)

- **`template.html` at ~1350 lines.** It's a single file *by design* — the `lit build` output must
  be self-contained for `file://` distribution. Splitting the source and re-inlining at build time
  would trade one big readable file for a build step; not worth it yet.
- **`pdf.py` opens documents without a context manager** (`extract_text`/`extract_doi`/
  `extract_title`). Short-lived one-shot CLI calls; not a leak that matters.
- **`normalize_work` defined in both source modules.** Same name, different modules and signatures
  — not a collision, and merging them would couple two independent schemas.
- **The graph core's documented v1 limits** (cross-paper acyclicity, quote integrity as a non-fatal
  flag) are called out in `validate`'s docstring and are intentional scope, not gaps.
