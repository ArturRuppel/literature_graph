# litgraph: the model

**Status:** model converged and implemented. The `lit` CLI ingests, curates, builds and serves.
**Model since:** 2026-06-25. **Last revised:** 2026-09-01.

A knowledge graph over the scientific literature. You read a paper, and the claims,
questions and methods inside it become nodes in a graph, each welded to its source by an
exact quote. Claims roll up from paper-specific and granular toward broad and general, so
the graph doubles as a living, evidence-backed map of what is known on the topics you care
about. Every node is something you could write in a paper's introduction, with the
supporting or contradicting literature one click away.

One constraint shapes every decision below: curation is the rate limiter. The system
proposes and a human accepts, edits or rejects. It never floods. A half-finished graph is a
normal, valid state.

Section 13 is a one-screen summary of the whole model. Section 14 records the ideas this
model replaced, so that the sections in between can describe the model as it is.

---

## 1. Plain text in git is the source of truth

PDFs live outside git, in a directory the human owns and names in config. The human
supplies them; nothing scrapes. Curated PDFs and their extracted full text are committed to
the private data repo, one per paper. Uncurated staging PDFs stay outside git.

The source of truth is YAML in git: one diffable file per curated paper, holding its claim,
question and method slices and their edges. A text form is what git versions and a human
reviews. See SCHEMA.md for the on-disk layout.

A generator builds a SQLite graph index and the catalog views from that YAML. The binary
graph is a disposable build artifact, gitignored like `experiments.db`. CI builds the
published views with no reference manager present, so the published view never depends on
a live app or a local API.

```
human-supplied PDF ─▶ external PDF dir   [outside git, named by config]
                          │  read + curate, one paper at a time
                          ▼
   per-paper YAML: claim / question / method slices + edges  [git-tracked, diffable]  ◀ source of truth
   broader claims / questions (free-floating)                [git-tracked]
                          │  generator
                          ▼
       graph.db (SQLite, gitignored)  ─▶  bibliography + knowledge-graph views   [built by CI]
```

---

## 2. One primitive: the slice, in a container

The whole model is slices and containers.

A **slice** is an irreducible piece of a paper and the only kind of node. It comes in three
kinds, claim, question and method, described in section 3. A slice is recursively
sliceable: a claim decomposes into sub-claims, which are themselves slices.

A **paper** is a container, written `P`. It is nothing but the grouping of its slices. A
paper is its slices, and "the paper as a whole" is just `P`.

Generality is not a separate layer. A broad claim is a slice high in the `leads-to` chain
of section 4. The granular end is paper-bound and quote-welded; the broad end is what you
would write in a review's introduction. It is one continuous ladder with no separate
abstraction node type. Topics are not on this ladder. A topic asserts nothing, so every
emergent property in this model is undefined on it. Topics are a separate keyword axis
outside the slice graph, specified in SCHEMA section 9.

A **stub** is a container with no resolved slices yet. It holds a single wildcard standing
for "some slice in here, not yet cut". Curation is slicing the container; see section 5.

`P` is a valid endpoint for any edge whose target kind it can host. Aiming an edge at `P`
says that the real target is some slice inside, not yet resolved. As the container is
sliced, the edge sharpens from `P` to the specific slice. Sharpening is never forced.
Resting at `P` is valid, and section 10 calls this the lazy frontier.

Authors sit outside the slice graph. An author is a person attached to a container, as
provenance about who wrote it, not a slice.

One extension exists. Everything in this document models what is known. The same primitive
has been extended to what is proposed: a research programme of hypotheses, the tests that
would settle them, and the capabilities those tests need. The extension adds two node kinds,
capability and test, and an aim as the container. It lives beside `curated/` rather than
forking the model, and the three-edge core below is untouched by it. It is specified in
[docs/2026-08-02-programme-graph-design.md](docs/2026-08-02-programme-graph-design.md),
worked in [`example/programme/`](example/programme/), and reported by `lit programme`.

---

## 3. Three slice kinds, and everything else emergent

| Slice | is | terminates a chain? |
|---|---|---|
| **Claim** | an assertion, what you would write in an introduction; quote-bound when paper-local | only if it is an axiom: a claim declared self-grounding, such as a definition or postulate |
| **Question** | an interrogative with no stance, welded to the sentence that raises it; the quote is optional but expected for open questions | not applicable |
| **Method** | a technique, either a measurement or a model | a measurement is a floor; a model is not (section 7) |

A `leads-to` chain bottoms out at a **floor**. There are two ways knowledge is grounded:

- A measurement method gives empirical grounding: data plus reasoning. The data alone
  asserts nothing; reasoning reads the claim out of it.
- An axiom gives formal grounding: reasoning from a declared starting point. Mathematics
  lives here.

A floor is wherever the curator stops decomposing, not a metaphysically pure bottom. A
measurement like a microbenchmark harness already embeds theory, but we cite its source and
stop. A model is a method that does not stop: it grounds in the measurements it consumes
and the theory it assumes, layering between data and the claims it feeds. So floor-ness is
itself emergent. The question is whether this slice's grounding bottoms out.

Everything above a floor is reasoning. No node carries a `status`, `evidence` or `role`
field. Every property that could be tagged is read off the graph instead:

| property | read from |
|---|---|
| question open vs answered | does it have an incoming `answers` edge? |
| claim original vs borrowed | does its `leads-to` grounding cross into another paper, i.e. a citation (section 6.1)? |
| claim grounded vs merely plausible | does its `leads-to` chain reach a floor, or dangle on reasoning? |
| evidence balance of a claim | count `corroborate` against `contradict` |

The only deliberate marker in the model is "this slice is a floor". It is emergent for
measurement methods and a one-off declaration for an axiom. Strength is emergent too: a
proof and a hand-wave differ by what corroborates them, not by a label. Authors are derived,
never authored (section 5).

---

## 4. Three edges

```
leads-to              Claim ← Claim,  or  Claim ← Method / axiom (the floor)
                      the entire support skeleton: grounding · derivation · generalization · citation
answers               Claim → Question
corroborate /         Claim ⟷ Claim   (lateral: two independently grounded claims agree / clash)
  contradict
```

`leads-to` is one edge doing four jobs, all with the same orientation, ground to derived:

- A method or axiom leads to a claim. That is grounding, reaching a floor.
- One claim leads to another. That is derivation, the chain of reasoning.
- Specific claims lead to a broader one. That is generalization, the same edge read upward.
  It is many-to-many, so the support DAG is not a tree.
- A source's claim leads to your restatement of it. That is citation: the speaker grounds
  the listener, as section 6.1 describes. It is cross-paper, and the citation lives on the
  edge, never as a node attribute.

`corroborate` and `contradict` are not support. Neither claim grounds the other. Both are
independently grounded and happen to agree or collide. This is the only place stance lives
and the only signed edge. Agreement is an edge between distinct slices, never a merge of
two nodes.

`answers` resolves a question with a claim. It is usually intra-paper, the spine of "we
asked Q, we found A". A question's answeredness is then just the presence of this edge.

Any edge may land on a container `P` when its precise slice is not resolved, for example
to cite an un-sliced stub or to park a method at the paper. It sharpens on curation. Authors
attach to the container, outside the slice graph.

On disk, `leads-to` is written from the derived end as `grounded_in` and from the ground end
as `leads_to`. SCHEMA section 5 gives the full mapping from these three edges to YAML fields.

---

## 5. Two tiers of paper: the curation frontier

A **curated** paper has been read. It is sliced into its claims, questions and methods, each
quote-welded, one paper at a time and human-paced. The human supplies the PDF.

A **stub** exists only because a curated paper grounds in it. It is an un-sliced container:
bibliographic metadata plus the incoming edge, the wildcard of section 2. It has not been
read.

Promoting a stub to curated is the frontier walk. When claim B in paper A grounds in D
through a citation, D enters as a stub. The day B matters enough to chase its root, you read
D and slice it. D sprouts its own slices and further stubs, and B's grounding sharpens from
`P` to D's specific slice. The boundary between stub and curated is the curation frontier,
encoded in the data.

The unit of work is one paper, and curating one paper means producing its local subgraph:
the container, its slices, the stubs it grounds in, and the edges among them. For example:
paper P contains claim B, grounded in a method, that contradicts cited paper D; question C,
answered by B; and B leads to broad claim E. The whole graph is these local subgraphs
stitched together where they share `leads-to` targets or ground in the same papers.

---

## 6. Paper types: a cheap filter

Each paper carries a `type` label, one of `original`, `review`, `methods`, `perspective` or
`commentary`. It is for filtering only and carries no evidential weight. Grounding and
strength are read off the graph, never from the label.

Each type still lands recognisably in the graph, with no special structure:

| type | its slices are mostly… |
|---|---|
| original research | claims grounded in a method floor; positioned against prior work by `corroborate` and `contradict` |
| perspective / commentary | claims grounded only in reasoning; no floor reached, so visibly plausible rather than established |
| review | claims whose `leads-to` grounds in other papers' claims: a chorus of restatements (section 6.1). The best bootstrapping seed, since it is a pre-assembled frontier of stubs |
| methods | a method slice, which is a floor; pulled in by the grounding of the claims that use it |

### 6.1 State and restate: speaker and listener

A citation is a cross-paper `leads-to`, and it hides a deeper structure. A claim is stated
once and restated many times: one speaker, many listeners.

The speaker is the original statement. A claim grounded in a floor is its own root: the
paper that first established it. Usually there is one root. A claim co-discovered by
independent labs has several speakers, several floor-grounded statements converging on the
one general claim. Many-to-many `leads-to` permits this with no special case.

The listener is a restatement. A paper that borrows a claim grounds it not in a floor but in
a cross-paper `leads-to` to the source, restating it in its own words and welded to its own
quote. A review is a chorus of restatements. Original versus borrowed is therefore emergent:
does this claim's grounding reach a floor, or point at another paper?

Provenance has a direction. `leads-to` flows from speaker to listener: the claim propagates
from its root to everyone who restates it. Follow it against the flow and you reach the
floor. That is the root walk of section 9. An interface draws the arrowhead accordingly: a
restatement's grounding arrives from its source, an original's from a floor.

Restatements sharpen when their source is curated. While the source is an un-sliced stub, the
borrowed claim grounds at the container `P`. Promote that stub and the grounding sharpens to
the source's specific claim slice. Nothing is lost, because the restatement always carried
its own quote.

This is not `corroborate` or `contradict`. Those are lateral: two independently
floor-grounded claims that agree or collide, neither restating the other.

---

## 7. Methods: measurements are floors, models layer

A methods paper is not weak knowledge. It is a different kind. It does not assert that X is
true; it says how to find out. Its slices are methods, and a measurement method is a floor
where an empirical claim's `leads-to` chain bottoms out.

The literature braids "we found X via technique T". In the slice model that braid is not a
new edge. It is `leads-to`: a data-grounded claim grounds in the method that produced its
data. The grounding is the how-axis, so the graph still answers "everything established via
microbenchmarking" and "is this finding method-dependent?".

A model is a method that grounds in other methods. Measurements are floors; a mathematical
model is not. It grounds in the measurements it consumes and the theory it assumes, layering
between data and the claims it feeds. "Layers on top" is literal:
`m_model grounded_in [m_measurement, …]`. A claim made by comparing data with a model grounds in both branches.
Their agreement is the claim, and no comparison edge is needed.

A method is a slice like any other, so it generalizes up the `leads-to` ladder exactly as a
claim does: a use of a harness, then microbenchmark, then performance benchmarking. There is
no separate machinery for method use versus method. Same kind, different altitude.

Methods enter the frontier the same way claims do. A claim grounding in a method whose
introducing paper is not curated points at that paper's container `P`. Promote the methods
stub and the grounding sharpens to the method slice it introduced. It is the frontier walk
on the how-axis, with the same machinery as the what-axis.

Still reserved: the bridge from a method to this lab's own `protocols/`, the lab-notebook
cross-link of section 12. It is distinct from the literature-internal how-axis described
here.

---

## 8. Acquisition: descoped

Because first-class papers are human-curated and the human supplies the PDF, the problem of
bulk-fetching paywalled papers evaporates for v1.

- A first-class paper arrives when the human drops the PDF into the external directory. No
  scraping. The paywall is solved by the human already having access and choosing what to
  curate.
- A stub only ever needs bibliographic metadata, which is open through Crossref or
  doi2bib and never paywalled. Cheap and automatic.
- Fetching a PDF by hand at the moment you promote a stub is an optional convenience, not a
  system to build.

---

## 9. Properties that fall out for free

These are how we know the model is right. None of them is a built feature.

- The evidence meter is emergent. A claim's `corroborate` versus `contradict` count is its
  state-of-knowledge balance, for example "5 support, 2 contradict". It is a count of
  lateral edges.
- The walk to root is finite and deterministic. Follow a claim's `leads-to` grounding down,
  into another paper or toward a floor, and repeat until you hit a floor. The chain
  terminates by construction. `corroborate` and `contradict` are lateral and never part of
  the walk. This walk is the speaker-to-listener chain of section 6.1 traversed against the
  flow.
- Grounded versus plausible is emergent. A claim whose walk reaches a floor is established.
  One whose chain dangles in reasoning is visibly plausible.
- Author queries are free once position is an edge attribute on the container: "everything
  where X is corresponding author", "which claims does this group keep contradicting".

---

## 10. Guiding principles

1. **Curation is the rate limiter.** Propose, then accept, edit or reject. Never flood. A
   partial graph is valid, and so is a partial paper. Curation is a single staircase,
   orthogonal to the curated-versus-stub breadth tier of section 5. A paper climbs one rung
   at a time from a bare ingested skeleton, through the abstract, the introduction and
   discussion, the results, and finally the methods, as CURATION.md describes. The breadth
   tier stays emergent from file presence. The depth rung is recorded in one small authored
   field, `pass: 0–4` on the curated paper: 0 ingested, 1 abstract, 2 introduction and
   discussion, 3 results, 4 methods. It is authored because how far curation went is process
   state, not graph structure, and it cannot be reconstructed from the slices. The map from
   reading to slices is lossy both ways: a deep read may add no method slices, and a
   shallow read may opportunistically grab a floor. The rung is both how far the paper was
   read and how mature the card is, one number with no second axis. This is the lone
   exception to "no authored process fields". Stopping early is a normal resting state, not
   an unfinished task.
2. **Generalize, don't merge, and don't duplicate for nesting either.** Never equate two
   claims, since that is lossy. Co-parent them under a broader claim via `leads-to`, so that
   the paper-specific phrasing and quote survive. Conversely, a broader claim earns its
   existence only when at least two children actually share it, or when it is genuinely
   broader than any single child. Never mint a thin claim that merely echoes one. And one
   claim is one slice, refined across passes, never re-extracted per section. Generality
   lives in `leads-to` edges between distinct slices, never in a slice copied to two
   altitudes.
3. **Keep authoring cheap.** This is the constraint that killed the formal academic efforts,
   nanopublications and ORKG: they died on the cost of hand-authoring rigid RDF triples.
   Here an AI drafts claims in natural language and the human only curates. Cheap LLM
   extraction is table stakes, not an advantage; it is what everyone in this space now does
   (section 11). What is distinctive lies downstream of it. The frontier of section 5 is a
   reader-side concept that a publisher curating its own corpus structurally cannot have.
   The quote weld is enforced as a build-failing validation rule rather than a convention
   (SCHEMA section 6, rule 4). And the lab-notebook bridge of section 12 connects a claim to
   the experiment that tests it. The last of those is the durable one.
4. **Lazy, human-paced frontiers.** Citation walking and question capture are selective.
   Exhaustive citation coverage, with every cited paper given an edge, is an ambition, not a
   requirement. The model has no bare paper-to-paper edge; every edge rides a slice or the
   container wildcard, so each one costs a mediating slice. Spend cheaply where it is cheap:
   anchor the citation walls, so that one borrowed claim grounds the whole wall with a single
   `leads-to` into all the papers cited behind it; let methods grounding fall out of pass 3
   for free; reserve `corroborate` and `contradict` for findings that earn them; and leave
   genuinely incidental references as bare stubs. You record what is live for your research.

---

## 11. Prior art and neighbours

### Ideas borrowed

- **Nanopublications.** Atomic assertion plus provenance; the model is almost exactly a
  slice. The lesson is that adoption died on RDF authoring cost, so keep authoring cheap.
- **Open Research Knowledge Graph.** Comparison tables across papers, a future matrix view.
- **scite.** Citations as support or contrast, adopted as the lateral `corroborate` and
  `contradict` edges. Their "mention" is dropped.
- **Consensus.** The agreement meter, here the emergent evidence balance.
- **Elicit.** The literature matrix, a future view.
- **PaperQA2.** The `search → gather_evidence → answer` retrieval loop: the engine that turns
  full text into claims with quotes, and living, cited answers to questions.
- **Zotero Better Notes.** Markdown notes with claim-to-citation traceability inside Zotero.
  The closest existing thing, just not in our interface.

### The 2026 wave: same premise, arrived at independently

Through 2026 several groups converged on this document's starting point: that papers are
narrative artifacts, and that machines need claims welded to evidence. Read this as
validation, not competition. This repo exists because its author needed it, and other people
building the same thing means the problem was real.

- **MIRA** (`mira.science`). The closest relative. Questions, claims, evidence and sources as
  four node types plus typed relations, each record signed by its author.
- **OpenEval.** Booeshaghi, Luebbert and Pachter, *Science should be machine-readable*
  (bioRxiv, 2026, `10.64898/2026.01.30.702911`): claim extraction across the eLife corpus,
  fully automated and benchmarked against human reviewers. The proof that extraction scales.
- **Mainen / HaaK.** Typed propositions and typed logical relations such as "A requires B",
  with invalidity propagation: a floor that fails greys out everything downstream. That view
  is nearly free here, since `leads-to` is already an acyclic ground-to-derived DAG. It is the
  best idea in this list to steal.
- **QED Science**, **preprints.ai**. Claim trees used for review and validity scoring.
- **eLife Pathways.** The publisher-side effort connecting several of the above.

Two things follow. First, where those designs keep node types and status fields, this one
reduced to one primitive and three edges with everything else emergent. That reduction is
the main thing worth contributing back. Second, litgraph sits downstream of them. If a
machine-readable claim format lands upstream, `lit ingest` becomes "fetch the claim tree"
instead of "run an extractor over a PDF". So the ingest boundary stays importable, and
bespoke extraction machinery is deliberately under-invested in.

---

## 12. Out of scope, and questions since resolved

Resolved, and no longer open:

- **The AI–human curation interface** is built. The propose-and-accept rhythm is the pass
  staircase of CURATION.md, and the viewer is the surface it happens on: `lit build` and
  `lit serve`, with `lit preview` rendering a proposition before it is committed. The design
  history is in [docs/](docs/), starting with
  [the visualization design](docs/2026-06-25-visualization-design.md).
- **Question nesting, independent versus anchored,** resolved to independent. Broad questions
  get their own thin `questions/` files, and a claim's `answers` is the only bridge from a
  question to a claim. SCHEMA section 8 records this; it is still retractable.

Genuinely still out of scope:

- **The lab-notebook bridge.** Linking a method to the curator's own experimental protocols,
  and a claim to the experiment that tests it. This is the one direction nobody else in the
  field is building, and it is deliberately not in this repo, because it needs a lab notebook
  on the other end. The literature-internal how-axis is in the core (section 7).
- **Additional views.** Matrix and comparison views, and per-question synthesized answers.

---

## 13. Converged model: one-screen summary

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

---

## 14. History: what this model replaced

The sections above describe the model as it stands. This section records the drafts it
replaced, so a reader who meets an old term in a design doc or a YAML comment can place it.

- **Zotero as the backend.** An earlier draft used it. Dropped. It was too much overhead, with a
  sandbox and an API to fight, for virtually no gain once the semantic layer lived in our
  own YAML. Section 1 is the replacement.
- **Five node types and about fifteen edge types.** Reduced to one primitive, the slice, and
  three edges (sections 2 and 4). The `evidence`, citation `role` and `status` axes dissolved
  into structure; section 3 lists what replaced each.
- **An `evidence` axis on papers** (`novel-data | novel-theory | none`). Gone. Whether a
  claim's `leads-to` chain reaches a floor, and which kind, now answers the same question,
  emergently.
- **A citation `role` enum** (`source | corroborates | contradicts | extends | mentions`).
  Gone. `leads-to` carries grounding, citation and extension, since `source` and `extends`
  were only ever "this grounds that". `corroborate` and `contradict` carry lateral stance.
  `mentions` was dropped outright: a bare "see also" earns no edge.
- **Rollup as a separate edge.** Now generalization, one of the four jobs of `leads-to`.
- **Topics as claims at high altitude.** An early draft folded topics into the claim ladder.
  That was wrong and is retracted: a topic asserts nothing, so every emergent property is
  undefined on it. Topics are now a separate keyword axis (SCHEMA section 9).
- **Question nesting left open.** Resolved to independent; see section 12.
