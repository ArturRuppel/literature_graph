# CLAUDE.md — project context for agents

`literature_graph` is a **knowledge graph over the scientific literature**, built for the
AI-proposes / human-curates rhythm. You (an AI agent) do the heavy lifting — parsing PDFs,
drafting claims, fetching metadata — and a human accepts / edits / rejects. **Curation is
the rate limiter; never flood. A half-finished graph is a normal, valid state.**

## Read these first (in order)

1. [CONCEPT.md](CONCEPT.md) — the model: 4 node types, 8 edges, the curated/stub frontier,
   the rollup DAG. *What* the graph is and *why*.
2. [SCHEMA.md](SCHEMA.md) — the on-disk data model: one diffable YAML per curated paper,
   thin files for abstractions, a stub registry. *How* it's written to disk.
3. [docs/superpowers/specs/](docs/superpowers/specs/) — design specs for each tool. Current:
   `2026-06-25-litgraph-ingest-design.md` (the `lit ingest` CLI).
4. [example/](example/) — a small worked library exercising every node type and edge.

## Mental model (the 30-second version)

- **Nodes:** Paper · Affirmation · Question · Author. Affirmations/Questions are *born
  nested inside* a curated paper, each welded to an exact `quote`.
- **Two tiers, encoded by file presence:** a paper is **curated** iff
  `curated/<citekey>.yaml` exists; otherwise it's a **stub** (an entry in `stubs.yaml`).
  The set of stubs *is* the citation frontier.
- **Generalize, don't merge:** never equate two claims; co-parent them under a broader
  `claims/` node. Paper-specific phrasing and quotes are never destroyed.

## Conventions this repo enforces

- **citekey = `<Family><Year><Venue>`**, CamelCase, e.g. `Ruppel2023eLife`. This one string
  names the PDF, its full-text `.md`, the `curated/<key>.yaml` file, **and** the
  `stubs.yaml` key. Venue is the ISO-4 journal abbreviation (+ an override map for brand
  names like `eLife`).
- **Authors** carry two orthogonal axes: `position` (`first | middle | last`, an authorship
  *tier* — multiple `first`s = co-first/equal-contribution) and an independent
  `corresponding: true` flag. List order = byline order.
- **Source of truth is git-tracked YAML.** The SQLite `graph.db` is a disposable build
  artifact (gitignored). **PDFs and their `.md` full-text live outside git**, in the
  external dir named by `config.toml` (`pdf_dir`). Never commit PDFs or paper full text.

## Tools

- **`lit ingest <pdf>`** — initialize a paper's bibliographic skeleton: writes
  `curated/<citekey>.yaml` (metadata + authors), one deduped `stubs.yaml` entry per
  citation (DOI-anchored via OpenAlex), and an AI-parsable `<citekey>.md` full text beside
  the (renamed) PDF. **Non-interactive**: an agent runs it, then agent + human review the
  written YAML together. Use `--dry-run` to preview without writing/renaming. It does *not*
  extract affirmations/questions — that's the future curation step (CONCEPT §12).

## Working with this project

- Propose, don't impose. Surface a paper's local subgraph for accept/edit/reject; don't
  auto-commit curated judgments.
- Metadata fetches use the OpenAlex/Crossref **polite pool** — always send the `mailto`
  from `config.toml`.
- Dev: Python. Tests are **offline & deterministic** (recorded OpenAlex/Crossref fixtures +
  saved PDF-text snippets) — no live network in the test suite.
