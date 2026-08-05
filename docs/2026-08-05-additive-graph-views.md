# Two additive views — the paper graph and the claim graph

**Status:** design · prototypes not yet built · **Date:** 2026-08-05
**Companions:** [CONCEPT.md](../CONCEPT.md) · [SCHEMA.md](../SCHEMA.md) ·
[2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) ·
[2026-08-03-topics-and-claim-altitudes.md](2026-08-03-topics-and-claim-altitudes.md)

Two new lenses over the *same* authored data, built as standalone prototypes and served
separately before anything is welded into the viewer. **Purely additive**: the board, the walk
and the library are untouched, and neither view writes anything or introduces a field.

The motivating observation is one sentence:

> **The support skeleton — the thing the whole model is built around — has no standing view.**

The band draws containment between broad nodes. `redraw` suppresses edges touching a broad node
unless it is isolated. The walk shows one focus and one relation. So `leads_to` from a
quote-welded claim, through derivation, across papers, down to a measurement floor exists in the
data, is *used* (every emergent colour is read off it), and is never drawn as a landscape.

---

## 0. What both views are not

An earlier version of this idea was an embedding point cloud — claims as points, proximity as
semantic similarity, clustering as generalization. It was rejected for the core, and the reason
is worth recording because it governs both views below:

> **Every relation Litgraph draws is authored, contestable and quote-welded. A cosine similarity
> is none of those.** A proximity you cannot disagree with is not a claim (2026-08-03 §1), and
> rendered in the same visual language as `leads-to` it will be read as one.

Both views below are **projections of authored edges**. Nothing is inferred, everything is
auditable, and no model is in the loop. An embedding layer remains possible later as a *third*,
clearly-distinct thing — most plausibly as a proposer (`lit propose`: merge candidates, missing
`leads_to`, incoherent families) rather than a renderer. Out of scope here.

## 1. The substrate — one file, no coupling

Both prototypes consume **`dist/graph.json`**, the payload `build.emit()` already writes
(3.2 MB against the current library). Nothing else. No Python import, no SQLite, no rebuild
hook, no shared module with the viewer. This is what makes the two buildable in parallel and
throwaway-able independently.

What is in it, and the shapes that matter:

| Key | Count today | Notes |
|---|---|---|
| `papers` | 77 | curated only; carries `pass`, `year`, `type`, `tags`, `slices`, and the four edge lists |
| `stubs` | 5047 | bib metadata only — title/year/type/doi/journal/authors |
| `broad` | 45 | `kind`, `title`, `text`, `meter {s,c}`, `leads_to` |
| `order` | 5124 | the global pass/year ranking |
| `topics` | 18 | keyword closures + curated paper lists |

Per-paper edge lists (each entry names the mediating slice in `via` — **there is no bare
paper→paper edge in the model**, CONCEPT §10.4):

| List | Entry | Total |
|---|---|---|
| `grounds` | `{key, tid, via}` — a `grounded_in` ref at a container; `tid` set iff sharpened | 634 |
| `cons` | `{slug, via}` — a slice's `leads_to` into a broad node | 297 |
| `lateral` | `{key,tid,sign,via}` or `{slug,sign,via}` — `corr` / `contra` | 92 |
| `ans` | `{key,tid,via}` or `{slug,via}` — cross-paper `answers` | — |

Per-slice: `{id, kind, text, color, is_floor, grounded, borrowed, answered, up, gen, quote}`.
822 slices total. **The emergent colours are already computed** (`color`, `grounded`,
`borrowed`, `is_floor`) — a view reads them, it does not re-derive them.

> **Rule for both prototypes: the graph.json path is a required CLI argument with no committed
> default.** The file lives in the private data repo; this repo is public. No absolute path,
> no fallback, no `config.toml` read.

---

## 2. View A — the paper graph (`prototypes/paper-graph/`, port 8001)

ResearchRabbit-shaped: papers as circles, sized and filled, in a force layout. Because the model
has no paper→paper edge, **every edge here is a projection**, and there are two worth drawing.
They answer different questions and should be togglable, not merged.

### A1 · Grounding projection — "what does my library rest on"

Collapse each `grounds` entry to `paper → target`, de-duped per pair. Directed.

Measured on the current library: **424 distinct targets, 357 of them with in-degree 1.** Drawn
naively that is a hairball of leaves around a small core. So:

> **Default to in-degree ≥ 2 (67 targets today), with the threshold on a slider.** The
> singletons are real data, not noise, but they are the frontier's tail and belong behind a
> control rather than in the landing view.

The curated core is thin, and it is worth stating the number at the right level of dedup —
three readings of "how much of my grounding lands on something I have read" that differ by a
factor of four:

| Counting | Value |
|---|---|
| raw `grounds` refs landing on a curated paper (a ref per mediating slice) | 117 of 634 |
| **distinct (source, target) pairs landing on a curated paper** — what the graph draws | **90 of 559** |
| distinct curated papers ever grounded in | 27 of 77 |

**The middle row is the one a graph view means**, since an edge is a pair. The rest points into
the 5047 stubs, and that asymmetry is the view's whole point, not a defect.

### A2 · Co-support projection — "who is working on the same claim"

Two papers are linked when slices in each `leads_to` the same broad node. Undirected, weighted
by the number of broad nodes shared. Derived entirely from `cons`.

Measured: **380 pairs over 53 papers** — mean degree ~14, a hairball at weight 1. **Default to
weight ≥ 2 (144 pairs); weight ≥ 3 is 41.** Same slider idiom as A1.

24 of the 77 curated papers touch no broad node at all and therefore do not appear in A2. They
should be shown as an explicit off-graph tray, not silently dropped — a paper with no rung is a
curation signal (2026-08-03: *order organizes; absence doesn't*).

On top of A2, the **signed layer**: `lateral` is already slice↔slice, so `corr` / `contra`
project to signed paper edges for free. This is the one question no existing surface asks —
the board lists a claim's evidence, it never shows *who is arguing with whom*. Distinct style,
own toggle, drawn over either projection.

### The mark — size and fill are two different variables

Degree is confounded with `pass`: a pass-4 paper has ~11 slices and a pass-1 paper has two, so
degree partly measures *how hard the paper was curated*. Don't hide that — put both in one mark,
reusing the idiom the landing card already has:

> **Size = degree. Fill = the `pass` pie (`○ ◔ ◑ ◕ ●`), empty ring = stub.**

The readout that falls out is the reason to build this view at all:

> **A big empty ring is the next paper to curate** — many curated papers ground in it, nobody
> has read it.

It works today. The top grounding targets are `Park2015NatMater` (9), `Angelini2011Pnas` (9),
`Bi2015NatPhys` (8) — all curated, all full disks, the jamming canon correctly identified as
load-bearing. The top *uncurated* target is `Sadati2013Differentiation` at in-degree 5. That is
the view's first answer, and it is a real one. **Ship-test: the prototype must surface it
without being asked.**

Hover gives title/authors/year/journal; click pins a paper and dims to its neighbourhood; a
paper's citekey is the handoff seam back to the board (`gotoPaper()` equivalent — for now, just
print the citekey where it can be copied).

## 3. View B — the claim graph (`prototypes/claim-graph/`, port 8002)

Slice-centric. **Papers demote to an attribute** — a hull, a badge, a hover — and the nodes are
the 822 slices plus the 45 broad nodes. This is the view that draws the support skeleton.

Edges, all authored, no projection:

- slice `up` → local `grounded_in` (within-paper support);
- slice `gen` → local `leads_to` (within-paper generalization ladder);
- `cons` → slice → broad node;
- `broad.leads_to` → the broad ladder (the 4-tier, 45-node structure the band draws as boxes);
- `grounds` with `tid` set → the **sharpened** cross-paper slice→slice edges;
- `lateral` → signed, drawn distinctly, **never part of the walk** (CONCEPT §9).

Colour is not a design decision — CONCEPT §3 already specifies it and `graph.json` already
carries it: grounded vs plausible, original vs borrowed, floor vs not, question open vs
answered. **Read the fields; invent nothing.**

### Layout: layered, not force

`leads_to` is a DAG with a real depth axis — that is the entire point of the altitude work — and
a spring layout throws it away. Rank nodes by distance-to-floor and lay out left→right, keeping
the board's established orientation:

> **left = evidence/past, right = synthesis/now** (2026-06-27 rotation, still binding).

Floors (`is_floor`) pin to the left edge; broad nodes to the right. A claim whose chain never
reaches a floor has no rank from below — **those are the interesting ones**, and they should be
visibly stranded rather than quietly assigned rank 0.

### What this view is for (flat version)

Not navigation — the board and the walk do that better. It is a **diagnostic of what the library
actually establishes versus what it merely asserts.** The expected first reading is
uncomfortable: a large mass of plausible-but-unfloored claims, clustered somewhere specific. If
the picture is *not* uncomfortable, be suspicious of the rendering before believing the library.

## 3.1 The claim graph goes spherical — generality as radius

**Date:** 2026-08-05, after looking at the flat build. The layered 2D version renders and its
diagnostic holds (48% of claims never reach a floor), **and it is kept** — but it is the wrong
primary. Flat layering spends one axis on altitude and packs the rest arbitrarily; the structure
has two independent authored dimensions and deserves both.

> **A sphere: generality is radius, family is direction, and the apex is the centre.**

| Coordinate | Read from | Note |
|---|---|---|
| **radius** | distance-to-floor (slices) / ladder tier (broad) | apex at r≈0, floors at the surface; small inner radius so the innermost nodes don't collide at a point |
| **direction** | the top-level ancestor of the broad node a slice `leads_to` — one of the band's **16** | Fibonacci-distributed over the sphere, not wedges: family is a solid angle, 2 DOF |
| **within a shell** | force-packed to avoid overlap | **meaningless by construction, and labelled so** |

Shell area grows as r², which matches the data: 3 nodes at the top tier, 112 floors at the
bottom. The one broad node with two top-level ancestors (`vimentin-effect-is-context-dependent`)
sits at the normalized midpoint of its parents' directions.

The **16 top-level entries** are 9 broad methods, 4 broad claims and 3 broad questions. The 4
claims are `tissue-behaviour-is-collective-mechanics` and
`mechanics-and-signalling-share-one-architecture` (the two apexes of 2026-08-03 §2), plus
`mechanical-response-is-context-dependent` and the deliberate orphan `go-or-grow-dichotomy`.
*(An earlier draft of this section said "2 apexes + 4 roots", which reads as six nodes; it is
four, two of which are the apexes.)*

### The inheritance rule is underdetermined — and the finding survives it anyway

"Inherit a family through the local `gen`/`up` ladder" does not pin down a single rule, and the
candidates disagree badly: **291** slices (follow `gen` only), **415** (forward-only along the
`leads_to` direction), **419** (`gen` then `up`), **509** (undirected transitive closure). That
spread is wider than most of the numbers in this document, so no conclusion may rest on it.

The halo conclusion does not, because **the radius constraint binds first**: only 421–429 slices
have a distance-to-floor at all, so the ball is capped near 49% of the 867 nodes before family
direction is even consulted. **The halo is a majority under every inheritance rule.**

### The coordinates are sparse, and that is the finding

| Coverage | Count |
|---|---|
| slices with an **authored** family direction (via `cons`) | 284 of 822 |
| …plus inheritance through the local `gen`/`up` ladder (also authored) | 419 of 822 |
| …plus a paper-level majority vote | 784 — **rejected** |
| slices with a distance-to-floor rank | 429 of 822 (393 unfloored) |

The paper-level fallback is rejected because it would place ~365 slices in a direction nobody
wrote — a guess wearing structure's clothes, which is §0's whole prohibition arriving from a new
angle. So:

> **A slice with no authored coordinate does not get a fabricated one.** It goes in a diffuse
> halo outside the shell, never into a sector it was never assigned to.

The resulting picture is a **structured ball** — claims that ladder into a family and reach a
floor — wrapped in a **haze** of claims that do neither. That is the view's payload: the
unfloored fraction stops being a statistic and becomes the first thing you see. If the haze is
thicker than the ball, that is the honest state of the library.

### Two motions, deliberately different controls

- **Camera distance drives level of detail.** Nodes merge into their nearest *ladder ancestor*
  as they stop resolving: 16 families → 45 broad → 867 nodes → quote text. This is the
  "zoom out and they merge" of the original sketch, with the merge target **authored** rather
  than clustered.
- **Radial position is navigation.** Flying to the centre is flying toward the apexes; "move
  inside" is a real gesture, not a camera trick.

**Occlusion is the cost of a filled ball**, and it is solved rather than apologized for: a
shell-window control showing `r ∈ [a, b]` peels radially. It is the altitude slider and the
see-the-middle fix in one control.

Quantitative readouts (meters, counts) stay in a 2D side panel — perspective and occlusion make
distance and density unreadable in 3D, so the sphere is for structure and navigation only.

Built standalone at `prototypes/claim-sphere/`, port **8003**, three.js vendored locally (no
CDN). Flat version stays on 8002 for comparison.

## 4. How they get built and looked at

Standalone, side by side, nothing welded:

- `prototypes/paper-graph/` and `prototypes/claim-graph/` — disjoint trees, no shared files.
- Each: one static page (vanilla JS + SVG/canvas, no CDN, no build step) plus a ~40-line
  `stdlib`-only static server taking `--graph <path>` and `--port`.
- Ports **8001** and **8002** (`lit serve` holds 8000; 8477–8479, 8766, 5001–5002 are taken by
  other desk services — see `~/agents/desk.md`). Bind `127.0.0.1`.
- No dependency on `litgraph`, no import from it, no change to any file outside the prototype
  tree. Nothing is committed by the implementing agents.

**Welding is a separate decision, deliberately deferred.** If a view earns its place, it becomes
a HUD toggle beside `walk` and its projection moves into the emit layer. If it doesn't, the
directory is deleted and nothing else has to be untangled. That property is the reason for the
separate servers, and it is worth more than the convenience of building in place.

## 5. Deliberately not decided

- **Whether the two paper projections should ever be shown at once.** They are different
  relations over the same nodes and superimposing them makes a node's degree meaningless.
  Toggle for now; revisit only if a real reading wants both.
- **Whether stubs belong in view B.** A stub has no slices, so it can only appear as a wildcard
  terminal. Left out of the first cut; it is the same container-wildcard question the board
  already handles with `landingKeys()`.
- **Whether view B should carry the topic axis.** It is the facet rail's job and 2026-08-03 §7
  already declined to put topics on claims. Not revisited here.
- **The embedding layer.** §0. A proposer, if ever, not a renderer.
