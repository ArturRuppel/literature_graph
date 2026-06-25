# VISUALIZATION — design direction (recursive container view)

**Status:** design direction (not yet implemented) · **Date:** 2026-06-25 · companion to
[CONCEPT.md](../CONCEPT.md) and [SCHEMA.md](../SCHEMA.md)

How the lean slice graph (CONCEPT: one primitive, the slice, in a container P, wired by three
edges) is *shown* to a human. Captured from a mockup session; the interface itself is future
work (CONCEPT §12). Reference mockups live in [`mockups/`](mockups/) — open in a browser:

- [`mockups/litgraph-containers.html`](mockups/litgraph-containers.html) — **the top level**
  (this doc's target).
- [`mockups/litgraph-lean.html`](mockups/litgraph-lean.html) — **the deep view** (fully
  drilled-in slice DAG; a destination, *not* a default).

Both run on the real converted `Ruppel2023eLife`.

---

## The core principle — recursive containers, progressive disclosure

The model is **recursively containerized** (a paper is a container of slices; a slice can be
sliced further), so the *view* must be too. **Collapse cohesive sub-graphs into container
nodes; nest containers in containers; drill in on demand.**

The full slice-level `leads-to` DAG is the **deep view** — legible only after a paper is
thoroughly curated (and even then it's busy). It is *earned by drilling in*, never the
landing page. (In the mockup we only got the deep Ruppel graph from the abstract because it's
the author's own paper; a normal Pass-0/1 graph is far sparser.)

## The top level (the default)

The paper **P** is drawn as a container — a boundary that is the **hull of its children**, so
it resizes as you expand things. Inside it, the paper's slices are grouped into a handful of
**collapsed** sub-containers; the broad (shared) slices sit **above** P:

```
        [ broad claim ]   [ broad claim ]        [ broad question ]      ← shared, outside P
              ▲                 ▲                        ▲
   ┌───────────────────── P · Ruppel2023eLife ───────────────────────┐
   │   ┌ Findings (grounded) ┐   ┌ Context (borrowed) ┐  ┌ q1 ⊃ q2 ┐  │
   │   └──────────▲──────────┘   └────────────────────┘  └─────────┘  │
   │   ┌ Methods (floors+models) ┐                                    │
   │   └──────────────────────────┘                                   │
   └──────────────────────────────────────────────────────────────────┘
```

For Ruppel the cohesive sub-containers are **Methods**, **Findings** (grounded claims),
**Context** (borrowed claims), and **Questions** (`q1 ⊃ q2`, the open molecular follow-up
nested in the answered route question). Edges at this level are **aggregate** `leads-to`
(solid) and `answers` (dotted): *Methods → Findings → broad*, *Context → broad*, *q1 → broad
question*.

## Reading the picture

- **Vertical axis = generality / derivation.** `leads-to` points **up** (ground → derived):
  method **floors** at the bottom, claims in the middle, **broad claims** at the top. The
  axis *is* the support skeleton.
- **Color = emergent property, never a tag** (CONCEPT §3): grounded (reaches a floor) vs
  borrowed (grounded in a citation); measurement floor vs model (layers); question (answered
  vs open); broad (a `leads-to` target). The viz computes these from structure.
- **Citations stay collapsed** — a claim/method shows a `▸ N sources` chip; expand to spawn
  the stub grounds (hover → abstract). The borrowed `Context` wall is the noisy part and
  should stay collapsed even under "expand all."

## What makes a good container boundary?

**A sub-graph that connects to the rest through only a few `leads-to` edges — a low-bandwidth
cut.** Methods are a clean container because they touch everything else through a single
relation ("grounds the findings"); that narrow interface is what lets them collapse to one
node without losing legibility. Candidate rule for *auto*-finding containers later: find
low-cut partitions of the `leads-to` DAG. The human can always draw/override a boundary by
hand. (Some boundaries are semantic nestings rather than cuts — e.g. `q2` inside `q1` — and
those are authored, not inferred.)

## Levels of detail (the drill-in ladder)

1. **Collapsed P** — sub-containers as single nodes, aggregate edges. *(landing page)*
2. **Expand a container** — its slices appear as rows, keeping their emergent color.
3. **Slice DAG** — fully expanded with **slice-level** edges re-routed (e.g. `methods →
   findings` becomes `m1 → c1`, `m3 → c1`, `m5 → c1`). This is `litgraph-lean.html`.

## Known gaps / next fidelity steps

- **Edge re-routing on expand.** Aggregate container edges should disaggregate to the precise
  slice edges as containers open — the thing that makes drilling in *informative*. Not yet
  done in the mockup.
- **Auto-layout.** Both mockups use hand-tiered positions; a real layered-DAG (or
  constraint/force) layout is needed once there is more than one paper.
- **Cross-paper view.** With a second curated paper, two container-P boxes share the broad
  slices above them, and a borrowed claim's citation **sharpens** from `→ P-stub` to `→ a
  specific slice` once the cited paper is curated (CONCEPT §2 wildcard). The container view
  should show that sharpening.
- **Container boundary auto-detection** (the low-cut rule above) — currently hand-picked.
