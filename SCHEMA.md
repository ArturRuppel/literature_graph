# SCHEMA — the on-disk data model

**Status:** v2 (lean / slice model) · **Date:** 2026-06-25 · companion to [CONCEPT.md](CONCEPT.md)

CONCEPT converged the *graph* to **one primitive** (the slice), in a **container** (the
paper), wired by **three edges** (`leads-to` · `answers` · `corroborate`/`contradict`), with
everything else emergent (CONCEPT §13). This doc fixes the *files*: how that graph is written
to disk so it stays **diffable, hand-editable, and machine-buildable** — the same philosophy
the experiment database already uses (a diffable text dump is the source of truth in git; the
binary DB is a gitignored build artifact a generator produces from it).

```
YAML source of truth (git)  ──generator──▶  graph.db (SQLite, gitignored)  ──▶  catalog views
        ▲ hand-curated, one paper at a time
PDFs live outside git, in an external dir named by config.
```

No code is required to *define* the model — this spec plus the worked
[`example/`](example/) tree **is** the model. A parser/generator conforms to it later.

---

## 1. The cardinal rule: one file per curated paper

A node's home is chosen so **the unit of storage equals the unit of curation** (CONCEPT §5:
"curating one paper = producing its local subgraph"). One session touches one file → one clean
commit, one readable diff.

| Node | Home | Rationale |
|---|---|---|
| **Curated paper** (the container `P`) | `curated/<citekey>.yaml` — metadata **+** its `claims` / `questions` / `methods` slices **+** their edges | the local subgraph |
| **Broad claim** | `claims/<slug>.yaml` (thin) | a `leads_to` target shared across papers; minted only when **≥2** slices share it (CONCEPT §10.2) |
| **Broad question** | `questions/<slug>.yaml` (thin) | shared `leads_to` target for questions |
| **Broad Method** | `methods/<slug>.yaml` (thin) | shared technique; minted only when **≥2** papers share it |
| **Stub** (uncurated paper) | one entry in `stubs.yaml` | an **un-sliced container** — bib-only, machine-fetched, holding only the wildcard |
| **Author** | *emergent* — derived from each paper's `authors:` | no hand-maintained author files |

### Two things fall out for free

- **Tier is encoded by file presence.** A paper is *curated* iff `curated/<citekey>.yaml`
  exists; else it is a *stub* (an entry in `stubs.yaml`). The frontier is the set of stubs —
  no `tier:` field. **Promotion = move the `stubs.yaml` entry into a new `curated/` file** and
  slice it; edges that pointed at the container `P` then sharpen to its slices (CONCEPT §2).
  This **breadth** tier stays emergent; the orthogonal **maturity** tier (how far curation ran,
  `0`–`4`) is the one thing recorded explicitly — `pass:` on the curated paper (§4, CONCEPT §10.1).
- **A slice's home in a container needs no syntax.** A `claims`/`questions`/`methods` entry
  *inside* a paper file *is* that paper containing it — the only implicit edge.

---

## 2. File layout

```
<root>/
  curated/
    Chen2021Sys.yaml         # one curated paper = its whole local subgraph
    ...
  claims/      <slug>.yaml   # thin broad claims (≥2 children)
  questions/   <slug>.yaml   # thin broad questions
  methods/     <slug>.yaml   # thin broad Methods (≥2 papers)
  stubs.yaml                 # { citekey: bib-metadata } — un-sliced containers
  config.toml                # deployment-local (private): external PDF dir, etc.
```

In the **public repo** this tree lives under [`example/`](example/). In a **private data
repo** it lives at the deployment's root (e.g. `literature/`), with the real PDF path in
`config.toml`.

---

## 3. Identifiers

| Id | Form | Source |
|---|---|---|
| **citekey** | `<Family><Year><Venue>` CamelCase, e.g. `Chen2021Sys`; `a/b/c` suffix for same-DOI collisions. `Venue` = ISO-4 abbreviation (+ override map for brand names like `eLife`). Also names the PDF and its `.md` | filename stem of a `curated/` file, **or** a key in `stubs.yaml` |
| **slice (local)** | `c1`, `c2` … (claims) / `q1`, `q2` … (questions) / `m1`, `m2` … (methods) — unique within its paper file. **No `a`/`ca` split** — "original vs borrowed" is emergent (§7), not encoded in the id | hand-assigned |
| **slice (global)** | `<citekey>:<local>`, e.g. `Chen2021Sys:c1` | composed by the generator |
| **broad claim / question / Method** | kebab-case `<slug>`, globally unique | filename stem in `claims/`, `questions/`, `methods/` |

**Ref syntax** — every edge target is one string, and its *form* says what it points at:

| form | refers to | in an edge, means |
|---|---|---|
| `m3`, `c2`, `q1` | a **local slice** in the same file | the precise slice |
| `throughput-scales-with-batching` | a **broad** `claims/`·`questions/`·`methods/` slug | the shared node |
| `West2015Sigmod` | a **container** (curated or stub) | the wildcard — "some slice in here, not yet resolved" (CONCEPT §2) |
| `West2015Sigmod:c3` | a **sharpened** cross-paper slice | the precise slice, once that paper is curated |

The generator resolves every ref into an edge and **fails the build on a dangling reference** (§6).

---

## 4. The slice and its edges

### Curated paper — `curated/<citekey>.yaml`

| Field | Req | Type | Notes |
|---|---|---|---|
| `title` | ✔ | str | |
| `type` | ✔ | enum | `original \| review \| methods \| perspective \| commentary` — a **filter only**, no evidential weight (CONCEPT §6) |
| `year` | ✔ | int | |
| `pass` | – | int | curation depth of the artifact, `0`–`4` — a single staircase where the number is *both* how far the paper was read *and* how mature the card is (CURATION.md): **0** ingested (metadata + extracted full text, no slices) · **1** abstract (every slice on the card is supported by the abstract) · **2** intro + discussion (borrowed claims, graph connections, open questions from the discussion) · **3** results (claims sharpened, welded to phrases describing the data) · **4** methods (methods read precisely, their citations traced and linked — the full sweep). **Absent on a stub** (uncurated; the breadth tier stays emergent via file presence, §1). The *one* authored process-state field — how far curation went isn't reconstructable from the slices (CONCEPT §10.1) |
| `doi` / `url` / `pdf` | – | str | `pdf` defaults to `<citekey>.pdf` under the config PDF dir |
| `authors` | ✔ | list | each `{name, position?, corresponding?}`; list order = byline. `position` ∈ `first \| middle \| last` (default `middle`) — an authorship **tier**, so multiple `first`s = co-first. `corresponding: true` is **independent** (any number) |
| `note` | – | str | free-text curator orientation (e.g. the experimental setup); not a graph element |
| `abstract` | – | str | verbatim abstract, written by `lit ingest` (OpenAlex/Crossref); shown in the viewer tooltip; not a graph element |
| `tags` | – | list[str] | free-form curator labels — a **container filter axis** for organizing and finding papers, the same category as `type` (a cheap filter, no evidential weight; CONCEPT §6). Carries **no** evidential weight and **nothing in the graph derives it**; it never feeds grounding/strength/any emergent property, and lives **only on the container, never on a slice**. Authored by hand or via `lit tag`; searched by the viewer. **Curated-only** (a stub has none). Not a graph element |
| `claims` / `questions` / `methods` | – | list | the paper's slices (below) — absent/empty is valid (partial curation is normal) |

**Claim** (item of `claims`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | `c1`… unique within file |
| `text` | ✔ | str | the natural-language claim — what you'd write in an intro |
| `quote` | ✔ | str | supporting text from the paper's `.md`. Normally a verbatim substring; non-contiguous passages may be joined with `[...]` but must be flagged for curator review |
| `quote_loc` | – | map | derived PDF anchor for the quote — `{page: int (0-based), rects: [[x0,y0,x1,y1], …]}`, each rect a **page fraction** (0..1), one per wrapped line. Written by `lit locate` (not hand-authored); optional and additive; drives the `lit serve` PDF quote windows (see *Quote windows*, §6) |
| `grounded_in` | – | ref list | **`leads-to` edges *into* this claim** — what it rests on. Heterogeneous; the target's *kind* is the meaning: a **method** ref → empirical floor; a **claim** ref → premise / derivation; a **container/citation** ref → a borrowed (restated) claim (CONCEPT §6.1) |
| `leads_to` | – | slug list | **`leads-to` edges *out* of this claim** — the broader claim(s) it generalizes into (the old "rollup", unsigned) |
| `corroborates` / `contradicts` | – | ref list | **lateral** stance toward an independently-grounded claim/paper — the only *signed* edges (CONCEPT §4) |
| `answers` | – | ref list | the question(s) this claim answers (CONCEPT §4) |
| `floor` | – | `true` | declares this claim an **axiom** (a self-grounding formal floor); the only deliberate marker in the model (CONCEPT §3) |
| `note` | – | str | free-text curator judgement; not quote-bound, never an edge |

**Question** (item of `questions`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | `q1`… |
| `text` | ✔ | str | interrogative; no stance (the interrogative asserts nothing) |
| `quote` | – | str | the paper sentence that **raises** the question — the same integrity weld a claim carries, so an open question is verifiable in the source and findable in the PDF. **Optional** (a purely synthesized question may lack a verbatim anchor), but **expected for open questions**: they are raised by a specific "future work / remains unclear" sentence. Verbatim substring by default; `[...]`-joined passages flagged for review. The `text` is the curator's interrogative rephrasing; the `quote` is the verbatim declarative source — exactly as a claim's `text` rephrases its `quote` |
| `quote_loc` | – | map | derived PDF anchor for the quote, written by `lit locate` (identical to a claim's, §6) — drives the `lit serve` PDF quote window |
| `leads_to` | – | slug list | the broader question(s) it generalizes into |

> **open vs answered is emergent** — a question is *answered* iff some claim `answers` it
> (§7). No `status` field. Because openness can flip (a later paper's claim may `answer` it),
> the `quote` weld is a **kind-level** affordance, never gated on open/answered.

**Method** (item of `methods`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | `m1`… |
| `text` | ✔ | str | the technique (e.g. "microbenchmark harness") |
| `grounded_in` | – | ref list | what this method rests on: the paper(s) that introduced it, **and/or other methods it layers on** (a model `grounded_in` the measurements it consumes — CONCEPT §7). A measurement method grounding only in its source paper is a **floor** |
| `leads_to` | – | slug list | a broader Method it generalizes into (the method ladder: microbenchmark → performance benchmarking) |
| `quote` | – | str | methods-section sentence; **optional** (methods prose is boilerplate). Shortening with `[...]` is allowed but must be flagged for curator review |

### Thin broad slice — `claims/<slug>.yaml`, `questions/<slug>.yaml`, `methods/<slug>.yaml`

Thin by design — a `leads_to` *target*. Its incoming edges live on the children and are
inverted by the generator (so the "5 support / 2 contradict" meter of CONCEPT §9 is just a
count, never bookkept here).

| Field | Req | Type | Notes |
|---|---|---|---|
| `text` | ✔ | str | the broad statement / question / technique name |
| `leads_to` | – | slug list | generalizes further up the ladder (a broad claim into a broader one; microbenchmark → performance benchmarking) |

### Stub — entry in `stubs.yaml`, keyed by citekey

```yaml
West2015Sigmod:
  title: "Unbounded throughput scaling in partitioned pipelines"
  authors: [Dana West, Omar Farooq]   # optional; byline order, display names (no role resolution)
  journal: "SIGMOD Record"            # optional; venue display name
  year: 2015
  doi: 10.0000/synth.west2015
  type: original                      # optional
```

An **un-sliced container**: bib-only, reached by some slice's `grounded_in` / `corroborates`
/ `contradicts`. Carries no slices (not read yet). `authors` and `journal` are the bib metadata
OpenAlex already returns for every reference, written by `lit ingest` and backfillable onto older
stubs with `lit enrich`; both drive the viewer's hover card (title · authors · journal · year).
Unlike a curated paper's authors, stub authors are plain names — no `position` / `corresponding`
(there's no PDF to resolve roles from). A stub's **abstract is never stored** (it would balloon
the frontier file); `lit serve` fetches it live from OpenAlex on hover instead.

### Author — emergent

Not a file. The generator collects distinct `name`s across all `authors:` lists and attaches
their `position` per paper, yielding the Author nodes and `Author → Paper {position}` edges —
for free, no hand authoring.

---

## 5. Edge encoding — one authoring site each

| CONCEPT §4 edge | Authored on | As | Direction |
|---|---|---|---|
| **`leads-to`** (grounding / derivation / generalization / citation) | the curated slice | `grounded_in` (arrow **in**) *or* `leads_to` (arrow **out**) | ground → derived |
| **`answers`** | the answering claim | `answers` | claim → question |
| **`corroborate` / `contradict`** | the asserting claim | `corroborates` / `contradicts` | lateral (signed) |
| `Author → Paper` (position) | the paper `authors[]` | `{name, position}` | — |

`leads-to` is **one edge type**; `grounded_in` and `leads_to` are inverse *views* of it, so
every edge is authored exactly once on the curated slice — never by editing a shared `claims/`
file or an upstream stub. Author downward edges (to floors / premises / citations) as
`grounded_in`; upward edges (to broader claims) as `leads_to`.

---

## 6. Validation rules (the generator enforces; build fails otherwise)

1. **No dangling refs.** Every `grounded_in` / `leads_to` / `corroborates` / `contradicts` /
   `answers` ref resolves to a local slice id, a `claims/`·`questions/`·`methods/` slug, a
   `curated/` file or `stubs.yaml` key (a container), or a `<citekey>:<id>` slice.
2. **Local ids unique** within each paper file (across `c*` / `q*` / `m*`).
3. **Slugs / citekeys globally unique**; a citekey is never both curated and a stub.
4. **Quote integrity.** Every claim `quote` — and every question/method `quote` when present — must
   be grounded in the paper's `.md` full text. Verbatim substrings are the default. A quote
   containing `[...]` is accepted when non-contiguous passages are intentionally shortened,
   but the generator **flags** such quotes for curator review; it never silently treats them
   as verbatim.
5. **`leads-to` is acyclic** (the support DAG; many-to-many, no cycles).
6. **Kind coherence.** `leads_to` targets a same-kind broad slug (claim→claim, question→
   question, method→method). `answers` targets a question. `corroborates`/`contradicts`
   target a claim or a container. `floor: true` only on a claim.
7. **No emergent fields authored.** `status`, `evidence`, citation `role`, rollup `polarity`
   are **not** valid keys — they are derived (§7), and their presence is an error. (A paper's
   `tags` is *not* one of these: it is authored container metadata like `type`, deriving no
   graph property — see §4.)
8. **Enums valid** (`type`, `position` ∈ `first|middle|last`, `corresponding` ∈ `true`/absent,
   `pass` ∈ `0|1|2|3|4` and only on a curated paper).

**Quote windows — `quote_loc`.** A `quote` may carry an optional `quote_loc` (page + fractional
rects, one per wrapped line) welding it to its place in the PDF. It is **derived, not authored**:
`lit locate` resolves it by word-geometry matching (covering the *whole* quote, across line
breaks and hyphenation) and writes it into the YAML — re-run it (`--force`) any time the matcher
improves. It is additive and never affects graph structure or emergent properties: it only drives
the `lit serve` viewer's PDF quote windows (a stored location renders instantly; a quote without
one is resolved live). `lit build`'s static artifact ignores it.

---

## 7. Emergent properties (computed by the generator, never authored)

| property | rule |
|---|---|
| **open vs answered** (question) | answered iff some claim `answers` it |
| **original vs borrowed** (claim) | borrowed iff its `grounded_in` reaches a **container/citation** (cross-paper) rather than a floor — a restatement (CONCEPT §6.1) |
| **grounded vs plausible** (claim) | grounded iff its `leads-to` chain reaches a **floor** (a measurement method, or an axiom); else it dangles on reasoning |
| **evidence balance** (claim) | count incoming `corroborates` vs `contradicts` |
| **floor** (slice) | a slice whose own grounding bottoms out — a measurement method (grounding only in its source paper), or an `floor: true` axiom. *Models are methods that are **not** floors* — they `grounded_in` the methods below them (CONCEPT §7) |

---

## 8. Open point — broader-question nesting (CONCEPT §12)

CONCEPT §12 left undecided "whether the question DAG stands alone or anchors onto claim
altitudes (lean: anchored, shallow)." v1 takes the minimal, retractable stance: broad
questions get their own thin `questions/` files, and a claim's `answers` is the only bridge
from a question to a claim. If §12 later resolves to "anchored," `questions/` collapses into
claim altitudes with no change to the paper files.
