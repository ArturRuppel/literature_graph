# litgraph — the model

**Status:** model converged and implemented; the `lit` CLI ingests, curates, builds and serves
**Model since:** 2026-06-25 · **Last revised:** 2026-08-13

A knowledge graph over the scientific literature. You read a
paper, and the claims, questions and methods inside it become curated, linkable nodes —
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
  plain directory the human owns, named by config (an absolute path outside the repo —
  a mounted share, a local data dir). Never committed; the human supplies them and
  nothing scrapes. *(An earlier draft used Zotero as the backend; it was dropped — too
  much overhead, a sandbox/API to fight, for virtually no gain once the semantic layer
  lives in our own YAML.)*
- **The source of truth is plain-text YAML in git** — one diffable file per curated
  paper, holding its claim / question / method slices and edges. A diffable text form is
  what git versions and a human reviews; the binary index is a derived artifact, gitignored.
  See [SCHEMA.md](SCHEMA.md) for the on-disk layout.
- **A generator builds a SQLite graph index + the catalog views** from that YAML. The
  binary graph is a disposable build artifact (gitignored, like `experiments.db`). CI
  can build the published views with **no reference manager present** — no live app or
  local API is ever in the loop, so the published view never depends on one.

```
human-supplied PDF ─▶ external PDF dir   [outside git, named by config]
                          │  read + curate, one paper at a time
                          ▼
   per-paper YAML: claim / question / method slices + edges  [git-tracked, diffable]  ◀ source of truth
   broader claims / questions (free-floating)         [git-tracked]
                          │  generator
                          ▼
       graph.db (SQLite, gitignored)  ─▶  bibliography + knowledge-graph views   [built by CI]
```

---

## 2. One primitive — the slice, in a container

The whole model is **slices** and **containers**.

- A **slice** is an irreducible piece of a paper — the only kind of node. Three kinds:
  **Claim · Question · Method** (§3). A slice is **recursively sliceable**: a claim
  decomposes into sub-claims, which are themselves slices.
- A **paper is a container `P`** — nothing but the grouping of its slices. A paper *is*
  its slices; "the paper as a whole" is just `P`.
- **Generality is not a separate layer.** A broad claim is simply a slice high in the
  `leads-to` chain (§4): the granular end is paper-bound with a quote, the broad end is what
  you'd write in a review's intro. **One continuous ladder** — no separate "abstraction"
  node type. (An early draft folded *topics* into this ladder as "just a claim at high
  altitude". That was wrong and is retracted: a topic asserts nothing, so every emergent
  property here is undefined on it. Topics are a **separate keyword axis**, outside the
  slice graph — SCHEMA §9.)
- A **stub** is a container with no resolved slices yet — a single **wildcard** standing for
  *"some slice in here, not yet cut."* **Curation = slicing the container** (§5).
- **`P` is a valid endpoint for any edge whose target-kind it can host.** Aiming an edge at
  `P` says *"the real target is some slice inside — not yet resolved."* As the container is
  sliced, the edge **sharpens** from `P` to the specific slice — never forced; resting at
  `P` is valid (the lazy frontier, §10).

Authors sit **outside** this — a person attached to a container (provenance about who wrote
it), not a slice.

> **One extension exists.** Everything in this document models what *is known*. The same
> primitive has been extended to what is *proposed* — a research programme: hypotheses, the
> tests that would settle them, the capabilities those tests need. It adds two node kinds
> (**capability**, **test**) and an aim as the container, and it lives beside `curated/`
> rather than forking the model. Specified in
> [docs/2026-08-02-programme-graph-design.md](docs/2026-08-02-programme-graph-design.md),
> worked in [`example/programme/`](example/programme/), reported by `lit programme`. The
> three-edge core below is untouched by it.

---

## 3. Slice kinds (3) — and everything else emergent

| Slice | is | terminates a chain? |
|---|---|---|
| **Claim** | an assertion — what you'd write in an intro; quote-bound when paper-local | only if it is an **axiom** (a claim declared self-grounding: a definition / postulate) |
| **Question** | an interrogative — no stance; welded to the sentence that *raises* it (a `quote`, like a claim — optional, but expected for open questions) | n/a |
| **Method** | a technique — a *measurement* or a *model* | a **measurement** is a floor; a **model** is not (§7) |

A `leads-to` chain (§4) bottoms out at a **floor** — the two ways knowledge is grounded:

- a **measurement Method** → *empirical* (data + reasoning); the data alone asserts nothing — reasoning
  reads the claim out of it;
- an **axiom** → *formal* (reasoning from a declared starting point; maths lives here).

A floor is **wherever the curator stops decomposing**, not a metaphysically pure bottom: a
measurement like a microbenchmark harness already embeds theory, but we cite its source and
stop — pragmatic, emergent. A **model** is a Method that does *not* stop: it `grounds in` the
measurements it consumes and the theory it assumes, layering between data and the claims it
feeds (§7) — so floor-ness is itself emergent (does *this* slice's grounding bottom out?).

Everything above a floor is reasoning. **No `status` / `evidence` / `role` fields on any
node** — every property we used to tag is read straight off the graph:

| property | read from |
|---|---|
| question **open vs answered** | does it have an incoming `answers` edge? |
| claim **original vs borrowed** | does its `leads-to` ground cross into another paper (a citation, §6.1)? |
| claim **grounded vs merely plausible** | does its `leads-to` chain reach a **floor** (method or axiom), or dangle on reasoning? |
| **evidence balance** of a claim | count `corroborate` vs `contradict` |

The **only** deliberate marker left in the model is *"this slice is a floor"* — emergent for
measurement Methods, a one-off declaration for an axiom. Strength is left emergent too (a proof and
a hand-wave differ by what corroborates them, not by a label). **Authors** are still
derived, not authored (§5).

---

## 4. Three edges

```
leads-to              Claim ← Claim,  or  Claim ← Method / axiom (the floor)
                      the entire support skeleton: grounding · derivation · generalization · citation
answers               Claim → Question
corroborate /         Claim ⟷ Claim   (lateral: two independently-grounded claims agree / clash)
  contradict
```

- **`leads-to` is one edge doing four jobs**, all the same orientation **ground → derived**:
  - a method/axiom **leads to** a claim → *grounding* (reaching a floor, §3);
  - one claim **leads to** another → *derivation* (the maths chain);
  - specific claims **lead to** a broader one → *generalization* (the old "rollup" — same
    edge, read upward; many-to-many, so the support DAG is not a tree);
  - a source's claim **leads to** your restatement of it → *citation* (the speaker grounds
    the listener, §6.1) — **cross-paper, and the citation lives on the *edge*, never as a
    node attribute.**
- **`corroborate` / `contradict` are *not* support** — neither claim grounds the other; they
  are independently grounded and happen to agree or collide. This is the only place stance
  lives, and the only **signed** edge. (The old "are these two claims the same?" merge is
  still never forced: agreement is an *edge between distinct slices*, never a node-collapse.)
- **`answers`** resolves a Question with a Claim — usually **intra-paper**, the self-
  referential spine *"we asked Q, we found A"*; a question's answeredness is then just the
  presence of this edge (§3).
- **Container wildcard (§2):** any edge may land on a container `P` when its precise slice
  isn't resolved (cite an un-sliced stub; park a method at the paper) and sharpens on
  curation. **Authors** attach to the container, outside the slice graph (§5).

This retires the old shape: 5 node-types → **one** (slice); ~15 edges → **three**; and the
`evidence` / citation-`role` / `status` axes dissolve into structure (§3).

---

## 5. Two tiers of paper — the curation frontier, made explicit

- **Curated (first-class):** actually read. *Rich* — **sliced** into its claims, questions
  and methods, each quote-welded. Produced one paper at a time, human-paced. **The human
  supplies the PDF.**
- **Stub (second-class):** exists *only* because a curated paper grounds in it. An un-sliced
  container — just bib metadata + the incoming edge (the wildcard, §2). Not yet read.

**Promoting a stub → curated *is* the frontier walk.** When claim B in paper A grounds in D
(a `leads-to` citation, §4), D enters as a stub. The day B matters enough to chase its root,
you read D and **slice it**; it sprouts its own claim/question/method slices and further
stubs, and B's grounding sharpens from `P` to D's specific slice (§2). The stub/curated
boundary *is* the curation frontier, encoded in the data.

**Unit of work — curating one paper = producing its local subgraph:**
`{ the container, its claim / question / method slices, the stubs it grounds in, and the
edges among them }` — e.g. *"P contains claim B (grounded in a method) that `contradict`s
cited paper D; question C, answered by B; B `leads-to` broad claim E."*
The whole graph is these local subgraphs stitched where they share `leads-to` targets or
ground in the same papers.

---

## 6. Paper types — a cheap filter

A `type` label per paper, for filtering only: `original | review | methods | perspective |
commentary`. It carries **no** evidential weight — grounding and strength are read off the
graph (§3), never from the label.

The two extra axes an earlier draft carried are gone, dissolved into the slice model:

- the old **evidence** axis (`novel-data | novel-theory | none`) → *does a claim's
  `leads-to` chain reach a floor, and which kind?* (§3) — emergent, not a field;
- the old citation **role** enum (`source | corroborates | contradicts | extends |
  mentions`) → the **edges themselves**: `leads-to` already carries grounding, citation and
  extension (`source`/`extends` were only ever "this grounds that"); `corroborate` /
  `contradict` carry lateral stance; and `mentions` is **dropped** (a bare "see also" earns
  no edge).

How each type still lands, with no special structure:

| type | its slices are mostly… |
|---|---|
| original research | claims grounded in a **Method** floor; positioned against prior work by `corroborate` / `contradict` |
| perspective / commentary | claims grounded only in **reasoning** — no floor reached, so visibly *plausible*, not established |
| review | claims whose `leads-to` grounds in **other papers' claims** (citations): a chorus of restatements (§6.1) — the **best bootstrapping seed**, a pre-assembled frontier of stubs |
| methods | a **Method** slice (a floor); pulled in by the `leads-to` grounding of the claims that use it |

### 6.1 State and restate — the speaker/listener provenance

Citation — a cross-paper `leads-to` (§4) — hides a deeper structure: a claim is *stated*
once and *restated* many times. **One speaker, many listeners.**

- **The speaker (original statement).** A claim grounded in a **floor** (a method, or an
  axiom — §3) is its own root: the paper that first established it. Usually one root; a claim
  **co-discovered** by independent labs just has *several* speakers (several floor-grounded
  statements) converging on the one general claim — many-to-many `leads-to` (§4) permits this
  with no special case.
- **The listener (restatement).** A paper that **borrows** a claim grounds it not in a floor
  but in a cross-paper `leads-to` to the source — restating it *in its own words, welded to
  its own quote*. A review is a chorus of restatements. **Original vs borrowed is therefore
  emergent** (§3): does this claim's grounding reach a floor, or point at another paper?
- **Provenance has a direction.** The `leads-to` flows **speaker → listener**: the claim
  propagates from its root to everyone who restates it. Follow it *against the flow* and you
  reach the floor — this is the §9 root-walk. (An interface draws the arrowhead so: a
  restatement's grounding arrives *from* its source; an original's, from a floor.)
- **Restatements sharpen when their source is curated.** While the source is an un-sliced
  stub, the borrowed claim grounds at the **container** `P` (the wildcard, §2). Promote that
  stub and the grounding **sharpens** to the source's specific claim-slice — provenance made
  explicit, nothing lost (the restatement always carried its own quote).

Not to be confused with **`corroborate` / `contradict`** (§4): those are *lateral* — two
independently floor-grounded claims that agree or collide, neither one restating the other.

---

## 7. Methods — the "how" axis (measurements are floors, models layer)

A methods paper isn't *weak* knowledge, it's a *different kind*: it doesn't assert "X is
true," it says "here's how to find out." Its slices are **Methods** — and a *measurement*
Method is a **floor** (§3), where an empirical claim's `leads-to` chain bottoms out.

The literature braids *"we found **X** (a claim) **via** technique **T** (a method)."* In
the slice model that braid is **not a new edge** — it's just `leads-to`: a data-grounded
claim **grounds in** the Method that produced its data. The grounding *is* the how-axis, so
the graph still answers "everything established via microbenchmarking" or "is this finding method-dependent?"

- **A model is a Method that grounds in other Methods.** Measurements are floors; a
  mathematical model is *not* — it `grounds in` the measurements it consumes *and* the theory
  it assumes, layering between data and the claims it feeds. "Layers on top" is literal:
  `m_model grounded_in [m_measurement, …]`. A claim made by *comparing data with a model* just
  grounds in **both branches** — their agreement is the claim, no "comparison" edge needed.
- **A Method is a slice like any other** — recursively generalizable up the `leads-to`
  ladder (a use of a harness → *microbenchmark* → *performance benchmarking*), exactly as a
  narrow claim generalizes to a broad one. No separate "method-use vs Method" machinery:
  same kind, different altitude.
- **Methods enter the frontier the same way.** A claim grounding in a Method whose
  introducing paper isn't curated points at that paper's **container** `P` (the wildcard,
  §2). Promote the methods stub and the grounding sharpens to the Method slice it
  introduced — the frontier walk on the how-axis, identical machinery to the what-axis.

**Still reserved:** the bridge from a Method to *this lab's own* `protocols/` (the
lab-notebook cross-link, §12) — distinct from the literature-internal how-axis here.

---

## 8. Acquisition — descoped

Because first-class papers are human-curated and **the human supplies the PDF**, the
paywalled-bulk-fetch problem evaporates for v1:

- **First-class:** drop the PDF into the external dir. No scraping. The paywall is solved
  by the human already having access and choosing what to curate.
- **Stub:** only ever needs bib metadata, which is open (Crossref / doi2bib) — never
  paywalled. Cheap and automatic.
- Fetching a PDF by hand at the moment you promote a stub is an *optional convenience*,
  not a system to build.

---

## 9. Properties that fall out for free (how we know the model is right)

- **Evidence meter is emergent.** A claim's `corroborate` vs `contradict` count *is* its
  state-of-knowledge balance ("5 support, 2 contradict") — just counting lateral edges (§4),
  not a built feature.
- **"Walk to root" is finite and deterministic:** follow a claim's `leads-to` grounding
  down — into another paper (a citation → promote the stub → that paper's own claim) or
  toward a floor — and repeat until you hit a **floor** (a method or axiom). The chain
  terminates by construction; `corroborate` / `contradict` are *lateral*, never part of the
  walk. This walk *is* the speaker/listener chain (§6.1) traversed against the flow.
- **Grounded vs plausible is emergent** (§3): a claim whose walk reaches a floor is
  established; one whose chain dangles in reasoning is visibly *plausible*.
- **Author queries are free:** "everything where X is corresponding author," "which
  claims does this group keep contradicting" — once position is an edge attribute on the container.

---

## 10. Guiding principles

1. **Curation is the rate limiter** — propose / accept / edit / reject; never flood.
   A partial graph is valid — and so is a partial *paper*. Curation is a **single staircase**
   orthogonal to the curated/stub breadth tier (§5): a paper climbs one rung at a time from a
   bare ingested skeleton, through the abstract, the intro+discussion, the results, and finally
   the methods (CURATION.md). The **breadth** tier stays emergent (curated vs stub = file
   presence, §5), but the **depth** rung is recorded in one small authored field —
   `pass: 0–4` on the curated paper (**0** ingested · **1** abstract · **2** intro+discussion ·
   **3** results · **4** methods; SCHEMA §4) — because *how far curation went* is
   process state, not graph structure, and it isn't reconstructable from the slices alone:
   the read→slice map is lossy both ways (a deep read may add no method slices; a shallow read
   may opportunistically grab a floor), so depth can't be inferred from which slice kinds
   are present. The rung is *both* how far the paper was read and how mature the card is — one
   number, no second axis. This is the lone exception to "no authored process fields"; stopping
   early is a normal resting state, not an unfinished task.
2. **Generalize, don't merge — but don't duplicate for nesting either.** Never equate two
   claims (lossy); co-parent them under a broader claim via `leads-to` (§4), and the
   paper-specific phrasing and quote are never destroyed. Conversely, a broader claim **earns
   its existence only when ≥2 children actually share it** (or it is genuinely broader than
   any single child) — never mint a thin claim that merely echoes one. And one claim is **one
   slice, refined across passes**, never re-extracted per section: generality lives in
   `leads-to` *edges between distinct slices*, never in a slice copied to two altitudes.
3. **Keep authoring cheap** — the constraint that killed the formal academic efforts
   (nanopublications, ORKG): they died on the cost of hand-authoring rigid RDF triples.
   Here an AI drafts claims in natural language; the human only curates. Note this is
   *table stakes*, not an advantage — cheap LLM extraction is now what everyone in this
   space does (§11). What is actually distinctive is downstream of it: the **frontier**
   (§5) is a reader-side concept a publisher curating its own corpus structurally cannot
   have; the **quote weld** is enforced as a build-failing validation rule rather than a
   convention (SCHEMA §6.4); and the **lab-notebook bridge** (§12) connects a claim to the
   experiment that tests it. The last of those is the durable one.
4. **Lazy, human-paced frontiers** — citation walking and question capture are selective.
   **Exhaustive citation coverage (every cited paper given an edge) is an *ambition, not a
   requirement*.** Because the model has no bare paper→paper edge — every edge rides a slice
   (or the container wildcard, §2) — each one costs a mediating slice. So spend cheaply where
   it's cheap: *anchor the citation walls* (one borrowed claim grounds the whole wall, a
   single `leads-to` into all the papers cited behind it), let methods grounding fall out of
   Pass 3 for free, reserve `corroborate` / `contradict` for findings that earn them, and
   leave genuinely incidental references as bare stubs. You record what is live for *your*
   research.

---

## 11. Prior art and neighbours

### Ideas borrowed

- **Nanopublications** — atomic assertion + provenance; the model is almost exactly a
  **slice**. *Lesson: adoption died on RDF authoring cost → keep authoring cheap.*
- **Open Research Knowledge Graph** — comparison tables across papers (a future matrix view).
- **scite** — citations as support / contrast; adopted as our lateral `corroborate` /
  `contradict` edges (§4). *(Their "mention" we drop.)*
- **Consensus** — the agreement "meter" (our emergent evidence balance).
- **Elicit** — the literature matrix (a future view).
- **PaperQA2** — `search → gather_evidence → answer` RAG; the engine that turns full text
  into claims-with-quotes; living, cited answers to questions.
- **Zotero Better Notes** — markdown notes with claim-to-citation traceability inside
  Zotero; the closest existing thing, just not in *our* interface.

### The 2026 wave — same premise, arrived at independently

Through 2026 several groups converged on this document's starting point: that papers are
narrative artifacts, and that machines need claims welded to evidence. Read as
**validation, not competition** — this repo exists because its author needed it, and other
people building the same thing means the problem was real.

- **MIRA** (`mira.science`) — the closest relative. Questions / claims / evidence / sources
  as four node types plus typed relations, each record signed by its author.
- **OpenEval** — Booeshaghi, Luebbert & Pachter, *Science should be machine-readable*
  (bioRxiv, 2026, `10.64898/2026.01.30.702911`): claim extraction across the eLife corpus,
  fully automated, benchmarked against human reviewers. The proof that extraction scales.
- **Mainen / HaaK** — typed propositions and typed logical relations (`A requires B`),
  with **invalidity propagation**: a floor that fails greys out everything downstream. That
  view is nearly free here, since `leads-to` is already an acyclic ground → derived DAG, and
  it is the best idea in this list to steal.
- **QED Science**, **preprints.ai** — claim trees used for review and validity scoring.
- **eLife Pathways** — the publisher-side effort connecting several of the above.

Two things follow. First, where those designs keep node types and status fields, this one
reduced to **one primitive and three edges** with everything else emergent (§13) — that
reduction is the main thing worth contributing back. Second, litgraph sits **downstream**
of them: if a machine-readable claim format lands upstream, `lit ingest` becomes "fetch the
claim tree" instead of "run an extractor over a PDF". So the ingest boundary stays
importable, and bespoke extraction machinery is deliberately under-invested in.

---

## 12. Out of scope / future

Since resolved, and no longer open questions:

- **AI–human curation interface** — built. The propose/accept rhythm is CURATION.md's
  pass staircase, and the viewer (`lit build` / `lit serve`, with `lit preview` rendering a
  proposition before it is committed) is the surface it happens on. Design history in
  [docs/](docs/), starting with
  [the visualization design](docs/2026-06-25-visualization-design.md).
- **Questions: independent vs anchored nesting** — resolved to *independent*: broad
  questions get their own thin `questions/` files and a claim's `answers` is the only
  bridge from a question to a claim (SCHEMA §8, still retractable).

Genuinely still out of scope:

- **The lab-notebook bridge** — linking a Method to the curator's own experimental
  protocols, and a claim to the experiment that tests it. This is the one direction nobody
  else in the field is building (§11), and it is deliberately not in this repo: it needs a
  lab notebook on the other end. The literature-internal how-axis is in the core (§7).
- **Additional views** — matrix / comparison, per-question synthesized answers.

---

## 13. Converged model — one-screen summary

```
Primitive: the SLICE — one node kind, recursively sliceable, inside a CONTAINER P (paper)
Slice kinds: Claim · Question · Method        (Method, and any declared axiom = a FLOOR)

Edges (3):
   leads-to            Claim ← Claim,  or  Claim ← Method/axiom (the floor)
                       = grounding · derivation · generalization · citation   (orient: ground → derived)
   answers             Claim → Question
   corroborate /       Claim ⟷ Claim   (lateral stance; the only signed edge)
     contradict

Container wildcard: any edge may target P when its slice isn't resolved; sharpens on curation.
A stub = a container holding only the wildcard.   Author = attached to P, outside the slice graph.

Emergent — no node fields:
   open vs answered      = has an incoming `answers` edge?
   original vs borrowed  = does `leads-to` grounding cross papers (a citation)?
   grounded vs plausible = does the `leads-to` chain reach a floor (method / axiom)?
   evidence balance      = count corroborate vs contradict

Principles: curation-paced · generalize-don't-merge · cheap authoring · lazy frontiers
Acquisition: human supplies first-class PDFs; stubs = open metadata only
```
