# Programme graph — tokenizing a research programme on the slice model

**Status:** design · **Date:** 2026-08-02 · extends [CONCEPT.md](../CONCEPT.md) + [SCHEMA.md](../SCHEMA.md)

The literature graph tokenizes what *is known*. This extends the same primitive to what is
*proposed* — a research programme: hypotheses, the experiments that would settle them, the
capabilities that make those experiments possible, and the objections already raised against
them. A grant application is then one **linearization** of the programme, not the object itself.

Three decisions taken up front, and the design is bound by them:

1. **Clean v2.** The graph starts at the stress/rheology framing. The v1 jamming/shape-index
   proposal is not imported as a historical layer.
2. **No prose.** The graph never generates proposal text. The weld runs text → graph, as a
   check; never graph → text.
3. **No fork.** Programme node kinds live in `litgraph`, and the programme tree lives inside
   the existing data repo beside `curated/`. One root, one build, one graph.

---

## 1. What the paper model cannot express

| Paper model | Programme |
|---|---|
| a claim bottoms out in a measurement that **happened** | the spine bottoms out in an experiment that **hasn't** |
| ungrounded ⇒ *merely plausible*, a defect | the central hypothesis **must** dangle — that is the ask |
| feasibility is invisible (the work is done) | "can *this* lab do it" is an orthogonal, equally-scored axis |
| lateral stance holds between two **grounded** claims that collide | the alternatives are **both ungrounded**, and a planned test separates them |
| container = the paper | container must **not** be the section — separating the DAG from the narrative is the whole point |

Everything below is the smallest set of additions that fixes those five rows.

---

## 2. Node kinds — two new, and three refusals

**New:**

| Kind | id | Is | Floor? |
|---|---|---|---|
| **Test** | `t1`… | a *planned* measurement that would settle something — a specific application of Methods, not a technique | a **hollow floor**: it terminates a grounding chain, but marks it *proposed*, not established |
| **Capability** | `k1`… | a thing that makes a Test possible — an instrument, a line, a pipeline, a collaborator's model | never; it grounds in the evidence that it exists (§8) |

**Reused unchanged:** **Claim** (`c*`), **Question** (`q*`), **Method** (`m*`). A Method is still
the *technique* (TFM, MSM, optoRhoA); a Test is a specific planned *use* of techniques to
separate two hypotheses. The distinction is the same one the lit model already draws between a
method-use and the method ladder — same kind, different altitude — so it needs no new machinery.

**Three things that were candidates and are refused,** because they are emergent:

- **Assumption** — a claim that something depends on and no Test points at. That is a *shape in
  the graph* (`in-degree ≥ 1`, no incoming `discriminates`), not a node kind. Detecting it is
  the single most valuable query in §8; making it authored would let it be forgotten.
- **Risk** — the same node, read by consequence. "If this is false, what breaks" is the
  dependent set. No node.
- **Mitigation** — a Test that discriminates the assumption. No node.

Worked: *"vimentin and actomyosin are orthogonal"* is a claim, load-bearing (the two-knob phase
diagram grounds in it), with no Test → the graph flags it. Adding the opto-clamp as a Test that
`discriminates` it and its negation clears the flag. The caveat, the risk and the contingency
that a proposal writes as three paragraphs are one claim and one edge.

---

## 3. Edges — two new (five total)

```
discriminates    Test → [Claim, Claim, …]   (≥2 targets)  the experiment separates these alternatives
enabled_by       Test → Capability                         the feasibility axis
```

- **`discriminates` is the epistemic core of a proposal.** `grounded_in` says *"this claim will
  rest on that test"*; it cannot say *"and that test kills the alternative."* Two claims both
  grounding in `t1` are not thereby alternatives. Hence a separate edge, authored on the Test,
  targeting **≥2** claims. A single-target `discriminates` is a validation error with a pointed
  message: author it as the claim's `grounded_in: t1` instead. (This is the same shape as the
  existing "cross-paper `leads_to` → author as `grounded_in`" error.)
- **`enabled_by` is deliberately not `grounded_in`.** A grant is scored on two independent axes:
  is it true and important, and can *you* do it. Folding capability into grounding merges them
  and destroys the only query that matters on the second axis — *which aim rests on a capability
  I do not yet have.*

Unchanged and reused: `leads-to` (`grounded_in` ⟂ `leads_to`), `answers`, `corroborate` /
`contradict`. A programme claim restating the literature grounds in a lit slice
(`grounded_in: Fuhs2022NatPhys:c3`) — that is already the model's *borrowed* case, no new
concept.

---

## 4. The container is the aim — and only the aim

**Aim** — `programme/aims/<slug>.yaml`: a coherent bundle of hypothesis, predictions, tests,
capabilities and open questions. It is the container because it is the **unit of curation** —
one session, one aim, one clean diff — which is SCHEMA §1's cardinal rule. It is emphatically
*not* a LaTeX section: §2.3 may present half of Aim 1 and a slice of Aim 2. That divorce is the
payoff (§8).

### 4.1 Feedback is a source of nodes, never a node

Reviewer comments do **not** get containers. Feedback is ephemeral: it exists to produce the
next version and is spent the moment it does. Giving it nodes would make the graph accrete dead
objections from every round of every application, and would smuggle dated process state into a
model that refuses `status` fields on exactly that principle.

So **reading a critique is a curation session, not a curation target.** Mine it for what
survives on its own merit, phrase that as programme content, discard the document:

| Comment | Becomes |
|---|---|
| "Fig. 2B doesn't show rigidity" | nothing — a new figure, then it's spent |
| "where could stably graded mechanics come from in vivo?" | a **Question** on the aim |
| "the soft-cells-in-stiff-tumour paradox could be ECM, not cells" | a **rival Claim**, and a Test that `discriminates` it from ours |
| "parameter count depends on ingredients, not on the model" | a **Claim**, grounded on its own merits |

Such questions carry no `quote` — nothing durable to weld to. SCHEMA §4 already permits this: a
purely synthesized question has no verbatim anchor, and a reviewer's point adopted as your own
open question is synthesized.

**What this deliberately gives up:** "which of Aleksi's comments did I silently drop" is no
longer answerable from the graph. That is a revision checklist, and it belongs wherever a
revision round is tracked — not in the durable model.

**The join.** Programme claims `leads_to` the **same** thin broad nodes the papers already use.
The v2 central hypothesis ladders into `claims/tissue-material-state-is-emergent.yaml`, which
already has paper children. The programme therefore hangs off the literature graph at the broad
layer rather than sitting beside it — and `claims/tissue-operates-at-jamming-criticality.yaml`,
the v1 framework, becomes visibly a broad claim the programme no longer feeds. That is what
"clean v2" looks like in the graph.

---

## 5. Ref grammar — the one real constraint

`classify_ref` reads a ref's meaning off its **form**. Today: `c1` local · `Chen2021Sys`
container (`^[A-Z][A-Za-z]*\d{4}[A-Za-z]`) · `foo-bar` broad slug · `X:c1` sharpened. A
programme container named `fluid-solid-switch` would be indistinguishable from a broad slug.

**One sigil resolves it:** a programme container is `@<slug>`, a sharpened programme slice is
`@<slug>:t2`. One regex branch, no ambiguity with any existing form, and every downstream
consumer (validation, viewer, build) keeps reading meaning off the form.

| form | refers to |
|---|---|
| `t1`, `k2`, `c3` | local slice in the same file |
| `@fluid-solid-switch` | a programme container (wildcard — "some slice in here") |
| `@fluid-solid-switch:c1` | a sharpened programme slice |
| `Fuhs2022NatPhys:c3` | a literature slice (the citation join) |
| `tissue-material-state-is-emergent` | a thin broad node, shared with the literature |

---

## 6. File layout

```
<data root>/
  curated/  claims/  questions/  methods/  stubs.yaml     # unchanged — the literature
  programme/
    aims/       <slug>.yaml      # the only container: claims · questions · tests · capabilities
    narrative/  <grant>.yaml     # ordering layer, §7 — one per application
```

The data repo is no longer purely literature. A rename is arguably owed; not now.

---

## 7. Fields

**Aim** — `programme/aims/<slug>.yaml`

| Field | Req | Notes |
|---|---|---|
| `title` | ✔ | |
| `claims` / `questions` / `tests` / `capabilities` / `methods` | – | the slices; absent is valid |
| `note`, `tags` | – | as on a curated paper |

No `pass`. Curation depth is a reading protocol for a document that already exists; an aim is
authored, not read.

**Claim** — as SCHEMA §4, with one change: **`quote` is optional.** A programme claim is the
curator's own assertion, not an extraction. When the v2 LaTeX exists, `quote` welds the claim to
the sentence in the proposal that states it — which is how decision (2) is honoured: the weld
lets us ask *"does §2.3 assert anything the graph doesn't support"* and *"is anything
load-bearing missing from the text"*, in the checking direction only.

**Test** (item of `tests`)

| Field | Req | Notes |
|---|---|---|
| `id` | ✔ | `t1`… |
| `text` | ✔ | the planned experiment, specifically enough to be costed |
| `discriminates` | – | ref list, **≥2 claims** — the alternatives it separates |
| `grounded_in` | – | the Methods it uses (local `m*`, or a lit method slice) |
| `enabled_by` | – | ref list → Capabilities |
| `note` | – | |

**Capability** (item of `capabilities`)

| Field | Req | Notes |
|---|---|---|
| `id` | ✔ | `k1`… |
| `text` | ✔ | e.g. "optoRhoA patterning of active stress" |
| `grounded_in` | – | the evidence it **exists**: a published method (`Ruppel2023eLife:m1`), an ELN experiment, or a host-lab asset. **Empty ⇒ aspirational** (§8) |

**Narrative** — `programme/narrative/<grant>.yaml`: `{section → [refs]}`, plus page budget. Pure
ordering. It carries no edges and derives nothing; it exists so the two coverage questions above
can be asked. Deleting it must not change the graph.

---

## 8. Emergent properties — the payoff

Nothing below is an authored field.

| Property | Rule |
|---|---|
| **modality** (claim) | chain reaches a Test ⇒ **proposed**; else reaches a literature slice or an ELN experiment ⇒ **established**; else **speculation**. *Proposed wins the tie*: a conjunction is only as established as its weakest link, so one planned experiment anywhere underneath makes the claim something the grant **asks for** rather than reports — otherwise the payoff claim of an aim, which always co-cites something, reads as already known. And a Test is a **hollow** floor: the walk stops there rather than inheriting the Test's own methods and their citations |
| **load-bearing** (claim) | ≥1 dependent, no Test aimed at it, **and** speculation — the assumption detector. The third condition is load-bearing itself: an assumption is what *nothing will ever check*, so a merely-proposed claim does not qualify (a test settles its support) and neither does a well-cited one. Without it the signal drowns |
| **blast radius** (claim) | size of its transitive dependent set. Ranked: *which single assumption, if false, kills the most aims* |
| **feasible** (test) | every `enabled_by` Capability is itself grounded; else **at-risk** |
| **aspirational** (capability) | `grounded_in` empty — claimed but not evidenced |
| **open** (question) | no claim `answers` it — the existing rule, unchanged |
| **orphan** | a Test discriminating nothing; a Capability nothing is enabled_by; a claim with no dependents that answers no question **and that no Test discriminates** — a rival hypothesis has no dependents by design, and the test aimed at it is what makes it live |

*Blast radius* is the query that justifies the build. For a pivot as sharp as jamming → stress
it is not visible in prose, and it is the first thing a hostile reviewer finds.

---

## 9. Validation (extends SCHEMA §6)

1. `discriminates` targets **≥2** claims; a single target errors with "author as the claim's
   `grounded_in`".
2. `enabled_by` targets only a Capability (`k*`).
3. `leads_to` is invalid on Test and Capability — no broad tests/capabilities in v1.
4. `floor: true` stays claim-only. A Test's hollow-floor status is emergent, never authored.
5. Programme refs (`@slug`, `@slug:id`) resolve; an aim slug is globally unique and never
   collides with a citekey or a broad slug.
6. Existing rules (dangling refs, unique local ids, kind coherence, acyclic `leads-to`) apply
   unchanged across the merged graph.

---

## 10. Implementation cost — against the actual code

The graph core is a genuinely small change. In `litgraph/graph.py`:

- `_LOCAL` regex `[cqm]` → `[cqmtk]`
- `_SLICE_GROUPS` += `tests`, `capabilities`
- `classify_ref` += the `@` branch (§5)
- `_EDGE_FIELDS` += `discriminates`, `enabled_by`; `_check_kinds` += their prefix rules
- `load_repo` += the `programme/` tree, into the same `papers` dict
- `compute_emergent` += the §8 phases; `_slice_color` += the new colors

**The cost centre is the viewer, not the model.** `dist/index.html` is a paper-centric column
view; an aim-centric programme view is a different layout, and `serve.py` is the largest module
in the tool. Therefore: **ship the model and the queries first.** Validation plus a `lit
programme` report (load-bearing claims by blast radius, at-risk tests, unaddressed objections,
orphans) delivers every §8 payoff as terminal output with no viewer work at all. Visualization
is a later, separate decision.

---

## 11. Out of scope

- **v1 import.** Excluded by decision (1).
- **Prose generation.** Excluded by decision (2), structurally: the narrative layer derives
  nothing and the quote weld runs one way.
- **Feedback tracking.** Excluded on principle, not for cost (§4.1). Reviewer comments are
  ephemeral, and a graph that remembers them is a graph accreting dead process state. Revision
  rounds are tracked elsewhere; only what survives on its own merit enters as a node.
- **The ELN bridge.** A Test resolving to a real `experiments.db` experiment once run is
  precisely the cross-link CONCEPT §12 reserves — the programme graph is the third leg that
  closes literature → programme → notebook → literature. Designed for, not built here.
- **Cost/effort fields.** A Test has no duration or budget. If a Gantt chart is ever wanted it
  is a view over the narrative layer, and it is not obvious it belongs in the graph at all.
