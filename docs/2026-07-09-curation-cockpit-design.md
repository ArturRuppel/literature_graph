# Curation cockpit — design direction (the focus channel + curate mode)

**Status:** shipped & browser-verified (focus channel + docked pane + `lit focus` + card-click +
terminal + `lit serve --curate`), then **reframed** — the global-mode framing here is superseded by
[the in-progress-zone redesign](2026-07-09-cockpit-redesign-in-progress-zone.md) (curation becomes a
per-paper *place*, not a whole-window mode). The *mechanisms* below (focus wire, docked pane,
terminal, wrapper) all carry over; only their framing/triggers change. · **Date:** 2026-07-09 ·
companion to [CURATION.md](../CURATION.md) and the
[visualization design](2026-06-25-visualization-design.md)

Turn curation from a **three-window shuffle** into one cockpit. Today a proposition lives in
three places — prose in the chat, a card in the WIP view, quotes in the PDF — and the human
carries it by hand between them: propose → "render it as a card" → go check the quotes in the
paper → back to the chat. This doc removes the carrying.

The load-bearing idea is a **focus channel**: one shared "what are we looking at right now"
wire that both the human's clicks *and* the agent's commands drive, so the card pane and the
PDF pane always show the same thing, and the agent can mark a passage in the human's PDF mid-
conversation. Everything else — the docked panes, the embedded terminal — bolts onto that wire.

Serve-only, single-user, local. None of this touches the static `lit build` artifact.

---

## 1. Scope

**In scope**

- A **focus channel** on the `lit serve` process: in-memory `{citekey, quote} → resolved loc`,
  set by `POST /focus`, read by `GET /focus`, polled by the viewer.
- A **`lit focus`** CLI verb that POSTs to the running server — the agent's hand on the wire.
- **Curate mode** in the viewer: a three-pane layout (card strip · docked PDF · terminal) where
  the PDF is a *docked pane* driven by focus, not a floating pinned window.
- An **embedded terminal pane** (ttyd + Claude Code session resume) with **persistent-per-paper**
  conversations and **click-to-preload**.

**Out of scope**

- Any change to `lit build`'s static output, or to the default (non-curate) viewer behavior.
- Accept/edit/reject buttons. Curated YAML is still written by the agent through the chat
  (CLAUDE.md: *no buttons; the human interacts with the tool through the agent*).
- Multi-user / remote / auth beyond binding to loopback.
- Replacing the existing floating quote-windows in the *default* view — they stay; curate mode
  is a distinct layout.

---

## 2. The three panes (curate mode)

```
┌───────────────┬───────────────────────────────────┐
│               │                                   │
│   CARD        │            PDF  (docked)           │
│   (scratch    │      always shows the focused      │
│    proposi-   │      weld — page + highlight       │
│    tion,      │                                   │
│    full       ├───────────────────────────────────┤
│    height)    │                                   │
│               │   TERMINAL  (ttyd → tmux → claude) │
│               │   one persistent session per paper │
│               │                                   │
└───────────────┴───────────────────────────────────┘
```

- **Left, full height — the card.** The active paper's slices (the live scratch proposition
  during a curation pass, or the curated card once tokenized). Clicking a slice sets focus.
- **Right-top — the docked PDF pane.** *This is the key simplification.* In the default view a
  quote preview is a floating window created per click (`pdfWindows` map + `nudgeIfColliding`),
  which is why they pile up. In curate mode there is exactly **one** PDF surface, docked, that
  re-aims whenever focus changes. There is no window to stack because there is no window —
  nothing to pile up, by construction.
- **Right-bottom — the terminal.** §5. Optional; the focus channel is fully useful with the
  human's real terminal beside the browser, so this pane ships last.

Entered via `lit serve --curate` (or a `?mode=curate` route / a header toggle — bikeshed at
build time). The default view is untouched.

---

## 3. The focus channel — the protocol

This is the 80%. Everything is one small piece of server state and two routes.

### 3.1 Server state

`_Server` gains one field, ephemeral (never persisted, serve-only):

```python
self.focus = {"seq": 0, "citekey": None, "quote": None, "loc": None}
```

`seq` is a monotonic counter bumped on every successful set — the cheap change-detector the
poller compares against. `loc` is the resolved `{page, rects}` (same shape as `quote_loc`), or
`null` when the quote didn't resolve.

### 3.2 `POST /focus` — set the wire

Request: `{"citekey": "Chen2021Sys", "quote": "the exact sentence to mark"}`

Both drivers hit this one route:

- **The agent**, via `lit focus` (§4).
- **A card click** in the viewer — the click handler POSTs `{citekey, quote}` for the clicked
  slice rather than driving the pane directly. *One source of truth, one code path:* the pane is
  **always** driven by the focus poll, never by the click directly. A click just moves the wire;
  the poll re-aims the pane a beat later.

On receipt the server resolves geometry with the existing `locate_quote(pdf, quote)` (the same
matcher `/resolve` uses), stores `{seq+1, citekey, quote, loc}`, and returns the resolved record:

```json
{ "seq": 42, "citekey": "Chen2021Sys", "quote": "…", "loc": {"page": 4, "rects": [[…]]} }
```

Validation mirrors `/resolve`: `_CITEKEY.match(key)`, PDF exists, non-empty quote → else `404`.

### 3.3 Resolution semantics — verbatim, fuzzy, and the graceful floor

- **Verbatim quote** → `locate_quote` returns `{page, rects}`; the pane scrolls to the page and
  draws the highlight box. The common case.
- **Fuzzy ask** ("show me the percolation bit") is resolved *before* it hits the wire. That is
  the **agent's** job: the agent reads the `<citekey>.md` full text, picks the actual sentence,
  and focuses *that* verbatim string. The wire only ever carries resolvable text; fuzziness is
  handled upstream, in the conversation.
- **Graceful floor.** If a quote still fails to resolve (`loc == null`), the pane switches to the
  paper and scrolls to its top rather than doing nothing, and the `POST` response carries
  `loc: null` so the agent sees the miss and can retry with cleaner text. A focus never
  silently no-ops.

### 3.4 `GET /focus` — read the wire

Returns the current record verbatim (`{seq, citekey, quote, loc}`). Cheap, `no-store`.

### 3.5 The poll

The viewer polls `GET /focus` on a short interval (~500 ms — a curation-speed wire, not a
game loop) and compares `seq` to the last one it acted on. On change it re-aims the docked PDF
pane: load the paper if `citekey` changed, scroll to `loc.page`, redraw the highlight from
`loc.rects` (reusing `mountDoc`'s existing rect-overlay code). No change → do nothing.

Polling, not SSE: it's one tiny JSON on loopback every half-second, the code is trivial, and it
survives the server restarting mid-session without a reconnect dance. SSE is a later nicety if
the poll ever feels laggy, which at curation cadence it won't.

### 3.6 Why a wire and not direct DOM

Because the terminal pane is a sealed iframe (§5) — the embedded agent can't touch the parent
page's DOM. Routing *everything* (even same-page clicks) through the server means the agent and
the human drive the panes through the exact same mechanism, and the iframe boundary stops
mattering. The server is the shared bus; the agent just runs `lit focus`.

---

## 4. `lit focus` — the agent's hand on the wire

```
lit focus <citekey> --quote "<verbatim sentence>"    # mark this passage in the human's PDF pane
lit focus <citekey> --slice <sid>                    # focus a slice's weld by id (looks up its quote)
```

A thin client: resolve the running server's address (the port `lit serve` is on — from a
pidfile/known port, detail at build), `POST /focus`, print the resolved record (page, matched?)
so the agent gets immediate feedback on whether the quote landed. If no server is running, it
says so and exits non-zero. That's the whole verb.

This is what makes "mark that sentence for me" real: the agent runs `lit focus`, the human's
docked PDF pane jumps to the sentence, no refresh, no button.

---

## 5. The terminal pane — persistent-per-paper, click-to-preload

The hacky-local answer, and it's off-the-shelf: **ttyd** serves any command as a browser
terminal (xterm.js + websocket, one binary), embedded as an `<iframe>` in the bottom-right
pane. No PTY/websocket/xterm code of ours.

### 5.1 Persistence = a transcript file, resumed by directory

A Claude Code conversation persists as a **transcript file on disk** — nothing needs to keep
running. Sessions are stored per working directory and *scoped* to it, so a **per-paper working
directory is the natural key**: give each paper a hidden folder `.sessions/<citekey>/`, and
`claude --continue` run inside it resumes *that paper's* conversation, with zero session-id
bookkeeping. (We never parse the transcript JSONL — its format is internal and version-fragile —
we only ever hand it back to `claude --continue`.)

> **Correction (build reality).** The first draft assumed the session would inherit `CLAUDE.md` /
> `CURATION.md` by Claude Code's walk **up** the tree. That fails here: curation runs against the
> **data repo** (`--root`), but the instructions live in the **code repo** — different trees. So
> cwd is used *only* as the resume key; the instructions reach the session another way — the seed
> **preload prompt injects the explicit `CURATION.md` path and the data root**. cwd location then
> doesn't matter for context, which frees `.sessions/` to sit wherever (gitignored either way).

ttyd runs a small wrapper instead of `claude` directly (verified end-to-end against a stubbed
`claude`): `cd` into the paper's folder, then on **first visit** run `claude "<preload>"` (seed
it), and on **every later visit** run `claude --continue` (resume). A marker file distinguishes
the two, so we never depend on `--continue`'s no-session exit behavior. The wrapper takes the
citekey from ttyd's `--url-arg` (the iframe's `?arg=<citekey>`) and reads its roots from the
environment the launcher sets:

```sh
key="$1"; sess="$LIT_SESSIONS"; data="$LIT_DATA_ROOT"; docs="$LIT_DOCS"
dir="$sess/$key"; mkdir -p "$dir"; cd "$dir"
if [ -e .seeded ]; then exec claude --continue
else : > .seeded
     exec claude "We are curating $key. Data root: $data (pass --root there to lit). Read \
$docs/CURATION.md and follow its four-pass protocol, one pass at a time. Drive my PDF pane with \
lit focus $key --quote \"…\". Pick up from curated/$key.yaml."; fi
```

The citekey **is** the conversation's identity, via its folder. The preload fires only once, on
seed; thereafter it's your ongoing session, and `/clear` · `/compress` are your context knobs
inside it. Crucially: **no tmux, no detached process.** Click away and the `claude` process
simply ends — the transcript is already written, and the next click resumes it from disk.

### 5.2 Click-to-preload

Clicking a paper in the app:

1. writes the **current curation target** (citekey + resolved pass + scratch path) somewhere the
   ttyd wrapper reads,
2. reloads the terminal iframe,
3. the wrapper `cd`s into `.sessions/<citekey>/` and either **seeds** (first visit) or
   **`--continue`s** (resume), per §5.1.

The preload prompt seeds the session on first visit: *"We're curating `<citekey>` at pass N. The
scratch proposition is at `<path>`. Drive Artur's PDF pane with `lit focus`. Read CURATION.md and
continue."* Repo context (CLAUDE.md, CURATION.md) loads for free because cwd is inside the repo
(§5.1). Click → a session that already knows the paper, whether freshly seeded or resumed.

### 5.3 Nothing to reap — persistence is just files

Because a session is a transcript file and **no process lingers between clicks**, there is
nothing to accumulate and nothing to kill. Off-screen, a paper is just its `.sessions/<citekey>/`
folder and a JSONL under `~/.claude/projects/…` — plain files, as cheap as any other. No process
table to police, no live-session dots, no cap, no `lit sessions` reaper. Clean up a paper's
history by deleting its folder, like any file; want a fresh start on a paper, delete its
`.seeded` marker (or the folder) and the next click re-seeds. This is the whole reason the
transcript-file model wins over keeping processes warm: **the pile-up problem doesn't exist.**

`.sessions/` is gitignored — transcripts are local scratch, never committed.

### 5.4 Safety

Bind ttyd and `lit serve` to `127.0.0.1`. Single-user, local, as specified. A shell over a
socket is only ever reachable from this machine.

---

## 6. Build order

Each stage is useful on its own; each is a natural stopping point.

1. **Focus channel + docked PDF pane.** `POST/GET /focus`, the poll, `lit focus`, and curate
   mode's left-card / right-PDF split. *Useful immediately* with the human's real terminal
   beside the browser — the agent can already drive the PDF. Kills the window pile-up and
   delivers "mark that passage."
2. **Card-click → focus.** Wire the card's slice clicks to `POST /focus` so the human drives the
   same pane the agent does. (Small; folds into stage 1 if convenient.)
3. **Terminal pane.** ttyd iframe over per-paper `.sessions/<citekey>/` + `claude --continue`,
   with the seed-or-resume wrapper. Pure bolt-on; if it ever annoys, the driving still works
   from a real shell — nothing lost.

The dependency is one-directional: the terminal can't drive anything until the focus channel
exists, and the focus channel is valuable without the terminal. So the risky/optional part is
strictly last.

---

## 7. Open questions

- **Curate-mode entry.** Flag (`--curate`), route (`?mode=curate`), or in-page toggle? Leaning
  flag for stage 1, revisit.
- **Server discovery for `lit focus`.** Fixed default port, a pidfile written by `lit serve`, or
  an env var. Pidfile is the least surprising; decide at build.
- **Card pane source in mid-curation.** The left pane wants the *scratch* proposition before it's
  tokenized — reuse `lit preview --scratch` / the `/preview.html` isolate path, pointed at the
  scratch YAML? Likely yes; confirm the scratch file's lifecycle (one per active paper).
- **Does a same-paper `lit focus` need the citekey?** During a session the paper is fixed; the
  verb could default to the terminal's current target and take just `--quote`. Convenience, not
  core.
