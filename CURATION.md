# CURATION — how to read a paper into its local subgraph

**Status:** v1 draft · **Date:** 2026-06-25 · companion to [CONCEPT.md](CONCEPT.md) and [SCHEMA.md](SCHEMA.md)

The model says *what* the graph is (CONCEPT) and *how* it's stored (SCHEMA). This doc is
the **reading protocol**: the structured pass an agent makes over one paper's full text to
*propose* its local subgraph — the affirmations, questions, method-uses and edges of
CONCEPT §5 — for a human to accept / edit / reject.

This is **not a CLI.** Curation is reading comprehension and judgement; only an agent
(reading) plus a human (curating) can do it. It is **interactive and discussion-first**: in
each pass the agent **first explains its reading** of the paper in prose, at that pass's
granularity, and the two **discuss until they agree** — *only then* does the agent
**tokenize**, writing the agreed nodes into `curated/<citekey>.yaml`. The human reviews the
**git diff** and edits/accepts. Nothing is "curated" until the human commits it.

## The rhythm (don't forget)

- **Discuss, then tokenize — align after every pass.** Never write nodes ahead of agreement.
  Each pass is a loop: *explain your reading at the pass's granularity → discuss until
  aligned → only then weld the agreed atoms into the file.* Realign before the next pass.
- **Propose, never flood** (CONCEPT §10). A handful of well-welded atoms beats a wall of
  shallow ones. **Curation has depth tiers** — a paper may stop at Pass 0, Pass 1, or run
  all the way to Pass 3; stopping early is a normal resting state, not an unfinished task.
- **The quote is the integrity anchor.** Every affirmation is welded to an *exact* quote —
  a verbatim substring of the paper's `.md` full text (SCHEMA §6 rule 8). Never paraphrase
  into a quote. If you can't find the verbatim sentence, the affirmation isn't ready.
- **Generalize, don't merge — and don't duplicate for nesting.** Before creating a `claims/`,
  `questions/`, or `methods/` node, **look** for an existing one to roll up under; co-parent,
  never equate two claims. A rollup target earns its existence only when **≥2 children share
  it** (or it's genuinely broader than any one child) — never mint a thin claim that echoes a
  single affirmation. One claim is **one node, refined across passes**, not re-extracted per
  section.

`lit ingest` has already written the bibliographic skeleton (metadata + authors +
`stubs.yaml` + the `<citekey>.md` full text). Curation fills in the semantic body.

---

## The four passes

A paper speaks in **three registers**, and the passes follow *that*, not the section order:

- **Words** (abstract · intro · discussion) — what the authors *claim* and how they *frame*
  it. The abstract is the low-res skeleton (Pass 0); intro and discussion are the full-res
  version and are **two halves of one move** (intro sets the claims up, discussion cashes
  them in), so they're read together as one **framing** pass (Pass 1).
- **Evidence** (results) — pins each claim to a measurement, figure, or argument, and
  surfaces any new sub-claims (Pass 2).
- **Approach** (methods) — pins the claims to the techniques that produced them (Pass 3).

So: Pass 0 *the gist* · Pass 1 *what they claim* · Pass 2 *what backs it* · Pass 3 *how they
did it*. Because abstract sentences are verbatim-dense, you'll often weld a provisional quote
in Pass 0 and merely *confirm or relocate* it from the results later.

Each pass runs as **explain → discuss → align → tokenize**: talk through your reading first,
converge with the human, and only then weld the agreed nodes into the file. The tables below
say *what* each pass yields; they are the targets of that discussion, not a license to write
before you agree.

### Pass 0 — Abstract (skeleton): *question · approach · claims*

Read only the abstract. Draft the condensed whole:

| you find | it becomes |
|---|---|
| the question(s) the paper sets out to answer | draft **Question** nodes (`questions:`) |
| the **approach** (what they did) | a paper-level **`note:`** — orientation, *not* a node (the formal method-uses come in Pass 3) |
| the headline claims | draft **Affirmations** (`affirmations:`), provisional quote welded to the abstract sentence |

### Pass 1 — Framing: intro + discussion together (the words)

Read intro and discussion as **one pass** — they're two halves of one move, and either alone
is half the picture. This is everything the authors *claim* and how they *position* it; the
data that backs each claim waits for Pass 2.

| you find | it becomes |
|---|---|
| the sharpened question(s) and their **hierarchy** | **Question** nodes; hierarchy = `rollup` to a broader question (`questions/<slug>.yaml`) |
| framing sentences sitting on citation walls (mostly intro) | **context Affirmations** (`ca*`, `evidence: none`) — borrowed consensus |
| the authors' headline insights (mostly discussion) | **Affirmations** (`a*`) at high altitude — the paper's contribution; `evidence: novel-data` / `novel-theory` per how the authors cast it |
| an insight positioned against prior work | a `cites` role `corroborates` / `contradicts` / `extends` on that affirmation |
| the broad claims **≥2 affirmations** ladder up into | `claims/<slug>` rollup targets — **look before creating**; a single child gets no claim twin |

Context affirmations are *borrowed consensus*: `evidence: none` ⇒ at least one `source` cite
must carry the claim (SCHEMA §6 rule 4).

**Map the walls (cheap-complete).** Anchoring each citation wall to one affirmation is the
cheapest way to give many stubs an edge at once: **every paper the authors cite behind the
claim becomes a `source`** — read the role from the *citing* sentence, trust their grouping,
and don't re-check whether each cite truly confirms (out of scope). Reserve `mentions` for
citations that *don't* back an asserted claim — neutral pointers like "a tool that does X" or
a catalogue of "other labs have done Y." Do this across the whole intro. This is the *cheap
tier* of the exhaustive-is-an-ambition policy (CONCEPT §10.4); the rich roles
(`corroborates` / `contradicts` / `extends`) are drafted here from the authors' words and
**confirmed against the data in Pass 2**.

### Pass 2 — Results: pin the claims to data

Go through the results **together** (agent + human), relating the data back to the framing.
This is where the framed claims get grounded in evidence:

| you do | it becomes |
|---|---|
| find the verbatim sentence / figure-caption that grounds each novel claim | the affirmation's exact `quote` (relocated from the Pass-0/1 weld if a tighter one exists) |
| a result that's its own finding, not captured in framing | a **new sub-claim** Affirmation, welded to its result sentence |
| confirm which specific prior paper each finding supports/refutes | the `cites[].role` against the right stub |
| record judgement / caveats | a **`note:`** on the affirmation or question — curator voice, *not* quote-bound, never rolled up |

### Pass 3 — Methods: pin the claims to the approach (the *how* axis, CONCEPT §7)

| you find | it becomes |
|---|---|
| each technique the paper applied | a **Method-use** in `methods:` — `uses:` a `methods/<slug>` node (look before creating), `cites` (role `source`) the methods paper that introduced it |
| which novel-data finding rests on which technique | a `via: [m1, …]` on that affirmation — the **braid**, *"we found X via T"* |

A method-use's `quote` is **optional** — methods prose is boilerplate; the `cites` to the
methods paper is the payload, and it pulls that paper into the frontier exactly like an
affirmation's source cite.

---

## Worked example (one intro sentence → its subgraph)

Threaded through [`example/curated/Ruppel2023NatPhys.yaml`](example/curated/Ruppel2023NatPhys.yaml):

- **Pass 1 (framing), a context sentence** *"…consistent with Ramms et al., keratin-rich
  cells showed elevated cortical tension"* → affirmation `ca1` (context id `ca*`, SCHEMA §3),
  `evidence: none`, `cites: [{paper: Ramms2013Pnas, role: source}]`, rolling up to claim
  `cytoskeleton-sets-tension`. One sentence pulled `Ramms2013Pnas` into the stub frontier.
- **Pass 2 (results), a novel finding** → affirmation `a1` (`evidence: novel-data`), welded
  to *"average traction stress increased monotonically…"*, `corroborates` `Jones2018BiophysJ`,
  rolls up `concordant` to `traction-scales-with-stiffness`.
- **Pass 3 (methods), the technique** → method-use `m1` (`uses: traction-force-microscopy`,
  `cites` the methods paper `Butler2002AmJPhysiol`), and `a1` gains `via: [m1]` — the data
  behind `a1` was obtained *via* TFM.

---

## When the subgraph is written

The agent writes the proposal into `curated/<citekey>.yaml`; the human reviews the diff and
edits/accepts. A future deterministic check (`lit verify`, the offline twin of `lit
ingest`) will gate it on SCHEMA §6: every quote verbatim, every edge target resolves, ids
unique, enums valid. Until then, the validation rules in SCHEMA §6 are the manual checklist.
