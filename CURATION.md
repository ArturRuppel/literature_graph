# CURATION — how to read a paper into its local subgraph

**Status:** v2 (lean / slice model) · **Date:** 2026-06-25 · companion to [CONCEPT.md](CONCEPT.md) and [SCHEMA.md](SCHEMA.md)

The model says *what* the graph is (CONCEPT) and *how* it's stored (SCHEMA). This doc is the
**reading protocol**: the structured pass an agent makes over one paper's full text to
*propose* its local subgraph — the **claim / question / method slices** and their edges
(`grounded_in` / `leads_to` · `corroborates` / `contradicts` · `answers`) — for a human to
accept / edit / reject.

This is **not a CLI.** Curation is reading comprehension and judgement; only an agent
(reading) plus a human (curating) can do it. It is **interactive and discussion-first**: in
each pass the agent **first explains its reading** in prose, at that pass's granularity, and
the two **discuss until they agree** — *only then* does the agent **tokenize**, writing the
agreed slices into `curated/<citekey>.yaml`. The human reviews the **git diff** and
edits/accepts. Nothing is "curated" until the human commits it.

## The rhythm (don't forget)

- **Discuss, then tokenize — align after every pass.** Never write slices ahead of agreement.
  Each pass is a loop: *explain your reading at the pass's granularity → discuss until
  aligned → only then weld the agreed slices into the file.* Realign before the next pass.
- **Propose, never flood** (CONCEPT §10). A handful of well-welded slices beats a wall of
  shallow ones. **Curation has depth tiers** — a paper may stop at Pass 0, Pass 1, or run all
  the way to Pass 3; stopping early is a normal resting state, not an unfinished task.
- **The quote is the integrity anchor.** Every claim is welded to an *exact* quote — a
  verbatim substring of the paper's `.md` full text (SCHEMA §6 rule 4). Never paraphrase into
  a quote. If you can't find the verbatim sentence, the claim isn't ready.
- **Generalize, don't merge — and don't duplicate for nesting.** Before creating a broad
  `claims/`, `questions/`, or `methods/` node, **look** for an existing one to `leads_to`;
  co-parent, never equate two claims. A broad target earns its existence only when **≥2
  children share it** (or it's genuinely broader than any one child). One claim is **one
  slice, refined across passes**, not re-extracted per section.

`lit ingest` has already written the bibliographic skeleton (metadata + authors +
`stubs.yaml` + the `<citekey>.md` full text). Curation fills in the semantic body.

---

## The four passes

A paper speaks in **three registers**, and the passes follow *that*, not the section order:

- **Words** (abstract · intro · discussion) — what the authors *claim*, how they *frame* it,
  and *how they found out*. The abstract is the low-res skeleton (Pass 0); intro and
  discussion are the full-res version and are **two halves of one move** (intro sets the
  claims up, discussion cashes them in), read together as one **framing** pass (Pass 1).
- **Evidence** (results) — grounds each headline claim in the specific method(s) and data,
  and surfaces new sub-claims (Pass 2).
- **Approach** (methods) — *refines* the method DAG and its provenance (Pass 3).

So: Pass 0 *the gist* · Pass 1 *what they claim* · Pass 2 *what backs it* · Pass 3 *the method
detail*. Because abstract sentences are verbatim-dense, you'll often weld a provisional quote
in Pass 0 and merely *confirm or relocate* it from the results later.

Each pass runs as **explain → discuss → align → tokenize**. The tables say *what* each pass
yields; they are the targets of that discussion, not a license to write before you agree.

### Pass 0 — Abstract (skeleton): *question · claims · methods*

Read only the abstract. The abstract states the approach, so **the methods come out here** —
as floor-slices the headline claims can immediately ground in (no deferral):

| you find | it becomes |
|---|---|
| the question(s) the paper sets out to answer | draft **Question** slices (`questions:`) |
| the **approach** (measurements, models) | **Method** slices (`methods:`) — a measurement is a *floor*; a model `grounded_in` the measurements it consumes (CONCEPT §7) |
| the headline claims | **Claim** slices (`claims:`), provisional quote welded to the abstract sentence, `grounded_in` the relevant method floors, `answers` the question they resolve |

### Pass 1 — Framing: intro + discussion together (the words)

Read intro and discussion as **one pass** — two halves of one move. This is everything the
authors *claim* and how they *position* it; the data that backs each claim waits for Pass 2.

| you find | it becomes |
|---|---|
| the sharpened question(s) and their **hierarchy** | **Question** slices; hierarchy = `leads_to` a broader question (`questions/<slug>.yaml`) |
| framing sentences sitting on citation walls (mostly intro) | **borrowed Claim** slices — `grounded_in` the cited papers (a citation, not a floor); emergently "restatements" (CONCEPT §6.1) |
| the authors' headline insights (mostly discussion) | **Claim** slices at high altitude — the paper's contribution; `grounded_in` a method floor (or a premise claim, for a theory claim) |
| an insight positioned against prior work | `corroborates` / `contradicts` on that claim (lateral) |
| the broad claims **≥2 claims** ladder up into | `claims/<slug>` `leads_to` targets — **look before creating**; a single child gets no broad twin |

**Map the walls (cheap-complete).** Anchoring each citation wall to one borrowed claim is the
cheapest way to give many stubs an edge at once: **every paper the authors cite behind the
claim goes into its `grounded_in`** — read the role from the *citing* sentence, trust their
grouping, don't re-check whether each cite truly confirms (out of scope). A borrowed claim
grounds in citations only (no floor) → it reads as a *restatement*, "plausible" until its
sources are curated. This is the *cheap tier* of the exhaustive-is-an-ambition policy
(CONCEPT §10.4); lateral `corroborates`/`contradicts` are drafted here from the authors'
words and **confirmed against the data in Pass 2**.

### Pass 2 — Results: ground the claims in data

Go through the results **together** (agent + human), relating the data back to the framing.
This is where each headline claim is grounded in evidence:

| you do | it becomes |
|---|---|
| find the verbatim sentence / figure-caption that grounds each claim | the claim's exact `quote` (relocated from the Pass-0/1 weld if a tighter one exists) |
| confirm which specific method(s) produced each finding | sharpen the claim's `grounded_in` from the coarse Pass-0 set to the precise floors |
| a result that's its own finding, not in the framing | a **new sub-claim** Claim, welded to its result sentence |
| confirm which specific prior paper each finding supports/refutes | the right `corroborates` / `contradicts` ref |
| record judgement / caveats | a **`note:`** on the slice — curator voice, *not* quote-bound, never an edge |

### Pass 3 — Methods: refine the *how* DAG (CONCEPT §7)

The method floors were born in Pass 0; here you refine them:

| you find | it becomes |
|---|---|
| which method layers on which (a model consumes a measurement) | `grounded_in` edges *between* methods (`m_model grounded_in [m_measurement, …]`) |
| the methods paper that introduced each technique | that method's `grounded_in: [<citekey>]` — pulls the methods paper into the frontier exactly like a claim's citation |

A method `quote` is **optional** — methods prose is boilerplate; its `grounded_in` provenance
is the payload.

---

## Worked example (Ruppel2023eLife, the lean encoding)

Threaded through [`curated/Ruppel2023eLife.yaml`](example/) — see the data root:

- **Pass 0, the approach → method floors.** The abstract's *"optogenetic activation … traction
  and monolayer stress microscopy … continuum model"* becomes `m1` (opto), `m2` (TFM), `m3`
  (MSM, `grounded_in: [m2]` — layers on traction), `m5` (continuum model, `grounded_in: [m3,
  …]` — a model on the measurement). A headline result becomes `c1`, `grounded_in: [m1, m3,
  m5]` (perturbation + stress data, compared against the model) and `answers: [q1]`.
- **Pass 1 (framing), a context sentence** *"…cells probe the mechanical and geometrical
  properties of their environment"* → borrowed claim `c4`, `grounded_in:` the twelve cited
  papers — one sentence pulled twelve stubs into the frontier (no floor → a restatement).
  Borrowed consensus that joins a headline claim gets a `leads_to`: `c7`, `c8` →
  `force-propagation-is-active`, alongside the novel `c1` (≥2 children earn the broad claim).
- **Pass 2 (results)** sharpens `c1`'s `grounded_in` to the exact methods and relocates its
  quote to the tightest results sentence.
- **Pass 3 (methods)** records the method DAG (`m3 grounded_in [m2]`, `m5 grounded_in [m3]`)
  and each technique's introducing paper.

---

## When the subgraph is written

The agent writes the proposal into `curated/<citekey>.yaml`; the human reviews the diff and
edits/accepts. A future deterministic check (`lit verify`, the offline twin of `lit ingest`)
will gate it on SCHEMA §6: every quote verbatim, every ref resolves, ids unique, no emergent
fields authored, enums valid. Until then, SCHEMA §6 is the manual checklist.
