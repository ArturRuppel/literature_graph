# VISUALIZATION — design direction (paper-centric column view)

**Status:** design direction (not yet implemented) · **Date:** 2026-06-25, revised 2026-06-27 ·
companion to [CONCEPT.md](../CONCEPT.md) and [SCHEMA.md](../SCHEMA.md)

How the lean slice graph (CONCEPT: one primitive, the slice, in a container P, wired by three
edges) is *shown* to a human. Reference mockups live in [`mockups/`](mockups/) — open in a
browser:

- [`mockups/litgraph-walk.html`](mockups/litgraph-walk.html) — **the walk** (2026-08-03,
  now in the viewer behind the HUD's `walk` toggle): one focus, one relation, an indented
  tree, no drawn edges. See [the walk design doc](2026-08-03-the-walk-design.md) for why
  the column board below stops scaling at 53 curated papers. The board this doc describes
  is unchanged and still the landing view — the two sit side by side.
- [`mockups/litgraph-columns.html`](mockups/litgraph-columns.html) — the column board this
  doc describes: the paper list and its lazy column expansion.
- [`mockups/litgraph-containers.html`](mockups/litgraph-containers.html) — an earlier
  container sketch (the vertical-generality framing this revision rotates; kept for reference).
- [`mockups/litgraph-lean.html`](mockups/litgraph-lean.html) — the fully drilled-in slice DAG
  (a *destination*, not a default).

> **What changed (2026-06-27).** The first draft put the support skeleton on the **vertical**
> axis (`leads-to` up = generality). This revision **rotates it onto the horizontal axis**:
> `leads-to` flows **left → right** (ground → derived), which for citations is **older → newer**.
> The frontier (the noisy, citation-heavy part) gets the intuitive "history recedes left,
> synthesis accretes right" reading, and the CONCEPT §9 *walk-to-root* becomes a literal walk
> **left**. The vertical axis is freed for *within-paper* structure.

---

## The core principle — one list, lazy columns, drill on demand

The model is **recursively containerized** (a paper is a container of slices; a slice slices
further) and **frontier-shaped** (every curated paper grounds leftward into older work and
generalizes rightward into shared claims). The view mirrors both: **start from a flat list of
papers, and spawn structure only where the human points.** The full graph is never the landing
page — it is *earned by drilling in* (CONCEPT §12).

Two orthogonal motions, one per axis:

- **Horizontal = cross-paper, along `leads-to` (≈ chronology).** Expanding a paper's grounds
  spawns a **column to its left** (older roots); expanding what builds on it spawns a column to
  its **right** (newer restatements / synthesis). Columns are **expansion generations, not
  year-buckets** — chronology falls out because grounding walks toward older papers, so we never
  impose a time grid (just sort within a column by year).
- **Vertical = within-paper.** A paper's claim / question / method slices appear by expanding
  its card **in place**, downward — same year, so never a new column.

## The landing list (the default view)

**All papers in one column**, *fully* collapsed to a curation circle + citekey, **no edges
drawn**. Ranked by **curation maturity** — the authored `pass` field (SCHEMA §4): stubs
(maturity 0) at the bottom, maturity-4 papers at the top, ties broken by year. The list *is*
the curation frontier, sorted by how far we've matured each paper.

### The collapsed card

```
┌──────────────────────────────────────────┐
│ ◕  Chen2021Sys                             │   ← curation circle (left) · citekey, one line
└──────────────────────────────────────────┘
```

- **Curation circle — `pass` made visible.** A single circle in the **top-left**, filled like a
  pie to `pass / 4`: an empty ring is a **stub** (maturity 0), a full disk is a fully-curated
  paper (maturity 4), partials in between (`◔ ◑ ◕`). This is the one place the
  [authored `pass` field](../SCHEMA.md) surfaces — the maturity tier the list ranks on.
- **Fully collapsed body = nothing but the circle and citekey** (one line per paper, curated and
  stub alike). The whole landing column is a scannable frontier; depth is earned by focusing.
- **Focusing a curated paper expands it** to the full card — `type` · `year` · title · byline
  (`corresponding` starred) · top-altitude claims — and fans out its columns (below).
- **Hover → metadata** (and, under `lit serve`, abstract + a PDF preview thumbnail; click to open
  the PDF). **Stubs have no PDF** (uncurated) — their hover shows bib metadata only, and the empty
  circle reads as "nothing to open yet."

## The abstract view — clicking spawns columns

Click a paper and it becomes the **focus**; its connecting papers fan out into new columns, and
**the connecting edges are drawn at the same moment**. A column is *only* created when its edge is
— "no edge, no column."

```
        grounds (older, ←)              FOCUS                 builds-on (newer, →)
   ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
   │  ○○○○ Bench2016       │──▶│ ●●●● Chen2021        │──▶│  throughput-scales-…  │   broad
   │  ○○○○ Patel2017       │──▶│      (focus)          │   │  batching-adds-latency│   "now"
   │  ○○○○ West2015 ⚡      │   └──────────────────────┘   └──────────────────────┘
   └──────────────────────┘
```

- **Symmetric.** Expanding `grounded_in` grows **left** (toward floors/roots); expanding
  `leads_to` / cited-by grows **right** (toward restatements and the broad "what we know" nodes).
  `leads-to` points rightward in both directions, so the axis stays honest: **left = evidence/past,
  right = synthesis/now.**
- **Accumulate, don't replace.** Expanding a second paper in a column pours *its* grounds into the
  **same** next column (it is not a single-path Miller-columns replace). When two siblings ground
  in the **same** paper, the column shows **one card with two incoming edges** — de-duped by
  citekey, never a duplicate.
- **Drill all the way.** Click a paper *in a spawned column* and it spawns its own next generation
  — this recursion **is** the CONCEPT §9 walk-to-root (leftward) and the restatement chain
  (rightward, CONCEPT §6.1).

### Where the atemporal nodes live

Broad slices (`claims/`, `questions/`, `methods/` — the shared `leads_to` targets) have no year.
They sit in a **synthesis band at the right edge** — the one direction generalization points,
keeping "new stuff right" true. A broad claim shows its **emergent evidence meter** in place
(`corroborate` vs `contradict` count, CONCEPT §9) — e.g. `throughput-scales-with-batching` reads
*2 support (Chen `c1` + Kumar `c1` via `leads_to`) / 1 contradict (Chen `c3`)*.

### Lateral edges cross columns

`corroborate` / `contradict` are **not** support (CONCEPT §4) and never part of the left-right
walk. They draw as a **distinct signed style spanning columns** — e.g. Chen2021:c1 ⟷ Rao2018,
or c3 ⟶∤ West2015 — connecting two papers at wherever they already sit.

## Color = emergent property, never a tag (CONCEPT §3)

The viz **computes** every color from structure, never from a field: grounded (chain reaches a
floor) vs borrowed (grounds in a citation); measurement floor vs model (layers on measurements);
question open (no incoming `answers`) vs answered; broad (a `leads_to` target). The only colors
that come from authored data are `type` (a filter chip) and the `pass` circle.

## Levels of detail (the drill-in ladder)

1. **List** — collapsed paper cards, no edges, ranked by `pass`. *(landing page)*
2. **Focus a paper** — its grounds/consequences fan into columns with aggregate edges.
3. **Expand a card** — its claim / question / method slices appear as rows (vertical, in place),
   each in its emergent color; aggregate paper→paper edges **disaggregate** to slice→slice
   (`Bench2016 → m1`, `m1 → c1`).
4. **Slice DAG** — fully drilled, slice-level edges everywhere. This is `litgraph-lean.html` — a
   destination, legible only on a thoroughly curated paper.

## Known gaps / next fidelity steps

- **Edge re-routing on expand.** Aggregate paper→paper edges should disaggregate to precise
  slice edges as cards open — the thing that makes drilling in *informative*.
- **Column auto-layout & edge bundling.** Accumulating siblings will crowd a shared column;
  needs ordering (by year) within a column and bundled, de-duped edges.
- **Citation-wall collapse.** A borrowed claim anchoring a whole wall (CONCEPT §10.4) should
  spawn its left column as a single collapsed "▸ N sources" stack, expandable on demand — the
  borrowed-context wall must stay folded even under "expand all."
- **Sharpening on promotion.** When a stub in a left column is later curated, its incoming edge
  should visibly **sharpen** from `→ P` to `→ a specific slice` (CONCEPT §2 wildcard).
- **Stub PDFs.** Promoting a stub to fetch its PDF is an optional manual convenience (CONCEPT §8),
  surfaced from the hover preview's "no PDF yet" state.
