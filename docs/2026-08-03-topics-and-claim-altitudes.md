# Topics and claim altitudes — two axes, one library

**Status:** design · data layer and viewer both built · **Date:** 2026-08-03
**Companions:** [CONCEPT.md](../CONCEPT.md) · [SCHEMA.md](../SCHEMA.md) ·
[2026-07-19-tags-and-search-design.md](2026-07-19-tags-and-search-design.md)

The library crossed the size where its own top level stopped being readable: 53 curated
papers, 19 broad claims in a flat scroll, and a 92-item `tags` vocabulary. Two different
things were illegible, and they needed two different fixes.

| Illegible thing | The question it fails to answer | Fix |
|---|---|---|
| 19 broad claims in one list | *what is known, and how does it hang together* | more altitude on the **claim ladder** — same `leads-to` edge, no schema change |
| 92 free-form tags | *what papers do I have on X* | a new **topic axis** — keyword containers, outside the graph |

The temptation was to solve both with one mechanism: mint category nodes above the broad
claims and let them serve as headings. This document records why that was rejected.

---

## 1. Why a category cannot be a claim

Every emergent property in the model is defined on things that **assert** something:
grounded-vs-plausible needs a chain that can reach a floor, the evidence meter counts
corroborations *of a proposition*, the walk-to-root terminates on a measurement. A heading
asserts nothing, so a heading placed in the `leads-to` chain is a node where all of that
machinery silently returns garbage — and garbage that *looks* like a reading, which is worse
than an error.

It is also a category error in the edge itself. `leads-to` means "generalizes into". A
claim does not generalize into a subject heading; it is *about* one. Those are different
relations and collapsing them costs the model its only structural guarantee.

**The operative test, and the whole of the rule:**

> A statement that can be **false** is a claim. A heading you cannot disagree with is a topic.

Applied to this library, the claim ladder had two rungs left in it — all seven new nodes in
§2 are contestable propositions with a real null hypothesis behind them. It stops there. The
ceiling is where statements like *"cells respond to force"* start appearing, and the two
apexes sit one rung below it: anything that would parent *both* of them is exactly that
sentence. That is the altitude at which to switch axes, not before and not after.

## 2. What was added to the claim ladder

Seven new broad claims across two rungs, no schema change (a broad claim's `leads_to` into a
broader one was already in SCHEMA §4). 19 broad claims → 26, with **4 roots instead of 19**
and a ladder three deep.

First rung — five heads over the existing claims:

| New head | Children | The null it was written against |
|---|---|---|
| `supracellular-stress-field-sets-behaviour` | 5 | passive continuum transmission + cell-autonomous behaviour |
| `active-stress-generates-tissue-form` | 3 | form imposed externally or by a geometric blueprint |
| `cytoskeletal-architecture-sets-cell-mechanics` | 3 | actomyosin sets force, other networks are inert scaffolding |
| `mechanotransduction-is-a-force-loaded-relay` | 2 | cells infer mechanics from a chemical proxy |
| `mechanical-response-is-context-dependent` | 2 | responses differ in magnitude but not in sign across contexts |

plus the existing `tissue-material-state-is-emergent`, which gained
`cell-shape-encodes-material-state` and `tissue-operates-at-jamming-criticality` beneath it.

Two claims are deliberately **multi-parented** — `division-injects-active-stress` and
`topological-defects-are-force-sources` each ladder into two heads. Nothing is duplicated;
the DAG carries it. `go-or-grow-dichotomy` is left an orphan root, which is a valid resting
state, not a gap to be filled with a head that would not earn its ≥2 children.

### The apex — two, and deliberately not one

Second rung. The five heads sorted themselves by *scale*, so they cap in two places:

| Apex | Children | The null it was written against |
|---|---|---|
| `tissue-behaviour-is-collective-mechanics` | `supracellular-stress-field-sets-behaviour`, `active-stress-generates-tissue-form`, `tissue-material-state-is-emergent` | tissue behaviour is the superposition of cell-autonomous programmes, mechanics a downstream readout rather than a cause |
| `mechanics-and-signalling-share-one-architecture` | `cytoskeletal-architecture-sets-cell-mechanics`, `mechanotransduction-is-a-force-loaded-relay` | mechanics and mechanotransduction ride on separable machinery — an inert load-bearing scaffold on one side, dedicated sensors feeding a chemical cascade on the other |

**They are not joined, and joining them is the mistake to resist.** A rung above both would
have to say something like *"cells respond to force"* — the §1 test rejects it, because
nobody can disagree with it. Two apexes with no common parent is what an honest ceiling
looks like; a single root is an aesthetic preference, not a claim.

The other two roots stay roots. `mechanical-response-is-context-dependent` is methodological
rather than scalar — it cuts across both apexes and belongs under neither — and
`go-or-grow-dichotomy` remains the deliberate orphan.

**The apex meters read `0 / 0`, and that is the healthy state.** No paper takes a direct
stance on either; they are reached only through the ladder. If an apex meter ever starts
filling, papers are asserting it *directly* — which means it was never as high as it looked,
and the ceiling is lower than we drew it.

### The known cost

A head accumulates large in-degree, and its corroborate/contradict meter becomes a count of
corroborations of something near-truistic. Survivable at six heads; it is precisely the
symptom that says the ladder has gone one rung too high. If a head's meter ever starts
reading as noise, that head wanted to be a topic.

## 3. What a topic is

A **container of keywords** — nothing more. Full field spec in SCHEMA §9.

```yaml
title: "Cancer mechanics"
note: "Mechanics read into the malignant cascade..."
broader: [disease-and-development]
keywords: [cancer, invasion, metastasis, glioblastoma, ...]
```

Three properties make it safe to add:

- **Membership is derived.** A paper is in a topic iff one of its `tags` is one of the
  topic's keywords (transitively through `broader`). Nothing is written on the paper; a
  paper never names a topic. `tags` remains exactly the free-form container field the tags
  design specified, and the ban on slice-level tags is untouched.
- **It never enters the graph.** `broader` is confined to `topics/ → topics/`. A topic slug
  in any slice edge is a dangling ref and fails the build. The three-edge core is intact.
- **Keywords are non-exclusive.** `glioblastoma` is in both `cancer` and `nervous-system`;
  `three-dimensional` is in both `model-systems` and `extracellular-matrix`. A topic may
  have several `broader` parents. This axis is a DAG on purpose.

## 4. The topic set as built

Four headings over fourteen keyword containers; all 92 tags filed, no dead keywords, every
one of the 53 papers reachable. Three containers sit under two headings each.

```
methods-and-measurement    force-measurement · perturbation-and-patterning ·
                           model-systems* · modelling-and-simulation
tissue-mechanics           material-state · stress-transmission · collective-migration ·
                           active-matter · extracellular-matrix* · morphogenesis*
cell-machinery             cytoskeleton · adhesion-and-mechanotransduction ·
                           extracellular-matrix*
disease-and-development    cancer · nervous-system · morphogenesis* · model-systems*
                                                              (* = two parents)
```

**The tier-1 headings are navigation, not filters.** `tissue-mechanics` reaches 46 of 53
papers, which is useless as a query and fine as a place to start drilling. The leaf
containers are the filter that actually narrows (10–24 papers each). Worth knowing before
anyone wires a UI that treats the two tiers alike.

## 5. Tooling — `lit topics`

`litgraph/topics.py` holds the axis, deliberately outside `graph.py`. `build_graph` loads and
validates it as a last step that touches nothing above it, so every `lit build` checks the
tree; the emit layer ignores `Graph.topics` entirely.

```
lit topics                 # the tree, with papers reached and keywords owned per node
lit topics <slug>          # the papers one topic reaches, and its keyword closure
lit topics --orphans       # unfiled tags · dead keywords · stranded papers  (--strict for CI)
```

**`--orphans` is the load-bearing one.** The other two are conveniences; this is what stops
the layer rotting as the tag vocabulary grows. Three signals, none of them build errors:

| Signal | Means |
|---|---|
| *unfiled tag* — on a paper, in no topic | the topic layer has fallen behind the tagging |
| *dead keyword* — in a topic, on no paper | a typo, or a tag since renamed |
| *stranded paper* — curated, reached by nothing | untagged, or tagged only in unfiled vocabulary |

Run it after a tagging session. The library is currently clean on all three.

## 6. Rendering — and the lesson it taught

Two things had to be built, and the *first* one was not enough on its own.

**The band tiers by altitude.** `BroadNode.leads_to` was documented in SCHEMA §4 but never
loaded, so the entire broad-to-broad ladder — the new claim rungs *and* the six broad methods
that had been laddering since long before this document — had silently never rendered. With
that fixed the band became columns keyed by `SYNTH + tier`, generality still increasing
rightward, and the two apexes landed at altitude 3 and 2 rather than sharing a rightmost column.

**Altitude alone did not fix the flat list, and this is the part worth remembering.** Tier 0
still held 31 of 42 broad nodes; the leftmost synthesis column was still a 31-item scroll. *A
ladder makes altitude legible, but it does not remove leaves.* The list only got shorter when
the band was **collapsed to its roots** — the 14 nodes nothing ladders out of — with one click
revealing one generation, the same drill idiom the rest of the board already used. 42 → 14 on
the landing view; 26 broad claims → 4.

**The landing column went the same way.** Papers now arrive only when something asks for them:
a broad node's `N papers` chip, or a jump from the search box or the library. The board landed
on 53 curated papers for the same bad reason the band landed on 42 nodes.

### The library view — the other half of the split

Collapsing the papers only works if browsing has somewhere else to live, so it got its own
surface in the same document (a second *file* would duplicate the ~2.3 MB inlined payload and
break the single-file `file://` property). It is a reference-manager list — row per paper, facet
rail, virtualized over the whole ~3.8k-entry bibliography — over the *same* index the find-a-paper
box already built. **The topic axis is its facet rail**, which is where §4 said this axis
belonged: headings group, leaf containers narrow.

> **Browse is where you find; the board is where you reason.** A row click hands off to
> `gotoPaper()`, and that handoff is the seam between the two.

One asymmetry to know: topics reach curated papers only, because `tags` are curated-only and a
topic reaches papers through tags. A stub can never match a topic facet.

## 7. Deliberately not decided

- **Whether claims should carry topics.** They should not, for now. A topic on a broad claim
  is arguable (nothing in the graph could derive it), but it buys nothing the paper-level
  axis does not already deliver, and it reopens a rule that is currently load-bearing.
- **Whether the band should separate kinds.** 8 of the 14 landing nodes are broad *methods*,
  so the first thing the eye meets is instrumentation rather than the claim ladder the collapse
  was built to expose. Splitting claims from methods into their own bands would fix that and
  would also change what the board's horizontal axis means. Not done unilaterally.
