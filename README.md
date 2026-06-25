# literature_graph

A knowledge graph over the scientific literature. You read a paper, and the
**affirmations** and **questions** inside it become curated, linkable nodes — each
welded to its source with an exact quote. Granular, paper-bound claims roll up toward
broad, general ones, so the graph doubles as a living, evidence-backed map of "what is
known" on the topics you care about.

The driving constraint: **curation is the rate limiter.** The system *proposes*; a
human *accepts / edits / rejects*. A half-finished graph is a normal, valid state.

This repo is the **general, reusable part** — the design and the tool. Your actual
library (real papers, real quotes) lives in a *separate, private data repo*; the PDFs
live outside git entirely. Anyone can point the tool at their own data and bootstrap
their own knowledge graph.

## Read these in order

1. **[CONCEPT.md](CONCEPT.md)** — the converged model: 4 node types, 8 edges, the
   curated/stub frontier, the rollup DAG. *What* the graph is and *why* it has this shape.
2. **[SCHEMA.md](SCHEMA.md)** — the on-disk data model: one diffable YAML per curated
   paper, thin files for abstractions, a stub registry. *How* it is written to disk.
3. **[example/](example/)** — a small, fully-resolvable worked library exercising every
   node type and all eight edges. Start here to see real YAML.

## Architecture in one diagram

```
human-supplied PDF ─────────────▶  external dir (outside git, named by config)
                                        │
read + curate, one paper at a time      │
        │                               │
        ▼                               │
YAML source of truth (git) ◀────────────┘   curated/*.yaml · claims/*.yaml
        │                                    questions/*.yaml · stubs.yaml
        │  generator (this tool)
        ▼
   graph.db (SQLite, gitignored build artifact)  ──▶  bibliography + knowledge-graph views
```

The split mirrors a diffable-text-is-truth philosophy: the YAML is versioned and
hand-curated; the SQLite graph is a disposable build artifact rebuilt from it; the
heavy PDFs never enter git. CI can build the views with no reference manager present.

## Status

Design converged; data model drafted. Tool (parser → validator → generator → views)
not yet written — the [SCHEMA](SCHEMA.md) plus [example/](example/) fully specify what
it must conform to.
