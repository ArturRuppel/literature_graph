# CURATION — how to read a paper into its local subgraph

**Status:** v1 draft · **Date:** 2026-06-25 · companion to [CONCEPT.md](CONCEPT.md) and [SCHEMA.md](SCHEMA.md)

The model says *what* the graph is (CONCEPT) and *how* it's stored (SCHEMA). This doc is
the **reading protocol**: the structured pass an agent makes over one paper's full text to
*propose* its local subgraph — the affirmations, questions, method-uses and edges of
CONCEPT §5 — for a human to accept / edit / reject.

This is **not a CLI.** Curation is reading comprehension and judgement; only an agent
(reading) plus a human (curating) can do it. The agent proposes by writing into
`curated/<citekey>.yaml`; the human reviews the **git diff** and edits/accepts. Nothing is
"curated" until the human commits it.

## The rhythm (don't forget)

- **Propose, never flood** (CONCEPT §10). A handful of well-welded atoms beats a wall of
  shallow ones. A half-finished paper is a valid, normal state.
- **The quote is the integrity anchor.** Every affirmation is welded to an *exact* quote —
  a verbatim substring of the paper's `.md` full text (SCHEMA §6 rule 8). Never paraphrase
  into a quote. If you can't find the verbatim sentence, the affirmation isn't ready.
- **Generalize, don't merge.** Before creating a `claims/`, `questions/`, or `methods/`
  node, **look** for an existing one to roll up under. Co-parent; never equate two claims.

`lit ingest` has already written the bibliographic skeleton (metadata + authors +
`stubs.yaml` + the `<citekey>.md` full text). Curation fills in the semantic body.

---

## The five passes

A **two-resolution sweep**: the abstract gives a low-res skeleton of the whole local
subgraph; the body passes refine each piece at high-res and weld the quotes. Because
abstract sentences are verbatim-dense, you'll often weld a provisional quote in pass 0 and
merely *confirm* it from the body later.

### Pass 0 — Abstract (skeleton): *question · approach · claims*

Read only the abstract. Draft the condensed whole:

| you find | it becomes |
|---|---|
| the question(s) the paper sets out to answer | draft **Question** nodes (`questions:`) |
| the **approach** (what they did) | a paper-level **`note:`** — orientation, *not* a node (the formal method-uses come in pass 4) |
| the headline claims | draft **Affirmations** (`affirmations:`), provisional quote welded to the abstract sentence |

### Pass 1 — Introduction (refine + context)

| you find | it becomes |
|---|---|
| the sharpened question(s) and their **hierarchy** | **Question** nodes; hierarchy = `rollup` to a broader question (`questions/<slug>.yaml`) |
| "cookie-cutter" framing sentences sitting on citation walls | **Affirmations** with `evidence: none` and `cites` role `source` / `mentions` — one affirmation anchors many stubs (high-value, cheap) |

These context affirmations are *borrowed consensus*: `evidence: none` ⇒ at least one
`source` cite must carry the claim (SCHEMA §6 rule 4).

### Pass 2 — Discussion + abstract (refine the claims)

| you find | it becomes |
|---|---|
| the authors' new insights, backed by their data | **Affirmations**, `evidence: novel-data` (or `novel-theory`), high-altitude — the paper's contribution |
| the insight positioned against prior work | a `cites` role `corroborates` / `contradicts` / `extends` on that affirmation |

These are the "high-level tokens" — the affirmations most likely to roll up to (or become)
broad `claims/` nodes. **Look before creating** the rollup target.

### Pass 3 — Results (weld + ground + judge)

Go through the results **together** (agent + human), relating the data back to the
discussion and intro. This is the reconciliation pass:

| you do | it becomes |
|---|---|
| find the verbatim sentence/figure-caption that grounds each novel claim | the affirmation's exact `quote` (relocated from the abstract weld if a tighter one exists) |
| assign which specific prior paper each finding supports/refutes | the `cites[].role` against the right stub |
| record personal judgement / caveats | a **`note:`** on the affirmation or question — curator voice, *not* quote-bound, never rolled up |

### Pass 4 — Methods (the *how* axis, CONCEPT §7)

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

- **Pass 1, a context sentence** *"…consistent with Ramms et al., keratin-rich cells showed
  elevated cortical tension"* → affirmation `a3`, `evidence: none`, `cites: [{paper:
  Ramms2013Pnas, role: source}]`, rolling up to claim `cytoskeleton-sets-tension`. One
  sentence pulled `Ramms2013Pnas` into the stub frontier.
- **Pass 2/3, a novel finding** → affirmation `a1` (`evidence: novel-data`), welded to
  *"average traction stress increased monotonically…"*, `corroborates` `Jones2018BiophysJ`,
  rolls up `concordant` to `traction-scales-with-stiffness`.
- **Pass 4, the technique** → method-use `m1` (`uses: traction-force-microscopy`, `cites`
  the methods paper `Butler2002AmJPhysiol`), and `a1` gains `via: [m1]` — the data behind
  `a1` was obtained *via* TFM.

---

## When the subgraph is written

The agent writes the proposal into `curated/<citekey>.yaml`; the human reviews the diff and
edits/accepts. A future deterministic check (`lit verify`, the offline twin of `lit
ingest`) will gate it on SCHEMA §6: every quote verbatim, every edge target resolves, ids
unique, enums valid. Until then, the validation rules in SCHEMA §6 are the manual checklist.
