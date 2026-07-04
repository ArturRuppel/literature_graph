# litgraph

A knowledge graph over the scientific literature. You read a paper, and the
claims, questions, and methods inside it become nodes in a graph: each one
welded to the exact sentence in the source that backs it. Granular,
paper-bound claims generalize upward toward broad ones, so the graph doubles as
a living, evidence-backed map of what is known on the topics you care about.

One constraint shapes everything: curation is the rate limiter. The tool
proposes; you accept, edit, or reject. A half-finished graph is a normal, valid
state, not a defect.

This repo is the general, reusable part: the model and the tooling. Your actual
library (real papers, real quotes) lives in a separate, private data repo, and
the PDFs live outside git entirely. Point the tool at your own data and
bootstrap your own graph.

## The model

One primitive, the **slice**, lives inside a container, the **paper**. A slice
is a single assertion welded to an exact `quote`. Slices come in three kinds:

- **Claim**: something the paper asserts.
- **Question**: something the paper asks.
- **Method**: how the paper measured or modeled something. Its quote is
  optional.

A paper *is* its slices, and slices are recursively sliceable: a broad claim can
hold finer ones. Three edges connect them:

- **leads-to**: the support skeleton: grounding, derivation, generalization,
  and citation.
- **answers**: a claim answers a question.
- **corroborate / contradict**: lateral stance between two slices.

Everything else is emergent from that structure, not written by hand: whether a
question is open or answered, whether a claim is original or borrowed, how the
evidence balances. You author the slices and the edges; the properties fall out.

Two tiers, decided by one fact on disk: whether a file exists.

- **Curated**: `curated/<citekey>.yaml` exists, so the paper has been sliced.
- **Stub**: it does not, so the paper is an un-sliced container in `stubs.yaml`.
  The set of stubs *is* the frontier. An edge can target a whole stub paper
  until curation slices it and the target sharpens.

One rule keeps the graph honest: generalize, don't merge. Never equate two
claims. Co-parent them under a broader claim node, so each paper's specific
phrasing and its quote survive.

## Source of truth

The git-tracked YAML is the source of truth: one diffable file per curated
paper, thin files for broad slices, a stub registry. The SQLite `graph.db` is a
disposable build artifact, rebuilt from the YAML and never committed. Curated
PDFs and their extracted full-text live in the data repo, one per paper;
uncurated staging PDFs stay outside git.

```
human-supplied PDF ──────────────▶  staging dir (outside git)
                                         │
read + curate, one paper at a time       │
        │                                │
        ▼                                │
YAML source of truth (git) ◀─────────────┘   curated/*.yaml · claims/*.yaml
        │                                     questions/*.yaml · methods/*.yaml · stubs.yaml
        │  lit build
        ▼
   graph.db (SQLite, gitignored)  ──▶  self-contained HTML graph viewer
```

The split means the graph is versioned and hand-reviewable as text, and CI can
build the viewer with no reference manager present.

One string names everything for a paper: the **citekey**,
`<Family><Year><Venue>` in CamelCase, for example `Chen2021Sys`. It names the
PDF, its full-text `.md`, the `curated/<citekey>.yaml` file, and the
`stubs.yaml` key.

## The tools

Everything runs through the `lit` CLI.

- **`lit ingest <pdf>`**: initialize a paper's bibliographic skeleton. Writes
  `curated/<citekey>.yaml` with metadata and authors, one deduped `stubs.yaml`
  entry per citation (DOI-anchored via OpenAlex), and an AI-readable `.md`
  full-text beside the renamed PDF. It does not extract slices: that is
  curation. Use `--dry-run` to preview without writing.
- **`lit build`**: build the static graph viewer into a self-contained
  `dist/index.html`. Validation fails the build on a dangling reference or a
  citekey collision. This is the shareable artifact.
- **`lit serve`**: the same viewer over loopback HTTP for a curation session.
  The graph rebuilds from the YAML on every refresh, so you edit a file and
  refresh; a broken edit returns the validation error and the server survives.
  Quotes get PDF hover-preview: hovering a claim's weld pops its PDF page with
  the sentence highlighted, and clicking pins a scrollable viewer over the whole
  document.
- **`lit locate`**: resolve every curated quote's place in its PDF and store it
  as `quote_loc` in the YAML. Run once, review the diff, commit.
- **`lit preview <citekey>`**: render one paper's local subgraph in isolation,
  through the same viewer `lit build` ships. Fed a scratch YAML, it renders a
  proposition before it is committed: the curation loop's "show it as it will
  look" step, which also flags any non-verbatim quote.

## Curating a paper

Curation is interactive and discussion-first, never a one-shot file dump. Work
one pass at a time. Explain your reading of the paper at that pass's
granularity in prose, discuss until you and the human agree, then tokenize the
agreed nodes into `curated/<citekey>.yaml`. Realign after every pass before
starting the next, and never tokenize ahead of agreement.

## Read next

The design is documented in the order it is best read:

1. **[CONCEPT.md](CONCEPT.md)**: the model. One primitive, one container, three
   edges, and why it has this shape.
2. **[SCHEMA.md](SCHEMA.md)**: the on-disk data model. One diffable YAML per
   curated paper, thin files for broad slices, the stub registry.
3. **[CURATION.md](CURATION.md)**: the reading protocol. The pass-by-pass sweep
   that turns a paper's full text into its proposed local subgraph.
4. **[example/](example/)**: a small, fully-resolvable worked library exercising
   every slice kind and every edge. Start here to see real YAML.

Design converged and the data model is drafted; the `lit` CLI ingests, locates,
builds, and serves. [CURATION.md](CURATION.md) is where to go next to read your
first paper into the graph.
