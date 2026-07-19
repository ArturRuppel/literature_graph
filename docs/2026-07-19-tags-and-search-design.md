# Tags and search — design

**Status:** spec (approved for planning) · **Date:** 2026-07-19
**Companions:** [CONCEPT.md](../CONCEPT.md) · [SCHEMA.md](../SCHEMA.md)

Two viewer/curation conveniences the tool is missing:

1. **Tags on papers** — free-form, curator-authored labels on a curated paper, for
   organizing and filtering.
2. **Search** — find a paper you have partial information about (keywords, maybe an
   author, maybe the journal).

Neither touches the graph model. Both are deliberately narrow; the "out of scope"
section fences off the adjacent-but-different features they are *not*.

---

## 1. Tags — a container filter axis, not emergent state

CONCEPT.md is militant that slices carry **no fields** and that properties readable off
the graph (open/answered, grounded/plausible, original/borrowed) are never authored
(§3, §13). Tags do not violate this, and the design holds the line that keeps it true:

- A tag is **container-level curator metadata**, the same category as `type` (§6, "a
  cheap filter, no evidential weight"), `note`, `pass`, and `authors`. It carries **no
  evidential weight**, and **nothing in the graph derives it**.
- A tag is `type` set free from its five-value enum: a free-form, multi-valued filter
  axis on the **container**. It lives **only on the container, never on a slice**. Wanting
  to tag a *slice* (e.g. mark a claim "important") is the smell that we are hand-authoring
  emergent state, and we stop.
- **Curated papers only.** Stubs are machine-fetched bib and get no tags.

### On-disk (SCHEMA §4)

A new optional field on `curated/<citekey>.yaml`:

```yaml
title: "..."
type: original
year: 2021
tags: [tension-percolation, monolayer, revision]   # optional; curated only
authors: [...]
```

- Absent / empty is valid (the default).
- Free-form strings. No controlled vocabulary. Matched case-insensitively (see §2), but
  stored **as authored** — no forced normalization.
- Rendered by `to_yaml()` after `year`/`doi`/`url`/`pdf`, before `authors`.

SCHEMA.md must gain `tags` as a valid authored field in the §4 CuratedPaper table, and
the build validator's key-check (§6 rule 7 — the one that rejects `status` / `evidence` /
`role` / `polarity`) must **accept** `tags`. If no strict whitelist exists, confirm the
loader simply reads the key; if one does, add `tags` to it.

### Data flow (four points, per the terrain map)

| Layer | Change |
|---|---|
| `model.py` `CuratedPaper` | add `tags: list[str] = field(default_factory=list)`; emit in `to_yaml()` |
| `graph.py` `Paper` + `paper_from_raw()` | add `tags: list[str]`; read from raw YAML |
| `build.py` `_paper_json()` | include `"tags": p.tags` |
| viewer | consume as `PAPERS[key].tags` |

### Authoring — `lit tag`

A new CLI verb rewriting the single YAML file (hand-editing YAML also always works):

- `lit tag <citekey> <tag> [<tag> …]` — add tag(s), de-duplicated, order-preserving.
- `lit tag --remove <citekey> <tag> [<tag> …]` — drop tag(s).
- `lit tag <citekey>` — list the paper's current tags.

Operates only on `curated/<citekey>.yaml`; errors clearly if the citekey is a stub or
absent. Registered like the other argparse subcommands in `cli.py`. **Not** browser-based
tag editing — that is a file-mutating-from-the-page feature left for later.

### Display

Tag chips on the curated card, near the `type` badge. Clicking a chip runs a search for
that tag (§2) — which is the entire filter-by-tag story, with no separate filter panel.

---

## 2. Search — paper-finding, client-side

The goal is narrow and specific: **find a paper you half-remember** — some keywords,
maybe the author, maybe the journal. It is *not* knowledge-search over claims/quotes
(see Out of scope).

### UI

- A **search box in the HUD bar** (`#hud` in `template.html`).
- Typing fragments live-filters into a **results dropdown** listing matching papers,
  **curated and stubs**, each shown with enough to recognize it: **title · authors ·
  journal/type · year**, curated vs. stub visually distinct.
- **Curated result → click** scrolls to and focuses its card (reuses the existing focus
  mechanism: the `focus` class + scroll).
- **Stub result → identify-only** for v1. Seeing "yes, that's the one — Chen 2019,
  *Nature*, still a stub" is frequently the whole answer. No navigation on click yet
  (click-to-referencing-card is a deliberate future step).
- `Esc` clears the box and closes the dropdown.

### Matching

- A per-paper searchable **blob**: `citekey + title + author names + journal + year +
  tags` (tags only exist on curated papers).
- Case-insensitive; the query is split on whitespace and terms are **AND**-ed (every
  term must appear somewhere in the blob).
- Simple substring scoring; **curated ranks above stubs**. No fuzzy / Levenshtein
  matching in v1.

### Where it runs

**Entirely client-side in the viewer JS.** No `serve.py` endpoint. This keeps
`lit build`'s static `dist/index.html` fully functional offline — consistent with
CONCEPT §1 ("the published view never depends on a server"). Search works identically in
`lit build` and `lit serve`.

---

## 3. Out of scope (on purpose)

- **Knowledge-search** over slice text, quotes, or abstracts — a different feature with a
  different UI; not this.
- **Browser-side tag editing** (a POST endpoint writing YAML from the page).
- A **controlled tag vocabulary** / tag validation.
- Standalone **type/tag filter panels** beyond what search + clickable chips give.
- **Tags on stubs.**
- Click-to-referencing-card navigation for **stub** search results.

---

## 4. Testing

Python tests stay **offline and deterministic** (repo convention — recorded fixtures, no
live network):

- **model** — a `CuratedPaper` with `tags` survives `to_yaml()` → parse round-trip;
  empty/absent tags default cleanly.
- **graph → JSON** — `paper_from_raw` reads `tags`; `_paper_json` carries them.
- **validation** — the build accepts a curated paper carrying `tags` (no false "emergent
  field authored" rejection).
- **`lit tag`** — add (with de-dup), `--remove`, and list each mutate/report the YAML
  correctly; a stub or missing citekey errors.

The viewer JS has **no test harness** in this repo (it's a template), so the search box,
results dropdown, and tag chips are verified **by hand via `lit serve`** and a static
`lit build`.
