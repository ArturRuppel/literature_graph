# SCHEMA — the on-disk data model

**Status:** v1 draft · **Date:** 2026-06-25 · companion to [CONCEPT.md](CONCEPT.md)

The concept doc converged the *graph* (4 node types, 8 edges). This doc fixes the
*files*: how that graph is written to disk so it is **diffable, hand-editable, and
machine-buildable** — the same philosophy this ecosystem already uses for its
experiment database (a diffable text dump is the source of truth in git; the binary
DB is a gitignored build artifact a generator produces from it).

```
YAML source of truth (git)  ──generator──▶  graph.db (SQLite, gitignored)  ──▶  catalog views
        ▲ hand-curated, one paper at a time
PDFs live outside git, in an external dir named by config.
```

No code is required to *define* the model — this spec plus the worked
[`example/`](example/) tree **is** the model. A parser/generator conforms to it later.

---

## 1. The cardinal rule: one file per curated paper

A node's home is chosen so that **the unit of storage equals the unit of curation**
(CONCEPT §5: "curating one paper = producing its local subgraph"). One curation
session touches one file → one clean commit, one readable diff.

| Node | Home | Rationale |
|---|---|---|
| **Curated paper** | `curated/<citekey>.yaml` — self-contained: metadata **+** its nested affirmations / questions / edges | the local subgraph |
| **Broader claim** | `claims/<slug>.yaml` (thin) | abstractions own no paper → can't nest → their own shard; the rollup targets |
| **Broader question** | `questions/<slug>.yaml` (thin) | free-floating questions; **see §7 — CONCEPT §12 left this shallow/open** |
| **Stub** (uncurated paper) | one entry in `stubs.yaml` | bib-only, machine-fetched, not hand-curated → a flat registry avoids file-explosion |
| **Author** | *emergent* — derived from each paper's `authors:` | keeps authoring cheap; no hand-maintained author files in v1 |

Rejected alternatives: **whole graph in one file** (every edit collides; merge hell)
and **one file per node** (an affirmation has no life outside its paper — CONCEPT §3 —
so splitting atoms out scatters one paper's subgraph and lets nodes orphan).

### Two things fall out for free

- **Tier is encoded by file presence.** A paper is *curated* iff `curated/<citekey>.yaml`
  exists; otherwise it is a *stub* (an entry in `stubs.yaml`). The curation frontier
  is the set of stubs — no `tier:` field anywhere. A citekey lives in exactly one of
  the two places; **promotion = move its `stubs.yaml` entry into a new `curated/` file.**
- **`asserts` / `poses` edges need no syntax.** They are nesting: an affirmation/question
  inside a paper file *is* that paper asserting/posing it.

---

## 2. File layout

```
<root>/
  curated/
    Ruppel2023NatPhys.yaml   # one curated paper = its whole local subgraph
    ...
  claims/
    traction-scales-with-stiffness.yaml
    ...
  questions/
    q-rigidity-sensing.yaml
    ...
  stubs.yaml                 # { citekey: bib-metadata } for every uncurated paper
  config.toml                # deployment-local (private): external PDF dir, etc.
```

In the **public repo** this tree lives under [`example/`](example/) as an
illustration. In a **private data repo** it lives at whatever root the deployment
chooses (e.g. `literature/`), and `config.toml` carries the real PDF path.

---

## 3. Identifiers

| Id | Form | Source |
|---|---|---|
| **citekey** | `<Family><Year><Venue>` CamelCase, e.g. `Ruppel2023eLife`; `a/b/c` suffix to disambiguate same-DOI collisions. `Venue` = ISO-4 journal abbreviation (+ override map for brand names like `eLife`). Also names the PDF, its `.md`, and the `pdf` field | filename stem of a `curated/` file, **or** a key in `stubs.yaml` |
| **affirmation / question (local)** | `a1`, `a2` … / `q1`, `q2` … — unique within its paper file | hand-assigned |
| **affirmation / question (global)** | `<citekey>:<local>` e.g. `Ruppel2023NatPhys:a1` | composed by the generator |
| **claim / broader-question** | kebab-case `<slug>`, globally unique | filename stem in `claims/` or `questions/` |

Cross-references are always one of these id strings; the generator resolves them into
edges and **fails the build on a dangling reference** (§6).

---

## 4. Node field reference

### Curated paper — `curated/<citekey>.yaml`

| Field | Req | Type | Notes |
|---|---|---|---|
| `title` | ✔ | str | |
| `type` | ✔ | enum | `original \| review \| methods \| perspective \| commentary` (CONCEPT §6) |
| `year` | ✔ | int | |
| `doi` | – | str | |
| `url` | – | str | |
| `authors` | ✔ | list | each `{name, position?, corresponding?}`; list order = byline order. `position` ∈ `first \| middle \| last` (default `middle`) — an authorship **tier**, so *multiple* `first`s are allowed (co-first / equal-contribution). `corresponding: true` is an **independent** flag (any number of authors). |
| `pdf` | – | str | defaults to `<citekey>.pdf` under the config PDF dir; set to override |
| `affirmations` | – | list | see below — absent/empty is valid (partial curation is normal) |
| `questions` | – | list | see below |

**Affirmation** (item of `affirmations`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | unique within file (`a1`…) |
| `text` | ✔ | str | the natural-language claim — what you'd write in an intro |
| `quote` | ✔ | str | exact supporting text. For `novel-*`: the evidential sentence. For `evidence: none`: the citing sentence |
| `evidence` | – | enum | `novel-data \| novel-theory \| none` (CONCEPT §6) — what *original* evidence this affirmation rests on; unset is valid |
| `cites` | – | list | each `{paper: <citekey>, role: source \| corroborates \| contradicts \| extends \| mentions}`; any affirmation may cite any number of papers; each `paper` enters as a stub if not curated (the citation frontier) |
| `rollups` | – | list | each `{to: <claim-slug>, polarity: concordant \| discordant \| neutral}` — the edge lives **here**, on the child, authored at curation time |

**Question** (item of `questions`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | unique within file (`q1`…) |
| `text` | ✔ | str | interrogative; no quote, no stance |
| `status` | ✔ | enum | `open \| answered` — an **open** question is a first-class frontier marker |
| `rollup` | – | question-slug | nests under a broader question (§7) |
| `answered_by` | – | claim-slug | curated edge, typically when `status: answered` |

### Broader claim — `claims/<slug>.yaml`

Thin by design — it is a *target*; its incoming `rollup` edges are stored on the
affirmations and inverted by the generator (so the "5 support / 2 contradict"
evidence meter of CONCEPT §9 is just a count, never bookkept here).

| Field | Req | Type | Notes |
|---|---|---|---|
| `text` | ✔ | str | the broad statement |
| `relates_to` | – | list | claim-slugs — symmetric free link |
| `depends_on` | – | list | claim-slugs — directed link |

### Broader question — `questions/<slug>.yaml`

| Field | Req | Type | Notes |
|---|---|---|---|
| `text` | ✔ | str | |
| `rollup` | – | question-slug | questions nest into broader questions |

### Stub — entry in `stubs.yaml`, keyed by citekey

```yaml
Ramms2013Pnas:
  title: "…"
  year: 2013
  doi: 10.1073/pnas.1313491110
  type: original        # optional
```

Bib-only. Reached only by some affirmation's `cites`. Carries no atoms (not read yet).

### Author — emergent

Not a file. The generator collects distinct `name`s across all `authors:` lists and
attaches their `position` per paper, yielding the Author nodes and the
`Author → Paper {position}` edges of CONCEPT §4 — for free, no hand authoring.

---

## 5. Edge encoding — all eight, and where each is authored

| CONCEPT §4 edge | Authored in | As |
|---|---|---|
| `Author → Paper` (position) | curated file `authors[]` | `{name, position}` |
| `Paper → Affirmation` (asserts) | curated file | **nesting** (implicit) + `evidence` tag |
| `Affirmation → Paper` (cites) | affirmation `cites[]` | `{paper, role}` — any affirmation, any number |
| `Paper → Question` (poses) | curated file | **nesting** (implicit) |
| `Affirmation → Claim` (rollup) | affirmation `rollups[]` | `{to, polarity}` |
| `Question → Question` (rollup) | question `rollup` | question-slug |
| `Question → Claim` (answered-by) | question `answered_by` | claim-slug |
| `Claim ⟷ Claim` (relates-to / depends-on) | claim `relates_to[]` / `depends_on[]` | claim-slug |

Every edge has **exactly one authoring site**, always the place where the curation
decision is made — so there is no two-sided bookkeeping to keep in sync.

---

## 6. Validation rules (the generator enforces; build fails otherwise)

1. **No dangling references.** Every `cites[].paper` resolves to a `curated/` file or a
   `stubs.yaml` key; every `rollups[].to` and `answered_by` to a `claims/` file;
   every `rollup` to a `questions/` file.
2. **Local ids unique** within each paper file.
3. **Slugs / citekeys globally unique**; a citekey is never both curated and a stub.
4. **Evidence ↔ citation-role coherence** (checked when both are set): a `source` cite ⇒
   `evidence: none` (the claim is borrowed); a `corroborates` / `contradicts` / `extends`
   cite ⇒ `evidence: novel-*` (you position your own finding); and `evidence: none` ⇒ at
   least one `source` cite (something must carry the claim).
5. **Rollup DAG is acyclic** (CONCEPT §4 — it is a DAG, not a tree, but no cycles).
6. **Enums valid** (`type`, `evidence`, citation `role`, `polarity`, `position` ∈
   `first|middle|last`, `corresponding` ∈ `true`/absent, `status`).

---

## 7. Open point — broader-question nesting (CONCEPT §12)

CONCEPT §12 left it undecided "whether the question DAG stands alone or anchors onto
claim altitudes (lean: anchored, shallow)." v1 takes the minimal, retractable stance:
broader questions get their own thin `questions/` files, symmetric with claims, and
`answered_by` is the only bridge from a question to a claim. If §12 later resolves to
"anchored," the `questions/` dir collapses into claim altitudes with no change to the
paper files.
