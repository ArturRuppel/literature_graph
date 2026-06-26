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

- **citekey = `<Family><Year><Venue>`**, CamelCase, e.g. `Ruppel2023eLife`. This one string
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
  extract the claim/question/method slices — that's the curation step (CURATION.md).

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
