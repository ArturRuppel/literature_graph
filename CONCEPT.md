# Literature — a semantically rich bibliography

**Status:** concept (data model converged; interface is a separate design challenge)
**Date:** 2026-06-25

A knowledge graph over the scientific literature, built *into* an electronic lab
notebook. You read a
paper, and the affirmations and questions inside it become curated, linkable nodes —
each welded to its source with an exact quote. Claims roll up from paper-specific and
granular toward broad and general, so the graph doubles as a living, evidence-backed
map of "what is known" on the topics you care about. Every node is something you could
write in a paper's intro, with the supporting (or contradicting) literature one click
away.

The driving constraint, present in every decision below: **curation is the rate
limiter.** The system's job is to *propose* and let a human *accept / edit / reject* —
never to flood. A half-finished graph is a normal, valid state.

---

## 1. Leverage, don't rebuild — plain text in git is the source of truth

- **PDFs live outside git, in an external dir.** The heavy stuff — the PDFs — sits in a
  plain directory the human owns, named by config (exactly like `sdgl.toml` points at
  `/gaia/...` and `/home/aruppel/Data/`). Never committed; the human supplies them and
  nothing scrapes. *(An earlier draft used Zotero as the backend; it was dropped — too
  much overhead, a sandbox/API to fight, for virtually no gain once the semantic layer
  lives in our own YAML.)*
- **The source of truth is plain-text YAML in git** — one diffable file per curated
  paper, holding its affirmations, questions and edges. This mirrors the repo's
  philosophy (`experiments.sql` is the diffable form of the DB; derived/heavy artifacts
  are gitignored). See [SCHEMA.md](SCHEMA.md) for the on-disk layout.
- **A generator builds a SQLite graph index + the catalog views** from that YAML. The
  binary graph is a disposable build artifact (gitignored, like `experiments.db`). CI
  can build the published views with **no reference manager present** — no live app or
  local API is ever in the loop, so the published view never depends on one.

```
human-supplied PDF ─▶ external PDF dir   [outside git, named by config]
                          │  read + curate, one paper at a time
                          ▼
   per-paper YAML: affirmations / questions + edges   [git-tracked, diffable]  ◀ source of truth
   broader claims / questions (free-floating)         [git-tracked]
                          │  generator
                          ▼
       graph.db (SQLite, gitignored)  ─▶  bibliography + knowledge-graph views   [built by CI]
```

---

## 2. Three layers

| Layer | Members | Nature |
|---|---|---|
| **Sources** | Paper, Author | containers/people that *hold and connect* atoms — not atoms themselves |
| **Atoms** | Affirmation, Question | irreducible, quote-bound content, **born nested inside a curated paper** |
| **Abstractions** | broader claims / topics | free-floating generalizations that own no paper; the rollups |

"Topic" is **not** a separate node type — a topic is just an affirmation at high
altitude. The granular end of the ladder is paper-bound with a quote; the broad end is
the abstraction you'd write in a review's intro. One continuous ladder of generality.

---

## 3. Node types (4)

- **Paper** — carries a `type` (§6) and exists in one of two tiers (§5).
- **Affirmation** — a knowledge atom. Always born nested in *one* curated paper, with an
  exact supporting quote. Lives at some **altitude** in the rollup DAG.
- **Question** — interrogative, not assertive. No quote, no stance. May be **open**
  (an unanswered question is a first-class object — a marked research frontier) or
  answered. Nests like affirmations.
- **Author** — a person. Links to papers with a position role.

---

## 4. Edges

```
Author → Paper            position: first | middle | last  (tier; co-first allowed)
                          corresponding: true               (independent flag)

Paper  → its Affirmation   asserts
                           evidence: novel-data | novel-theory | none
Affirmation → cited Paper  cites
                           role: source | corroborates | contradicts | extends | mentions
                           (the cited paper enters as a stub  ← the citation frontier)

Paper  → its Question      poses

Affirmation → broader Claim   rollup
                              polarity: concordant | discordant | neutral
Question    → broader Question rollup (nested)

Question → broader Claim       answered-by   (curated edges, not a live query)
Claim    ⟷ Claim               relates-to | depends-on   (free cross-level links)
```

Key consequences of this shape:

- **A paper only ever *asserts* its own affirmations.** An affirmation *may* cite another
  paper with a stance (`corroborates` / `contradicts`), but it points at the **paper**,
  never at that paper's affirmation — so the lossy "are these two claims *the same*?"
  merge judgment is never forced. (This is "Model 2", chosen over a shared-node model.)
  Agreement at the level of *abstractions* is expressed at the shared rollup.
- **Citations ground the cross-paper edges, and stance lives in two complementary places.**
  A *citation* carries stance toward a specific prior **paper** (`corroborates` /
  `contradicts` — "I argue with this paper"); a *rollup* carries stance toward a broader
  **claim** (`concordant` / `discordant` — "I support / undermine this generalization").
  Novelty does **not** mean uncited: a novel data point is usually born *positioned*
  against prior work, and carries exactly those citations (§6).
- **The rollup DAG is many-to-many** (not a tree): one granular atom can roll up under
  several broad claims; a broad claim can reach down to atoms under *other* broad claims.

---

## 5. Two tiers of paper — the curation frontier, made explicit

- **Curated (first-class):** actually read. *Rich* — carries its nested affirmations and
  questions, each with quotes. Produced one paper at a time, human-paced. **The human
  supplies the PDF.**
- **Stub (second-class):** exists *only* because a curated paper points at it. Just bib
  metadata + the incoming edge. Not yet read.

**Promoting a stub → curated *is* the frontier walk.** When affirmation B in paper A
cites D, D enters as a stub. The day B matters enough to chase its root, you read
D and promote it; it sprouts its own nested atoms and citation-stubs. The stub/curated
boundary *is* the curation frontier, encoded in the data.

Promotion is **type-aware** (§6): promoting a research/review stub extracts its
affirmations/questions; promoting a methods stub links it to a protocol (future, §7).

**Unit of work — curating one paper = producing its local subgraph:**
`{ the paper, its nested affirmations, its nested questions, its citation-stubs, and the
edges among them }` — e.g. *"A asserts B (evidence: novel-data) which `corroborates`
cited paper D; A poses question C; B rolls up to broad claim E."*
The whole graph is these local subgraphs stitched together where they share rollups or
point at the same papers.

---

## 6. Paper types, the evidence axis, and the citation axis

A cheap `type` label per paper, used for filtering:
`original | review | methods | perspective | commentary`.

Evidential strength is **not** carried by `type`. It splits into **two orthogonal,
per-affirmation axes** — this is where "citations ground the edges" lands. The old
single `backing` field conflated them; separating them is the key refinement.

**Evidence axis** — what *original* evidence the affirmation rests on:

| evidence | meaning | typical source |
|---|---|---|
| `novel-data` | the paper's own experiment/measurement (experimental) | original research |
| `novel-theory` | the paper's own model/argument (theoretical) | perspectives, theory papers |
| `none` | no original evidence — the affirmation is carried entirely by what it cites | reviews live here |

**Citation axis** — every `cites` edge carries a **role**, because a claim is almost
never made in a vacuum; it is positioned against prior work:

| role | meaning |
|---|---|
| `source` | the claim is borrowed wholesale from the cited paper (provenance) |
| `corroborates` | this (novel) finding *supports* the cited paper |
| `contradicts` | this (novel) finding *refutes* the cited paper |
| `extends` | builds on / generalizes the cited paper |
| `mentions` | neutral reference |

The two axes are independent. A borrowed claim is `evidence: none` + a `source` citation.
A novel data point that contradicts Smith is `evidence: novel-data` + a `contradicts`
citation of `smith`. **Novelty does not mean uncited** — most novel contributions
corroborate or contradict existing claims and carry exactly those citations. Both axes
are *optional to populate* (unset is valid) and are structurally just edge tags — no new
node type. Together they power filters like "only the theoretical claims under topic X"
or "which novel results contradict this broad claim."

How each paper type lands without any new structure:

| type | affirmations mostly… | role |
|---|---|---|
| original research | `novel-data`, citing prior work `corroborates` / `contradicts` | bedrock evidence |
| perspective / commentary | `novel-theory` | argument; weak evidence |
| review | `evidence: none`, dense `source` citations | **best bootstrapping seed** — a pre-assembled frontier of stubs |
| methods | — (parked, §7) | bridges to `protocols/` (future) |

---

## 7. Methods papers — parked on a reserved "how" axis

A methods paper isn't *weak* knowledge, it's a *different kind*: it doesn't say "X is
true," it says "here's how to find out." It makes no affirmations and poses no questions,
so it does **not** sit on the claims/questions DAG. But it isn't excluded either.

The literature carries two axes, braided in every paper — *"we found **X** (a claim)
using **technique T** (a method)."*

- **what / why axis** — claims & questions (everything above)
- **how axis** — methods papers, cited *for a tool*, the literature-facing twin of this
  repo's `protocols/`

**v1 scope:** a methods paper is just a `Paper` with `type: methods` — it **exists as a
node** (authors, metadata, citable) but its special structure is dormant. The `uses-method`
edge (Paper → Methods paper) and the methods-paper ↔ protocol bridge are a **reserved
future extension** that doesn't disturb the core.

---

## 8. Acquisition — descoped

Because first-class papers are human-curated and **the human supplies the PDF**, the
"paywalled bulk-fetch via a headless Pasteur browser" problem evaporates for v1:

- **First-class:** drop the PDF into the external dir. No scraping. The paywall is solved
  by the human already having access and choosing what to curate.
- **Stub:** only ever needs bib metadata, which is open (Crossref / doi2bib) — never
  paywalled. Cheap and automatic.
- The Pasteur browser becomes an *optional manual convenience* for the moment you promote
  a stub and want its PDF — not a system to build.

---

## 9. Properties that fall out for free (how we know the model is right)

- **Evidence meter is emergent.** A broader claim's `concordant` vs `discordant`
  child-count *is* its state-of-knowledge balance ("5 support, 2 contradict") — just
  counting rollup edges, not a built feature.
- **"Walk to root" is finite and deterministic:** follow a `source` citation → its stub
  → promote it → that paper's own affirmation (which carries `novel-*` evidence, or its
  own `source` citations) → repeat until you hit `novel-*` evidence. The provenance chain
  terminates; `corroborates` / `contradicts` citations are *lateral* (positioning), not
  part of the root walk.
- **Author queries are free:** "everything where X is corresponding author," "which
  claims does this group keep contradicting" — once position is an edge attribute.

---

## 10. Guiding principles

1. **Curation is the rate limiter** — propose / accept / edit / reject; never flood.
   A partial graph is valid.
2. **Generalize, don't merge** — never equate two claims (lossy). Co-parent them under a
   broader claim; the paper-specific phrasing and quote are never destroyed.
3. **Keep authoring cheap** — the moat the formal academic efforts (nanopublications,
   ORKG) never had: they died on the cost of hand-authoring rigid RDF triples. Here an AI
   drafts claims in natural language; the human only curates.
4. **Lazy, human-paced frontiers** — citation walking and question capture are selective,
   never exhaustive. You record only what is live for *your* research.

---

## 11. Prior art (ideas borrowed)

- **Nanopublications** — atomic assertion + provenance; the model is almost exactly an
  "affirmation." *Lesson: adoption died on RDF authoring cost → keep authoring cheap.*
- **Open Research Knowledge Graph** — comparison tables across papers (a future matrix view).
- **scite** — citations as support / contrast / mention; adopted directly as our
  **citation role** (`corroborates` / `contradicts` / `mentions`).
- **Consensus** — the agreement "meter" (our emergent evidence balance).
- **Elicit** — the literature matrix (a future view).
- **PaperQA2** — `search → gather_evidence → answer` RAG; the engine that turns full text
  into claims-with-quotes; living, cited answers to questions.
- **Zotero Better Notes** — markdown notes with claim-to-citation traceability inside
  Zotero; the closest existing thing, just not in *our* interface.

---

## 12. Out of scope / future

- **AI–human curation interface** — the propose/accept rhythm; how a paper's proposed
  local subgraph is surfaced and accepted/edited/rejected. *A separate design challenge,
  next.*
- **The "how" axis** — `uses-method` edges + methods-paper ↔ `protocols/` bridge (§7).
- **Cross-link to experiments** — a claim → an `experiments.db` experiment that tests it;
  unifies the lab notebook and the literature into one graph.
- **Additional views** — matrix / comparison (ORKG, Elicit), per-question synthesized answers.
- **Questions: independent vs anchored nesting** — whether the question DAG stands alone or
  anchors onto claim altitudes (lean: anchored, shallow). Left open.

---

## 13. Converged model — one-screen summary

```
Layers:   Sources (Paper, Author) · Atoms (Affirmation, Question) · Abstractions (broader claims)

Nodes:    Paper(type; curated | stub) · Affirmation · Question · Author

Edges:    Author      → Paper        position: first | middle | last (+ corresponding: true)
          Paper        → Affirmation  asserts; evidence: novel-data | novel-theory | none
          Affirmation  → Paper        cites; role: source | corroborates | contradicts | extends | mentions
          Paper        → Question     poses
          Affirmation  → broader Claim rollup; polarity: concordant | discordant | neutral
          Question     → broader Question rollup
          Question     → broader Claim answered-by      (curated)
          Claim        ⟷ Claim        relates-to | depends-on

Principles: curation-paced · generalize-don't-merge · cheap authoring · lazy frontiers
Methods papers: parked (type=methods), "how" axis reserved
Acquisition: human supplies first-class PDFs; stubs = open metadata only
```
