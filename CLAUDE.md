# CLAUDE.md — project context for agents

`literature_graph` is a **knowledge graph over the scientific literature**, built for the
AI-proposes / human-curates rhythm. You (an AI agent) do the heavy lifting — parsing PDFs,
drafting claims, fetching metadata — and a human accepts / edits / rejects. **Curation is
the rate limiter; never flood. A half-finished graph is a normal, valid state.**

## Read these first (in order)

1. [CONCEPT.md](CONCEPT.md) — the model: **one primitive (the slice) in a container
   (the paper), three edges**, everything else emergent. *What* the graph is and *why*.
2. [SCHEMA.md](SCHEMA.md) — the on-disk data model: one diffable YAML per curated paper,
   thin files for broad slices, a stub registry. *How* it's written to disk.
3. [CURATION.md](CURATION.md) — the reading protocol: the four-pass sweep that turns a
   paper's full text into its proposed local subgraph. *How* a paper is read in.
4. [tools/lit/](tools/lit/) — the `lit` CLI, self-contained (package, tests, spec).
   Design spec: [tools/lit/docs/2026-06-25-litgraph-ingest-design.md](tools/lit/docs/2026-06-25-litgraph-ingest-design.md).
5. [example/](example/) — a small worked library on the lean slice model (SCHEMA v2).
6. [docs/2026-06-25-visualization-design.md](docs/2026-06-25-visualization-design.md) —
   *future* direction for showing the graph: the **recursive container view** (+ reference
   mockups in `docs/mockups/`). Not yet built.

## Mental model (the 30-second version)

- **One primitive — the slice**, inside a **container `P`** (the paper). Three slice kinds:
  **Claim · Question · Method**, each welded to an exact `quote` (methods optional),
  recursively sliceable. A paper *is* its slices.
- **Three edges:** `leads-to` (the support skeleton — grounding · derivation ·
  generalization · citation; authored as `grounded_in` ⟂ `leads_to`), `answers` (claim →
  question), `corroborate` / `contradict` (lateral stance). A **measurement** Method is a
  *floor* where grounding bottoms out; a *model* is a Method that layers on measurements.
- **Everything else is emergent — no node fields:** open/answered, original/borrowed,
  grounded/plausible, evidence balance (CONCEPT §13). Don't author `evidence`/`status`/`role`.
- **Two tiers, by file presence:** *curated* iff `curated/<citekey>.yaml` exists; else a
  **stub** — an un-sliced container in `stubs.yaml`. The set of stubs *is* the frontier; an
  edge targets the container `P` until curation slices it (the wildcard sharpens).
- **Generalize, don't merge:** never equate two claims; co-parent them under a broader
  `claims/` node via `leads_to` (≥2 children). Paper-specific phrasing and quotes survive.

## Conventions this repo enforces

- **citekey = `<Family><Year><Venue>`**, CamelCase, e.g. `Chen2021Sys`. This one string
  names the PDF, its full-text `.md`, the `curated/<key>.yaml` file, **and** the
  `stubs.yaml` key. Venue is the ISO-4 journal abbreviation (+ an override map for brand
  names like `eLife`).
- **Authors** carry two orthogonal axes: `position` (`first | middle | last`, an authorship
  *tier* — multiple `first`s = co-first/equal-contribution) and an independent
  `corresponding: true` flag. List order = byline order.
- **Source of truth is git-tracked YAML.** The SQLite `graph.db` is a disposable build
  artifact (gitignored). **Curated PDFs and their `.md` full-text live in `pdfs/`
  inside the data repo** (`pdf_dir` in `config.toml`), committed one-per-paper.
  Uncurated/staging PDFs live outside git in `~/Literature/`.

## Tools

- **`lit ingest <pdf>`** — initialize a paper's bibliographic skeleton: writes
  `curated/<citekey>.yaml` (metadata + authors), one deduped `stubs.yaml` entry per
  citation (DOI-anchored via OpenAlex), and an AI-parsable `<citekey>.md` full text beside
  the (renamed) PDF. **Non-interactive**: an agent runs it, then agent + human review the
  written YAML together. Use `--dry-run` to preview without writing/renaming. It does *not*
  extract the claim/question/method slices — that's the curation step (CURATION.md). Ingest also
  writes each stub's `authors` + `journal` (the bib OpenAlex already returns per reference), which
  the viewer shows on hover.
- **`lit enrich`** — backfill `authors` + `journal` onto **existing** `stubs.yaml` entries from
  OpenAlex (by DOI), for stubs ingested before those fields existed. One batched query; only fills
  gaps unless `--force`; `--dry-run` reports without writing. Run once, review the diff, commit.
  (Abstracts are *not* stored — `lit serve` fetches a stub's abstract live on hover; SCHEMA §4 Stub.)
- **`lit build`** — build the static graph viewer: reads the data repo's YAML, computes the
  graph + emergent properties (SCHEMA §7), and emits a self-contained `dist/index.html`
  (the paper-centric column view) plus `graph.json`. Open the HTML directly; no server.
  Validation fails the build on a dangling ref or a curated/stub citekey collision (SCHEMA §6).
  The viewer's HUD carries a **paper-finding search box** (title · author · journal · year · tag,
  curated + stubs) — client-side, so it works in the static artifact offline.
- **`lit serve`** — the same viewer over loopback HTTP, for a curation session: the graph is
  rebuilt from the YAML on every refresh (edit → refresh; a broken edit returns the
  validation error and the server survives), and the tooltip gains PDF hover-preview +
  click-to-open for the `<citekey>.pdf` files in `pdf_dir` (config.toml, else `<root>/pdfs`).
  **Two surfaces** (design: `docs/2026-07-09-cockpit-redesign-in-progress-zone.md`):
  - *Browse view* — the graph, plus one **collapsible PDF viewer** docked right, toggled by the
    header's **📄 PDF** pill. Open, hovering a quote-slice aims it at that claim's citation — the
    **whole PDF** as a lazily-rendered scroll of pages, opened on the highlight, with a real
    scrollbar, ⌘/ctrl-wheel zoom, a live page indicator, and a pan / text-select toolbar (drag to
    pan, or select & copy the page's real text via a transparent word overlay). The location comes
    from a stored `quote_loc` (SCHEMA §6) when present, else resolved live.
  - *In-progress zone* — **right-click a curated card → "Curate this paper"** *moves* it out of the
    graph into the **"in progress · N"** worklist (`[curation] active` in config.toml). The pill
    opens a picker; entering a paper opens its **three-pane cockpit**: the isolated subgraph as the
    left card, the focus-wire PDF pane top-right, and that paper's **ttyd terminal** (embedded
    Claude session) bottom-right. **"Return to graph"** finishes it back into the graph. `lit serve`
    spawns the terminal's ttyd when installed (loopback, default port 7682 — **7681 is often a
    system login ttyd**; `--term-port` overrides); absent ttyd, the zone still works sans terminal.
  Serve-only; a static `lit build` keeps the pill/toggle hidden and stays the shareable artifact.
- **`lit curate <citekey>`** / **`lit curate --done <citekey>`** — the same move from the terminal:
  add (or remove) a curated paper to the in-progress worklist. Drives the same `[curation] active`
  that the right-click move and the "in progress" pill share.
- **`lit tag <citekey> [tags…]`** — add / remove / list a curated paper's **`tags`**: free-form
  curator labels (a container filter axis like `type`, SCHEMA §4 — no evidential weight, curated-only).
  Bare `lit tag <citekey>` lists; `--remove` drops the given tag(s). Round-trips the one YAML file
  (comments survive). Tags are searchable in the viewer, and clicking a tag chip on a card searches it.
- **`lit focus <citekey> [--quote "…"]`** — aim a running `lit serve` in-progress zone's PDF pane
  at a quote (my hand during curation): resolves the quote and re-aims the docked pane. The zone's
  left-card quote-clicks drive the same wire, so agent and human stay in one truth.
- **`lit locate`** — resolve every curated quote's place in its PDF (full-coverage word-
  geometry match) and store it as `quote_loc` in the YAML: run once, review the diff, commit.
  `--force` re-resolves quotes that already have a location; `--dry-run` reports without writing.
- **`lit preview <citekey>`** / **`lit preview --scratch <file>`** — render **one paper's**
  local subgraph *in isolation* (its slices + every edge, cross-paper endpoints as stub
  chips / synthesis band) via the same viewer `lit build` ships, so it can't drift. Fed a
  scratch YAML (real `curated/` schema), it renders a **proposition before it's tokenized** —
  the curation loop's "show it as it'll look" step (CURATION.md). Also flags non-verbatim
  quotes at proposition time. Emits a self-contained `dist/preview.html`.

## Curating a paper

When the human asks to **curate a paper**, **read [CURATION.md](CURATION.md) first** and
follow its protocol. Curation is **interactive and discussion-first**, never a one-shot file
dump:

- Work **one pass at a time** (the four passes in CURATION.md).
- Each pass is a loop: **explain your reading** of the paper at that pass's granularity in
  prose → **discuss with the human until you agree** → *only then* **tokenize** (write the
  agreed nodes into `curated/<citekey>.yaml`).
- **Realign after every pass** before starting the next. Never tokenize ahead of agreement.

## Working with this project

- Propose, don't impose. Surface a paper's local subgraph for accept/edit/reject; don't
  auto-commit curated judgments.
- Metadata fetches use the OpenAlex/Crossref **polite pool** — always send the `mailto`
  from `config.toml`.
- Dev: Python. Tests are **offline & deterministic** (recorded OpenAlex/Crossref fixtures +
  saved PDF-text snippets) — no live network in the test suite.
