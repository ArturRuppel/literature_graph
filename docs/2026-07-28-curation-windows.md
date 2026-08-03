# Curation windows — the cockpit stops being a split panel

**Status:** shipped (2026-07-28) — supersedes the three-pane layout of
[the cockpit redesign](2026-07-09-cockpit-redesign-in-progress-zone.md) §4 and the terminal
transport of [the cockpit design](2026-07-09-curation-cockpit-design.md) §5 · companion to
[CURATION.md](../CURATION.md)

The cockpit put card, PDF and terminal in one browser window, split three ways by a CSS grid with
drag handles. **This drops the split.** Entering a paper now opens **three real OS windows** and
lets the window manager do what it is for.

Everything about *what* the three surfaces are, and the wire between them, survives. What changes
is that each becomes a top-level window instead of a cell.

---

## 1. Why

The split panel was reimplementing the window manager, worse:

- **The grid was a WM in CSS.** Two drag gutters, an `fr`-weight model, a persisted split in
  `localStorage`, a `ResizeObserver` to re-fit the PDF after a drag. All of it to approximate
  tiling — on a machine already running a tiling WM that does it better, across monitors and
  workspaces, with no code of ours.
- **The terminal was the real cost.** `ttyd` in an `<iframe>` is a *simulation* of a terminal:
  a second HTTP server on a second port (7681 collides with a system login ttyd, hence the
  `--term-port` escape hatch), a browser-mediated keyboard where the page's own shortcuts and the
  session's compete, and scrollback that isn't the terminal's. A real emulator has none of those
  problems and is one `Popen` away.
- **Panes couldn't leave.** The PDF couldn't go to the second monitor while the card stayed put;
  the terminal couldn't be full-screened for a long diff. Windows can do all of that for free.

The cockpit's *idea* — curation is a place with three surfaces in view at once — was right. It was
the container that was wrong.

**On going back to three windows.** The original cockpit doc opens by promising to turn curation
"from a three-window shuffle into one cockpit," so this looks like a round trip. It isn't, and the
difference is worth naming: what made the old shuffle painful was not the window *count*, it was
that the human carried the context between them by hand — propose in chat, go render a card, go
find the quote in the PDF. The **focus wire** is what killed the carrying, and the wire is
untouched here. Three windows sharing one wire is not the thing we escaped; three windows sharing
nothing was.

---

## 2. The three windows

Selecting a paper from the "in progress · N" picker performs the whole transition in one click:
the current graph window becomes the card, the PDF opens as the one browser popup, and the server
opens the terminal:

| | Window | What drives it |
|---|---|---|
| **card** | `preview.html?key=…&drive=1` | the paper's isolated subgraph. Quote-clicks POST `/focus`; it polls `data_version` and hot-reloads itself in place when the YAML changes |
| **paper** | `index.html?focus=1` | the PDF, full-bleed. Polls `/focus` and re-mounts when `seq` moves |
| **terminal** | `POST /term` → `kitty -e curate_session.sh <key>` | that paper's persistent Claude session, in a native emulator |

The graph window is deliberately reused as the card. This avoids spending a second popup while
also removing the no-longer-needed parent surface from the curation workspace.

**Each window is self-sufficient.** The old zone had the parent poll `/focus` and `postMessage` the
card iframe; now the card and the paper each poll for what they need. That is one more 500 ms tick
and a good deal less plumbing.

**One PDF window, shared.** The wire holds a single focus, so a second would only mirror the first.
The window is named `litpdf_focus`; the card windows are named per paper (`litcard_<key>`), so
re-entering a paper raises the window it already has instead of spawning another.

**Popup blockers.** Browsers generally authorize only one new window per user gesture. The PDF
uses that allowance; the current graph window becomes the card with `location.assign`, which is a
navigation rather than a popup, and the server spawns the terminal as a native process. The focus
and terminal POSTs settle before navigation so leaving the graph cannot cancel them.

---

## 3. The terminal, natively

`lit serve` resolves an emulator once at startup: `$LIT_TERMINAL` (shell-split, so
`kitty --class litcurate -e` works for a WM rule) else the first of kitty · wezterm · ghostty ·
foot · alacritty · konsole · gnome-terminal · xfce4-terminal · xterm on `PATH`. `POST /term
{citekey}` spawns it running the **unchanged** `curate_session.sh` wrapper — same per-paper
`.sessions/<citekey>/` dir, same seed-or-resume, same `.seeded` marker. Only the transport changed.

Two details the window form forces:

- **`start_new_session=True`** — Ctrl-C on `lit serve` must not take the curation sessions with it.
- **The wrapper holds the window on failure.** A spawned emulator dies with its command, so an
  error that used to sit readably in a pane would now flash and vanish. An `EXIT` trap keeps the
  window up on any non-zero exit; the final `claude` is no longer `exec`'d so the trap still covers
  it.

**Degradation is honest:** no emulator found → no `cockpit` payload → the picker says so and opens
the card and paper windows only. You start the session yourself.

---

## 4. Ledger

**Carries over unchanged:** the `/focus` wire (GET/POST + `seq` + `data_version`) · `buildWin` /
`mountDoc` / `resolveLoc` · `curate_session.sh` and the per-paper `.sessions/` model · the `active`
worklist + `POST /active` + `lit curate` · `lit focus` · the browse view entirely (collapsible
viewer, hover-aim, `⧉ detach`).

**Retires:** `#wipOverlay` and its three-pane grid · the divider drag + `lit.zone.split` persistence
· the `.wo-*` / `.pw-zone` CSS · `setTerm` / `TERM_ORIGIN` · **ttyd** as a dependency ·
`_spawn_ttyd` · `lit serve --term-port` · the parent-polls-and-postMessages card refresh.

**Changes:** `GRAPH.cockpit` now means "the server can open a terminal window" and carries
`{terminal: "<emulator>"}` instead of `{term_port: N}` · `?detached=1` and the new `?focus=1` share
one PDF-only window body (`PDFWIN`), differing only in driver — BroadcastChannel vs focus poll.

---

## 5. Open questions

- **WM placement.** Nothing tells the compositor these three belong together. A Hyprland rule
  keyed on `--class litcurate` (via `$LIT_TERMINAL`) plus a window rule on the popup titles could
  put a session on its own workspace, laid out the same way every time. Worth doing once the
  windowed flow has some mileage; deliberately not baked into the tool.
- **Several papers at once.** Each gets its own card window and they all share one PDF window,
  which is right for a wire that holds one focus — but switching papers silently re-aims the shared
  window. Fine for two; revisit if the worklist grows.
- **Closing a session.** Returning a paper to the graph (✓ — either the picker row's, or the card
  window's own **✓ finish curation** HUD button, which navigates that window back to the graph)
  leaves the PDF and terminal windows open. Harmless, but a "close this paper's windows" action
  could be worth it — the card can't do it itself: it holds no `window.open` handle on the PDF
  (that popup was opened by the graph window before it navigated into the card), and the terminal
  is the server's child.
