# CURATION — how to read a paper into its local subgraph

**Status:** v2 (lean / slice model) · **Date:** 2026-06-25 · **batch mode added 2026-08-21** · companion to [CONCEPT.md](CONCEPT.md) and [SCHEMA.md](SCHEMA.md)

The model says *what* the graph is (CONCEPT) and *how* it's stored (SCHEMA). This doc is the
**reading protocol**: the structured pass an agent makes over one paper's full text to
*propose* its local subgraph — the **claim / question / method slices** and their edges
(`grounded_in` / `leads_to` · `corroborates` / `contradicts` · `answers`) — for a human to
accept / edit / reject.

This is **not a CLI.** Curation is reading comprehension and judgement; only an agent
(reading) plus a human (curating) can do it. The human is always the gate: the agent
**proposes**, the human **accepts / edits / rejects**, and nothing is "curated" until the human
commits it. What varies is *when* the human is consulted, and there are **two modes**:

- **Interactive** — the human is present, typically with `lit serve` and the paper's card open.
  Each pass is a loop: the agent **explains its reading** in prose at that pass's granularity,
  the two **discuss until they agree**, and *only then* does the agent **tokenize** into
  `curated/<citekey>.yaml`. Realign before the next pass. Use this when the paper is
  load-bearing, when its reading is contested, or when the curator wants to steer granularity
  as it forms.
- **Batch** — the human is not present. A dispatched agent is given **one paper and a target
  pass up front**, climbs to that rung in a single run writing directly into
  `curated/<citekey>.yaml`, and the completed proposition is reviewed afterwards as a **git
  diff**. Agreement moves to the two ends: the target pass is agreed at dispatch, the slices
  are judged on return. This is how a batch of papers is curated in parallel, one agent per
  paper.

Batch trades alignment bandwidth for throughput, and the cost is real: a misjudged reading
surfaces at the end rather than at the pass that produced it, so there is more to reject at
once. Two briefing rules keep it honest. **Tell the agent what the paper is being asked to
support, and instruct it that a finding which *undermines* that is the most valuable thing it
can return** — an agent that only ever confirms has been briefed badly. And **name the specific
question the paper must settle**, so its verdict on that question comes back stated outright
rather than buried in the slices.

## The rhythm (don't forget)

- **Discuss, then tokenize — align after every pass (interactive mode).** Never write slices
  ahead of agreement. Each pass is a loop: *explain your reading at the pass's granularity →
  discuss until aligned → only then weld the agreed slices into the file.* Realign before the
  next pass. **In batch mode this loop collapses to its two ends** — target pass agreed at
  dispatch, whole proposition judged on the git diff — so what follows in this bullet describes
  interactive work.
  **Curation runs from a conventional coding-agent session now, not the retired in-browser
  cockpit** (CLAUDE.md records the move): there is no separate card window to trigger a pass
  from, so the explain step happens in the session's own chat, same as any other pass. The
  `active` worklist (`lit curate` / the viewer's right-click "Curate this paper") still exists,
  but it is now a reading list the human keeps papers on, not a curation-session launcher.
- **Render the proposition, don't just describe it — `lit preview`.** Prose is hard to judge.
  During the *explain* step, write the pass's proposed slices to a **scratch YAML** (the real
  `curated/` schema, held *outside* `curated/`) and run
  `lit preview --scratch <file> --root <data>`: it renders that one paper's local subgraph
  **in isolation** — its slices and every edge, cross-paper endpoints shown as their stub
  chips / synthesis band — using the exact viewer `lit build` ships, so the preview can't
  drift from the final graph. The human judges the card as it'll actually look; only on
  agreement is the scratch draft promoted into `curated/<citekey>.yaml` (that promotion *is*
  the tokenize step). Preview also polishes the focal quotes, so a `quote-flag` warns you at
  proposition time if an anchor isn't verbatim in the `.md`. It's a rendering aid, not a
  shortcut past the reading and judgement — the discussion is still the work.
  - **Where the render must land depends on the human's review surface.** `lit preview
    --scratch` writes a **standalone `dist/preview.html`** — reach for it when there's no `lit
    serve` running, or to see a proposition rendered before it lands in `curated/` at all. When
    `lit serve` **is** running against the data repo, the simpler path is to tokenize straight
    into `curated/<citekey>.yaml` — that edit *is* the proposition — run `lit build` first to
    confirm it validates, then tell the human to refresh the paper's card in the ordinary graph
    viewer (a plain page reload; the card window that used to hot-reload itself on every edit
    was cockpit machinery and is gone). Either way the human accepts / edits / rejects via the
    git diff; revert whatever's rejected before the next pass.
- **Propose, never flood** (CONCEPT §10). A handful of well-welded slices beats a wall of
  shallow ones. **Curation is a single staircase** — a paper climbs it one rung at a time, and
  the rung *is* both how far you read and how mature the card is: there is no second axis.
  **Record the rung reached** as `pass: 0–4` on the curated file: **0** ingested (metadata +
  extracted full text, ready to curate) · **1** abstract (every slice on the card is supported
  by the abstract) · **2** intro + discussion (borrowed claims, graph connections, open
  questions from the discussion) · **3** results (claims sharpened, welded to phrases
  describing the data) · **4** methods (methods read precisely, their citations traced and
  linked — the full sweep). Climb one rung at a time, bumping `pass` as you go — one per
  sitting in interactive mode, or up to the dispatched target in a batch run. Stopping early is
  a normal resting state, not an unfinished task, and a batch target below 4 is a deliberate
  resting place rather than a job left half done. This is the signal the interface
  ranks and renders (the curation circle in `docs/2026-06-25-visualization-design.md`). A stub
  carries no `pass` (breadth stays emergent via file presence, SCHEMA §1). The reading passes
  below **are** these rungs — same numbers, same names.
- **The quote is the integrity anchor.** Every claim is welded to a quote grounded in the
  paper's `.md` full text (SCHEMA §6 rule 4). Verbatim substrings are the default; non-
  contiguous passages may be shortened with `[...]` when the curator explicitly accepts the
  flag. Never paraphrase into a quote. If you can't find the grounded sentence, the claim
  isn't ready.
- **The quote lives in the PDF, not as inline text.** Under `lit serve` the viewer no longer
  prints the weld — hovering a claim pops its PDF page with the sentence highlighted, clicking
  pins it. The highlight comes from `quote_loc` (SCHEMA §6): run **`lit locate`** once to
  resolve every quote's place in its PDF (full-coverage word-geometry match) and store it in
  the YAML; review the diff and commit. Quotes without a stored location fall back to a live
  resolve. `quote_loc` is derived-and-regenerable (re-run `lit locate --force` any time), not a
  hand-authored judgement.
- **Generalize, don't merge — and don't duplicate for nesting.** Before creating a broad
  `claims/`, `questions/`, or `methods/` node, **look** for an existing one to `leads_to`;
  co-parent, never equate two claims. A broad target earns its existence only when **≥2
  children share it** (or it's genuinely broader than any one child). One claim is **one
  slice, refined across passes**, not re-extracted per section.

`lit ingest` has already written the bibliographic skeleton (metadata + authors +
`stubs.yaml` + the `<citekey>.md` full text). Curation fills in the semantic body.

---

## The passes (the rungs of the staircase)

**Pass 0 is the ingested starting line**, not a reading step: `lit ingest` has written the
bibliographic skeleton (metadata + authors + `stubs.yaml` + the `<citekey>.md` full text) and
no slices yet. Curation climbs from there. A paper speaks in **three registers**, and the
reading passes follow *that*, not the section order:

- **Words** (abstract · intro · discussion) — what the authors *claim*, how they *frame* it,
  and *how they found out*. The abstract is the low-res skeleton (Pass 1); intro and
  discussion are the full-res version and are **two halves of one move** (intro sets the
  claims up, discussion cashes them in), read together as one **framing** pass (Pass 2).
- **Evidence** (results) — grounds each headline claim in the specific method(s) and data,
  and surfaces new sub-claims (Pass 3).
- **Approach** (methods) — *refines* the method DAG and traces its citation provenance (Pass 4).

So: Pass 0 *ingested* · Pass 1 *the gist* · Pass 2 *what they claim* · Pass 3 *what backs it* ·
Pass 4 *the method detail*. Because abstract sentences are verbatim-dense, you'll often weld a
provisional quote in Pass 1 and merely *confirm or relocate* it from the results later.

Each pass runs as **explain → discuss → align → tokenize** in interactive mode. In batch mode
the agent climbs the rungs in order without pausing, and the whole climb is judged at the end;
the rungs still have to be climbed in sequence, because each one refines the slices the previous
one wrote rather than appending beside them. The tables say *what* each pass yields; in
interactive mode they are the targets of that discussion, not a license to write before you
agree.

### Pass 1 — Abstract: *question · claims · methods*

Read only the abstract. The abstract states the approach, so **the methods come out here** —
as floor-slices the headline claims can immediately ground in (no deferral):

| you find | it becomes |
|---|---|
| the question(s) the paper sets out to answer | draft **Question** slices (`questions:`) |
| the **approach** (measurements, models) | **Method** slices (`methods:`) — a measurement is a *floor*; a model `grounded_in` the measurements it consumes (CONCEPT §7) |
| the headline claims | **Claim** slices (`claims:`), provisional quote welded to the abstract sentence, `grounded_in` the relevant method floors, `answers` the question they resolve |
| the authors' **keyword line** (sits under the abstract) | proposed **`tags`** — *not slices*: a container filter axis (SCHEMA §4), welded to nothing, no evidential weight. Run `lit tag <key> --suggest` to scrape and kebab-case the line from the full text; it prints candidates and a ready `lit tag` command, **writes nothing** — you accept the ones worth keeping. Author lists are often three broad words a journal required, so gate them by hand |

### Pass 2 — Framing: intro + discussion together (the words)

Read intro and discussion as **one pass** — two halves of one move. This is everything the
authors *claim* and how they *position* it; the data that backs each claim waits for Pass 3.

| you find | it becomes |
|---|---|
| the sharpened question(s) and their **hierarchy** | **Question** slices, `q1`, `q2` …; hierarchy = `leads_to` a broader question (`questions/<slug>.yaml`) |
| the questions the paper **raises and leaves open** — "future work," "it remains unclear whether," "an open question is" (mostly discussion) | **open Question** slices (`questions:`), **id `oq1`, `oq2` …**, each **welded to the verbatim sentence that raises it** (a `quote`, exactly like a claim — the `text` is your interrogative rephrasing, the `quote` the declarative source) so it's verifiable and findable in the PDF; but **left floating** as edges go — no `answers`, no anchor to the finding that provoked them. *Go looking for these:* the birds-eye "what does this paper leave unanswered" is easy to miss when reading for what the authors claim |
| framing sentences sitting on citation walls (mostly intro) | **borrowed Claim** slices, **id `b1`, `b2` …** — `grounded_in` the cited papers (a citation, not a floor); restatements (CONCEPT §6.1) |
| the authors' headline insights (mostly discussion) | **Claim** slices at high altitude, `c1`, `c2` … — the paper's contribution; `grounded_in` a method floor (or a premise claim, for a theory claim) |
| **methods named in the body but not the abstract** (the intro's "we measured … with", the discussion's model) | new **Method** floor slices, and coarse `grounded_in` on the Pass-1 claims sharpened to point at them — the abstract rarely names every technique; the rest surface here (their DAG + provenance still wait for Pass 4) |
| an insight positioned against prior work | `corroborates` / `contradicts` on that claim (lateral) |
| the broad claims **≥2 claims** ladder up into | `claims/<slug>` `leads_to` targets — **look before creating**; a single child gets no broad twin |

**Two of the ids carry your reading (SCHEMA §3).** Pass 2 is where `b` and `oq` first appear,
because pass 2 is the pass that produces borrowed claims and open questions. `b` = "this is a
restatement off a citation wall," `c` = "this is the paper's own." `oq` = "the paper raises this
and walks away," `q` = "the paper set out to answer this." **Each prefix counts separately** —
`c1 b1 c2 c3 b2` down the file, in reading order — so a claim keeps its id when a later pass adds
slices around it. If you cannot decide between `b` and `c`, that hesitation is usually the
signal that the sentence is doing two jobs and wants splitting into two slices.

The prefix is a *label on your judgement*, not a substitute for the edges: a `b*` claim still
needs its citations in `grounded_in` — the generator computes "borrowed" from those, and reads
no prefix anywhere. Where the two disagree, chase it. And an `oq` that a later paper answers
**keeps its `oq` id** — the id says what this paper left open, the emergent flag says what the
library still has open, and those are meant to come apart.

**Map the walls (cheap-complete).** Anchoring each citation wall to one borrowed claim is the
cheapest way to give many stubs an edge at once: **every paper the authors cite behind the
claim goes into its `grounded_in`** — read the role from the *citing* sentence, trust their
grouping, don't re-check whether each cite truly confirms (out of scope). A borrowed claim
grounds in citations only (no floor) → it reads as a *restatement*, "plausible" until its
sources are curated. This is the *cheap tier* of the exhaustive-is-an-ambition policy
(CONCEPT §10.4); lateral `corroborates`/`contradicts` are drafted here from the authors'
words and **confirmed against the data in Pass 3**.

**Open questions stay unwired here.** Weld each to its verbatim source sentence (the `quote`,
then `lit locate` for the PDF highlight — same as a claim) and stop. Do *not* connect them by
edge — no anchor to the finding that raised them, no link to a claim elsewhere that answers
them. Those connections are made in the **meta read**, a separate cross-library pass that takes
a birds-eye view over the whole graph; per-paper curation just deposits the open question as a
floating-but-welded slice. An open question so left renders in its own **"open questions"**
section at the bottom of the paper's card (the viewer buckets it by the emergent open flag),
and closes on its own the day some paper's claim `answers` it.

### Pass 3 — Results: ground the claims in data

Go through the results **together** (agent + human), relating the data back to the framing.
This is where each headline claim is grounded in evidence:

| you do | it becomes |
|---|---|
| find the verbatim sentence / figure-caption that grounds each claim | the claim's exact `quote` (relocated from the Pass-1/2 weld if a tighter one exists) |
| confirm which specific method(s) produced each finding | sharpen the claim's `grounded_in` from the coarse Pass-1 set to the precise floors |
| a result that's its own finding, not in the framing | a **new sub-claim** Claim, welded to its result sentence |
| confirm which specific prior paper each finding supports/refutes | the right `corroborates` / `contradicts` ref |
| record judgement / caveats | a **`note:`** on the slice — curator voice, *not* quote-bound, never an edge |

### Pass 4 — Methods: refine the *how* DAG (CONCEPT §7)

The method floors were born in Pass 1; here you refine them:

| you find | it becomes |
|---|---|
| which method layers on which (a model consumes a measurement) | `grounded_in` edges *between* methods (`m_model grounded_in [m_measurement, …]`) |
| the methods paper that introduced each technique | that method's `grounded_in: [<citekey>]` — pulls the methods paper into the frontier exactly like a claim's citation |

A method `quote` is **optional** — methods prose is boilerplate; its `grounded_in` provenance
is the payload.

---

## Worked example (Chen2021Sys, the lean encoding)

Threaded through [`curated/Chen2021Sys.yaml`](example/) — see the data root:

- **Pass 1, the approach → method floors.** The abstract's *"a microbenchmark harness … an
  open-network queueing model"* becomes `m1` (the harness — a measurement floor,
  `grounded_in: [Bench2016Tools]`) and `m2` (the queueing model, `grounded_in: [m1]` — a model
  layered on the measurement). A headline result becomes `c1`, `grounded_in: [m1]`.
- **Pass 2 (framing), a context sentence** *"…memory bandwidth bounds the latency floor of a
  pipeline"* → borrowed claim `b1`, `grounded_in: [Patel2017Vldb]` — one sentence pulls a stub
  into the frontier (no floor → a restatement) and `answers: [q1]`. The open question the paper
  walks away from is `oq1`, welded but unwired. Consensus that generalizes
  gets a `leads_to`: `c1` → `throughput-scales-with-batching`, which earns its broad claim once
  a second paper (`Kumar2020Net:c1`) shares it (≥2 children).
- **Pass 3 (results)** sharpens each claim's `grounded_in` to the exact methods
  (`c3 grounded_in [c1, m2]` — the measured trend compared against the model) and relocates each
  quote to the tightest results sentence.
- **Pass 4 (methods)** records the method DAG (`m2 grounded_in [m1]`) and each technique's
  introducing paper (`m1 grounded_in [Bench2016Tools]`).

---

## When the subgraph is written

The agent writes the proposal into `curated/<citekey>.yaml`; the human reviews the diff and
edits/accepts. A future deterministic check (`lit verify`, the offline twin of `lit ingest`)
will gate it on SCHEMA §6: every quote grounded (verbatim by default; `[...]` flagged),
every ref resolves, ids unique, no emergent fields authored, enums valid. Until then,
SCHEMA §6 is the manual checklist.
