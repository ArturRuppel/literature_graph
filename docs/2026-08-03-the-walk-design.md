# THE WALK — one focus, one relation, no drawn edges

**Status:** **shipped in the viewer as a toggle** (2026-08-04); design direction below ·
**Date:** 2026-08-03 · supersedes nothing — the column board of
[2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) is untouched and
remains the landing view.

- **In the viewer:** the `walk` button in the HUD (or the `w` key) swaps the board for the
  walk and back. One or the other, never both — the same full-pane exchange the library
  makes. Reading state on each side survives the toggle.
- **Mockup:** [`mockups/litgraph-walk.html`](mockups/litgraph-walk.html) — standalone,
  synthetic library generated to the measured statistics of the real one. Kept because it
  is the thing you can open next to `litgraph-columns.html` and judge side by side.

---

## 1. The diagnosis — measured, not felt

Taken from the real `dist/graph.json` (53 curated papers, 532 slices, 3766 stubs,
42 broad slices, 18 topics):

| focus | board spawns | board draws |
|---|---|---|
| `Hohmann2022Cellsa` | 57 cards | 88 edges |
| `Ruppel2023eLife` | 51 cards | 71 edges |
| `Tambe2011NatMater` | 50 cards | 71 edges |
| `Ruppel2026NatPhys` | 44 cards | 74 edges |
| **median paper** | **4 cards** | — |

Three things follow.

**The fanout is bimodal, and the cause is curation maturity.** The median paper spawns 4
cards; the papers we actually work on spawn 40–57. The board is tuned for the median and
collapses exactly where the work went. This is not random — `pass` predicts it, because a
matured paper is precisely one that has acquired slices, sources, a ladder and stances.
*The board gets worse as the library gets better.*

**Five relations share one canvas.** `grounds` is a DAG, within-paper support is a tree,
the `leads_to` ladder is a chain, `answers` is bipartite, stance is a signed relation.
Each has a different natural layout. Superimposed, none of them is readable. We are not
looking at a messy graph — we are looking at five graphs on one sheet of paper.

**Stance has no layout home, by design.** The 2026-06-25 doc says `corroborate` /
`contradict` draw "at wherever they already sit." `Guillamat2026Science` has 19.
Those are the strokes that cross the whole board, because they connect cards whose
column positions are unrelated to each other.

Hover-isolation (TODO, landed) is the tell: it exists because the resting state is
already unreadable. It is a transient fix for a persistent problem.

## 2. The move — walk one relation, render it as a tree

**Default view = one focus + one relation, as an indented tree, with no SVG edge layer
at all.** Zero lines means zero crossings, permanently, at any library size.

Same focus as the table above, in the walk (depth 2, sibling cap 7):

| focus | grounds | builds | gen | answers | stance | *board* |
|---|---|---|---|---|---|---|
| `Hohmann2022Cellsa` | 4 | 4 | 15 | 16 | 16 | *58c / 89e* |
| `Ruppel2023eLife` | 4 | 4 | 15 | 8 | 2 | *51c / 71e* |
| `Tambe2011NatMater` | 1 | 4 | 15 | 6 | 0 | *50c / 71e* |
| `Ruppel2026NatPhys` | 1 | 1 | 10 | 9 | 10 | *44c / 74e* |

Every relation, on every hub, stays inside one screen. (Measured against the shipped
viewer, not the mockup — hence the small drift from §1, which predates the `builds` fix
in §3.)

### The four rules

**1 · Every relation you are not walking is a badge, not a line.** Each row carries
`⊣3 ⊢2 ⤴1 ?1 ⚖2`. Clicking a badge draws nothing — it *pivots*: that node becomes the
focus and that relation becomes the walk. Navigation replaces superposition.

**2 · The DAG becomes a tree by repetition.** A node reached twice renders fully once and
elsewhere as a dim `↩ also under <key>` that jumps to the canonical occurrence. This is
already how the within-paper substructure view behaves, and it is the one part of the
current viewer that stays legible at depth.

**3 · Stance gets a ledger, not an arrow.** "What contradicts this" is a different
question from "what grounds this." Answering it with a stroke across a board is why the
board looks the way it does. Instead: the claim at the top, corroborating evidence in the
left column, contradicting in the right, each entry drilling to its quote. An endpoint
resting on a container renders as `▸ not yet sliced` — the CONCEPT §2 wildcard, visible
rather than silently mis-drawn.

**4 · The budget makes mess structurally impossible.** A depth cap and a sibling cap
bound what can render. Beyond them: a chip with a count. The citation wall folds *by
construction*, never by clean-up — and the readout in the HUD states, for every focus,
what the board would have drawn instead.

## 3. What the integration cost, and what it taught

Wiring the walk onto the real emitted JSON (rather than the mockup's own generator) turned
up three things the synthetic data could not have shown:

- **`builds` is not shaped like `grounds`.** In a `builds` record (build.py `_builds`),
  `key` *and* `via` both name the **building** paper — its citekey and its building slice —
  while `tid` names the slice of *this* paper being built on. Reading `via` as ours mints a
  cross-product id belonging to neither paper. It silently resolved to a real-looking node
  whenever the two papers happened to share a slice id, which is often.
- **The broad band has its own internal ladder.** `BROAD[slug].leads_to` climbs broad → broad
  up to the apexes the library is capped at. Index only the paper→broad `cons` edges and the
  four apex claims read as empty nodes — the exact opposite of the truth, since they sit at
  the top of the ladder.
- **A stance endpoint may rest on a container.** `{tid: null}` is the CONCEPT §2 unsharpened
  wildcard, not a miss. The ledger renders it as `▸ not yet sliced` rather than dropping it.

None of these are visible at mockup scale; all three were caught by exercising every node
against every relation on the real library.

## 4. What this does not change

The data model is untouched — no new fields, no authored layout. The walk reads the same
emitted JSON. `grounds` / `builds` / `gen` / `answers` / stance are the relations SCHEMA
already validates, and the emergent colouring rule (CONCEPT §3: colour is computed, never
tagged) carries over unchanged.

**The column board is untouched.** It remains the landing view and keeps every gesture it
had; the walk is a second view beside it, not a replacement, and which one is "default" is
a question to answer after living with both. The PDF dock spans the seam — hovering or
clicking a weld quote in the walk aims it exactly as a slice row does on the board.

## 5. Open questions, for after looking at it

- **`grounds` at paper granularity is nearly empty** (1–4 rows) because only 13
  curated→curated grounding edges exist library-wide; almost everything a paper cites is
  still a stub in one chip. The mockup therefore opens a paper on the **ladder**. Is that
  right, or is the near-empty grounds tab itself the honest signal that paper-level
  grounding is not where the knowledge lives?
- **Two relations at once, ever?** `gen` + `answers` around one claim is tempting. It is
  also exactly how the board started.
- **Where does the topic axis attach** — the rail filters by it today; it may deserve to
  be a walkable relation of its own.
- **Does the repeat marker scale?** On a heavily shared support (a much-cited method) the
  tree could show the same node a dozen times before the reader notices they are repeats.
