# CLAUDE.md — project context for agents

`literature_graph` is a **knowledge graph over the scientific literature**, built for the
AI-proposes / human-curates rhythm. You (an AI agent) do the heavy lifting — parsing PDFs,
drafting claims, fetching metadata — and a human accepts / edits / rejects. **Curation is
the rate limiter; never flood. A half-finished graph is a normal, valid state.**

## Read these first (in order)

1. [CONCEPT.md](CONCEPT.md) — the model: **one primitive (the slice) in a container
   (the paper), three edges**, everything else emergent. *What* the graph is and *why*.
2. [SCHEMA.md](SCHEMA.md) — the on-disk data model: one diffable YAML per curated paper,
   thin files for broad slices, a stub registry. *How* it's written to disk.
3. [CURATION.md](CURATION.md) — the reading protocol: the four-pass sweep that turns a
   paper's full text into its proposed local subgraph. *How* a paper is read in.
4. [tools/lit/](tools/lit/) — the `lit` CLI, self-contained (package, tests, spec).
   Design spec: [tools/lit/docs/2026-06-25-litgraph-ingest-design.md](tools/lit/docs/2026-06-25-litgraph-ingest-design.md).
5. [example/](example/) — a small worked library on the lean slice model (SCHEMA v2).
6. [docs/2026-06-25-visualization-design.md](docs/2026-06-25-visualization-design.md) —
   *future* direction for showing the graph: the **recursive container view** (+ reference
   mockups in `docs/mockups/`). Not yet built.
7. [docs/2026-08-02-programme-graph-design.md](docs/2026-08-02-programme-graph-design.md) —
   the **programme graph**: the same slice model extended from *what is known* to *what is
   proposed*. Two extra kinds (**Test · Capability**), two extra edges (`discriminates` ·
   `enabled_by`), one extra container (the **aim**, under `programme/aims/`), and one extra
   ref form (the `@aim` sigil). Model + `lit programme` are built; no viewer.

## Mental model (the 30-second version)

- **One primitive — the slice**, inside a **container `P`** (the paper). Three slice kinds:
  **Claim · Question · Method**, each welded to an exact `quote` (methods optional),
  recursively sliceable. A paper *is* its slices.
- **Three edges:** `leads-to` (the support skeleton — grounding · derivation ·
  generalization · citation; authored as `grounded_in` ⟂ `leads_to`), `answers` (claim →
  question), `corroborate` / `contradict` (lateral stance). A **measurement** Method is a
  *floor* where grounding bottoms out; a *model* is a Method that layers on measurements.
- **Everything else is emergent — no node fields:** open/answered, original/borrowed,
  grounded/plausible, evidence balance (CONCEPT §13). Don't author `evidence`/`status`/`role`.
- **Two tiers, by file presence:** *curated* iff `curated/<citekey>.yaml` exists; else a
  **stub** — an un-sliced container in `stubs.yaml`. The set of stubs *is* the frontier; an
  edge targets the container `P` until curation slices it (the wildcard sharpens).
- **Generalize, don't merge:** never equate two claims; co-parent them under a broader
  `claims/` node via `leads_to` (≥2 children). Paper-specific phrasing and quotes survive.
- **Two axes, kept apart:** the **claim ladder** (`leads_to` between `claims/` nodes) answers
  *what is known*; the **topic axis** (`topics/` — keyword containers over paper `tags`)
  answers *what papers do I have on X*. A statement that can be **false** is a claim; a
  heading you cannot disagree with is a topic. Topics are never edge targets, and nothing in
  the graph derives from them (SCHEMA §9).

## Conventions this repo enforces

- **citekey = `<Family><Year><Venue>`**, CamelCase, e.g. `Chen2021Sys`. This one string
  names the PDF, its full-text `.md`, the `curated/<key>.yaml` file, **and** the
  `stubs.yaml` key. Venue is the ISO-4 journal abbreviation (+ an override map for brand
  names like `eLife`).
- **Authors** carry two orthogonal axes: `position` (`first | middle | last`, an authorship
  *tier* — multiple `first`s = co-first/equal-contribution) and an independent
  `corresponding: true` flag. List order = byline order.
- **Source of truth is git-tracked YAML.** The SQLite `graph.db` is a disposable build
  artifact (gitignored). **Curated PDFs and their `.md` full-text live in `pdfs/`
  inside the data repo** (`pdf_dir` in `config.toml`), committed one-per-paper.
  Uncurated/staging PDFs live outside git in `~/Literature/`.

## Tools

- **`lit ingest <pdf>`** — initialize a paper's bibliographic skeleton: writes
  `curated/<citekey>.yaml` (metadata + authors), one deduped `stubs.yaml` entry per
  citation (DOI-anchored via OpenAlex), and an AI-parsable `<citekey>.md` full text beside
  the (renamed) PDF. **Non-interactive**: an agent runs it, then agent + human review the
  written YAML together. Use `--dry-run` to preview without writing/renaming. It does *not*
  extract the claim/question/method slices — that's the curation step (CURATION.md). Ingest also
  writes each stub's `authors` + `journal` (the bib OpenAlex already returns per reference), which
  the viewer shows on hover.
- **`lit enrich`** — backfill `authors` + `journal` onto **existing** `stubs.yaml` entries from
  OpenAlex (by DOI), for stubs ingested before those fields existed. One batched query; only fills
  gaps unless `--force`; `--dry-run` reports without writing. Run once, review the diff, commit.
  (Abstracts are *not* stored — `lit serve` fetches a stub's abstract live on hover; SCHEMA §4 Stub.)
- **`lit build`** — build the static graph viewer: reads the data repo's YAML, computes the
  graph + emergent properties (SCHEMA §7), and emits a self-contained `dist/index.html`
  (the paper-centric column view) plus `graph.json`. Open the HTML directly; no server.
  Validation fails the build on a dangling ref or a curated/stub citekey collision (SCHEMA §6).
  The viewer's HUD carries a **paper-finding search box** (title · author · journal · year · tag,
  curated + stubs) — client-side, so it works in the static artifact offline.
  Next to the width slider it carries the **board zoom** — its own slider, plus ctrl/⌘-wheel over
  the board and the bare `+` `−` `0` keys; remembered in `localStorage`, and clicking the `100%`
  readout puts it back. The track is **log-spaced over 1/3 … 3**, so 100% sits exactly mid-track
  and half sits as far from it as double (zoom multiplies; a linear track would crush the whole
  zoom-out half into a fifth of the bar). Same shape as the width slider because the gesture is
  the same — you sweep until the board looks right — but they are not the same thing:
  **width** re-lays-out a card's text, **zoom** is a *camera* — one `scale()`
  on `#stage`, so nothing re-wraps and the picture you had learned survives the move. Zoomed out
  the board stops being readable and becomes a **map** (which column fans where, whether a hoisted
  claim actually gathered anything) — the question you have on a paper with 58 cards, and one the
  500px column could never answer. The edge overlay lives on the same stage, so redraw() is the one
  place that converts glass pixels back into stage pixels (÷ BZ); every scroll-anchoring site is
  untouched, which is why this is a transform and not CSS `zoom`.
  **The board hides nothing pending a click.** The landing column lists **every curated paper** in
  `ORDER`'s pass ranking (plus a tail of cards for the uncurated papers a lateral / `answers` edge
  points at, so those arrows have an anchor), and the **synthesis band** gives every broad claim /
  question / method a card, always.
  **The band is containerized: one box per ladder root.** A broad claim's `leads_to` ladder is drawn
  as *containment* — the root's card heads the box and everything laddering into it nests inside,
  recursively — because a family is a container of narrower claims exactly as a paper is a container
  of slices. So the ladder is visible standing still: the rung **arrows are gone**, since geometry
  now says what they said (they were suppressed at rest anyway, which is why the ladder used to read
  as invisible). 45 broad nodes → 5 family boxes + 11 singletons today. Each box carries a
  `fold to titles` / `show statements` bar (the paper card's `.sbar` idiom one scale up) and **lands
  folded**: the band is a map, and a map shows names — the statement is the row's hover text, never
  removed. A claim with **two parents** nests under the first its `leads_to` names and leaves a
  `↗ reference row` under the others (never a duplicate card), with the crossing kept as one drawn
  edge. **Clicking a broad claim shows it**: its *box* goes to the top of the synthesis column and
  every paper asserting it to the top of the curated list. Each hoisted paper says which claim it
  answers to, which is what keeps two gathered blocks apart. Clicking again releases but leaves the
  order — nothing snaps back under you; the column header's **`clear`** (present only when there is
  something to release) puts every shown claim away at once.
  (Two reversals worth knowing, both in `docs/2026-08-03-topics-and-claim-altitudes.md`. §6: the band
  and the landing column once *hid* what you had not clicked — reversed, because **hoisting places
  the reader's attention, so hiding only made the rest of the graph unmentionable.** §6.1: what
  replaced it sorted the band into **altitude columns**, which rendered a derived scalar instead of
  the authored relation and sprayed each family across the board — reversed by containment, which
  **adds a boundary and subtracts nothing**. Do not re-introduce either by treating a long column as
  the problem: length is not the defect, unstructured length is.)
  Browsing the **other** ~3.8k entries is still the **library** view's job — the board's flat list
  is the curated set, not the bibliography.
  The HUD's **`walk`** button (or `w`) swaps the board for **the walk** — one focus, one relation,
  an indented tree, **no drawn edges at all** (design: `docs/2026-08-03-the-walk-design.md`). One or
  the other, never both; `Escape` or `← board` returns. The board superimposes five differently
  shaped relations on one canvas and stops being readable on exactly the papers curated hardest
  (58 cards / 89 edges on `Hohmann2022Cellsa`); the walk shows one at a time under a depth and
  sibling budget, so the mess is structurally impossible. Its **first tab is `contains`** — a
  **roster**, not a walk: every claim, question and method in the paper, **uncapped and unfolded**,
  each with its weld quote, filterable by kind. Every other tab is a *relation*, so a slice that
  participates in none is unreachable there; the roster is the only **complete** view, and it flags
  those slices **`unwired`** (64 of 532 today). This is the view to sift a paper in.
- **`lit serve`** — the same viewer over loopback HTTP, for a curation session: the graph is
  rebuilt from the YAML on every refresh (edit → refresh; a broken edit returns the
  validation error and the server survives), and the tooltip gains a first-page preview of the
  `<citekey>.pdf` files in `pdf_dir` (config.toml, else `<root>/pdfs`).
  **Two surfaces** (design: `docs/2026-07-09-cockpit-redesign-in-progress-zone.md`, windowed by
  `docs/2026-07-28-curation-windows.md`):
  - *Browse view* — the graph, plus one **collapsible PDF viewer** docked right, toggled by the
    header's **📄 PDF** pill. **The pill is the only thing that opens it** — opening a card is
    reading the graph, not a request for a PDF across half the screen. Clicking a quote-slice
    *aims* the viewer whether or not it is open (a shut dock just remembers the aim), so the next
    📄 lands on that claim's highlight; with nothing aimed yet the pill opens the focused paper at
    page 1. Open, hovering a quote-slice aims it at that claim's citation — the
    **whole PDF** as a lazily-rendered scroll of pages, opened on the highlight, with a real
    scrollbar, a live page indicator, and a pan / text-select toolbar (drag to
    pan, or select & copy the page's real text via a transparent word overlay). The location comes
    from a stored `quote_loc` (SCHEMA §6) when present, else resolved live.
    Its **zoom is its own** — a slider in the titlebar, ⌘/ctrl-wheel over the page, or
    the bare `+` `−` `0` keys while the pointer is on it (in a PDF-only window they are always its,
    since there is no board there to mean instead). It shares nothing with the board's: a page at
    200% beside a board at 60% is the ordinary way to curate. Fit-width is the floor, and the zoom
    is **remembered across mounts** — aiming at the next quote is not a request to stand back up,
    and the new page opens on its highlight at the distance you were already reading from
    (`showQuote` centres the whole highlight, clamped to keep the quote's *opening line* in frame
    once the zoom makes it wider than the pane). The dock's titlebar
    carries a **⧉ detach** button that pops the PDF into its **own OS window** (`index.html?detached=1`,
    for a second monitor); the same hover keeps aiming it via a `lit-pdf` BroadcastChannel, and the
    **📄 PDF** pill re-docks it. Detaching reclaims the graph's full width.
  - *Curation session* — **right-click a curated card → "Curate this paper"** *moves* it out of the
    graph onto the **"in progress · N"** worklist (`[curation] active` in config.toml). The pill
    opens a picker; selecting a paper performs the whole transition in **one click**: the current
    graph window becomes the **card** (`preview.html?key=…&drive=1`, its isolated subgraph,
    hot-reloading on a YAML edit), the **paper** opens as the click's one browser popup
    (`index.html?focus=1`), and the server opens a **terminal** running that paper's persistent
    Claude session. The PDF is aimed by polling the focus wire so `lit focus` and the card's
    quote-clicks both steer it. The window manager tiles them; there is no in-page split. The terminal is a
    native emulator (`kitty`, `wezterm`, … — first found, or `$LIT_TERMINAL`) spawned by the
    server via `POST /term`, so it's a *real* terminal with full keybindings and scrollback;
    with no emulator installed you get the two browser windows and start the session yourself.
    The card window carries the walk too, as a **`contents`** HUD button (or `w`): its paper's
    full roster, standing on that paper with the library rail dropped (one paper is the whole
    subgraph). Clicking a quote there POSTs the weld to the focus wire like any card row, so it
    aims the paper window; and the card's hot-reload re-indexes it, so a slice the agent has just
    written appears in the roster without a refresh. This is where you check that a pass wrote
    what it claimed to.
    Finishing runs both ways: the picker row's **✓**, or the card window's own HUD button
    **✓ finish curation**, which drops the paper off the worklist and turns that window back
    into the graph (the PDF and terminal windows are left open). Leaving *without* finishing is
    the card's **← graph** button: it navigates back to the browse view and leaves `[curation]
    active` alone, so the paper is still on the "in progress" pill and one click re-enters its
    card — finishing is a statement about the paper, not the only door out of the window.
  Serve-only; a static `lit build` keeps the pill/toggle hidden and stays the shareable artifact.
  A third HUD pill, **"aims · N"**, indexes `programme/aims/` (via `/aims.json`) with each aim's
  assumption and at-risk-test counts; a row opens that aim's card at `/preview.html?key=@<slug>`
  in a new tab. `/graph.json` stays paper-only, so the landing board is untouched by the
  programme layer — and a repo with no `programme/` tree never shows the pill.
- **`lit curate <citekey>`** / **`lit curate --done <citekey>`** — the same move from the terminal:
  add (or remove) a curated paper to the in-progress worklist. Drives the same `[curation] active`
  that the right-click move and the "in progress" pill share.
- **`lit tag <citekey> [tags…]`** — add / remove / list a curated paper's **`tags`**: free-form
  curator labels (a container filter axis like `type`, SCHEMA §4 — no evidential weight, curated-only).
  Bare `lit tag <citekey>` lists; `--remove` drops the given tag(s). Round-trips the one YAML file
  (comments survive). Tags are searchable in the viewer, and clicking a tag chip on a card searches it.
  `--suggest` proposes tags from the paper's **author-keyword line** (scraped + kebab-cased from the
  full text) — a **Pass-1** step (CURATION.md): it prints candidates and a ready `lit tag` command and
  **writes nothing**, so the curator gates which land in the filter axis.
- **`lit topics`** — report the **topic axis** (SCHEMA §9): keyword containers over the `tags`
  vocabulary, so papers stay findable as it grows. Bare prints the tree with papers reached and
  keywords owned; `lit topics <slug>` lists one topic's papers; **`--orphans`** is the one that
  matters — unfiled tags (on a paper, in no topic), dead keywords (in a topic, on no paper) and
  stranded papers, the three signals that keep the layer from rotting behind the tagging
  (`--strict` exits non-zero for CI). Run it after a tagging session. Topics are **not graph**:
  never an edge target, membership derived from tags alone, nothing on a paper names one.
- **`lit focus <citekey> [--quote "…"]`** — aim a running `lit serve` session's **paper window** at
  a quote (my hand during curation): resolves the quote and re-aims the PDF. The card window's
  quote-clicks drive the same wire, so agent and human stay in one truth.
- **`lit locate`** — resolve every curated quote's place in its PDF (full-coverage word-
  geometry match) and store it as `quote_loc` in the YAML: run once, review the diff, commit.
  `--force` re-resolves quotes that already have a location; `--dry-run` reports without writing.
- **`lit preview <citekey>`** / **`lit preview --scratch <file>`** — render **one paper's**
  local subgraph *in isolation* (its slices + every edge, cross-paper endpoints as stub
  chips / synthesis band) via the same viewer `lit build` ships, so it can't drift. Fed a
  scratch YAML (real `curated/` schema), it renders a **proposition before it's tokenized** —
  the curation loop's "show it as it'll look" step (CURATION.md). Also flags non-verbatim
  quotes at proposition time. Emits a self-contained `dist/preview.html`. Also renders an
  **aim** — `lit preview '@<slug>'`, or `--scratch` an aim-schema YAML under an `@` key, so
  the same propose-before-tokenizing loop works on *proposed* work. An aim's card swaps the
  entry groups from a paper's rhetoric (novel / borrowed / open) to a programme's
  (hypotheses & rivals · assumptions · established · speculation · tests · capabilities), a
  load-bearing claim carries its blast radius as a badge, and drilling a test opens what it
  separates (`discriminates`), what it needs (`enabled_by`) and the methods under it.
- **`lit programme`** — report the **programme graph**'s emergent state (design doc §8): the
  **load-bearing assumptions ranked by blast radius** (claims with dependents, no test aimed
  at them, and no grounding in the literature — the thing a hostile reviewer finds first),
  plus speculation, tests at risk from an unevidenced capability, aspirational capabilities,
  open questions and orphans. Reads `programme/aims/*.yaml`; silent on a repo without one.
  `--strict` exits non-zero when anything is flagged, for CI. Terminal only — every payoff
  lands without the viewer.

## Curating a paper

When the human asks to **curate a paper**, **read [CURATION.md](CURATION.md) first** and
follow its protocol. Curation is **interactive and discussion-first**, never a one-shot file
dump:

- Work **one pass at a time** (the four passes in CURATION.md).
- Each pass is a loop: **explain your reading** of the paper at that pass's granularity in
  prose → **discuss with the human until you agree** → *only then* **tokenize** (write the
  agreed nodes into `curated/<citekey>.yaml`).
- **Realign after every pass** before starting the next. Never tokenize ahead of agreement.

## Working with this project

- Propose, don't impose. Surface a paper's local subgraph for accept/edit/reject; don't
  auto-commit curated judgments.
- Metadata fetches use the OpenAlex/Crossref **polite pool** — always send the `mailto`
  from `config.toml`.
- Dev: Python. Tests are **offline & deterministic** (recorded OpenAlex/Crossref fixtures +
  saved PDF-text snippets) — no live network in the test suite.
