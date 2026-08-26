# Four states for an edge, decided in one place

**Status:** built · in `viewer/template.html` (`edgeVis`, `pinLive`, `releaseArrows`) · **Date:** 2026-08-05
**Companions:** [CLAUDE.md](../CLAUDE.md) ·
[2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) ·
[2026-08-05-additive-graph-views.md](2026-08-05-additive-graph-views.md)

The board draws five relations on one canvas. Whether any given arrow appeared solid, faint or
not at all was decided in **five different places, written at different times** — so the board's
answer to *"why is that arrow there and that one not"* depended on which relation you happened to
be looking at. Worse, some of those decisions read a **gesture** ("you just clicked this") rather
than a **state** ("this is open"), which is how the board ended up holding arrows anchored to
things you could no longer see.

This is the consolidation. One function decides; every input to it is current state.

---

## 0. The complaint, stated precisely

Two symptoms, one cause each.

**The board got messy and stayed messy.** Expand a run of claims, collapse them again, and the
arrows remained. Measured on the real library with four papers open, the resting board drew
**350 edges**. Most of them were not readable as anything: with four papers open, **155 of the
187** cross-card scaffolding arcs ran further than one screenful, and the worst ran **17,500 px**.
An arc that long is not faint structure. It is a line leaving the screen at one edge and arriving
at another, and it costs exactly as much ink as a line that says something.

**There was no way out.** Clicking empty board space thawed row pins, which is discoverable only
by accident, and it did not release *shown* claims at all. So the natural recovery — collapse
everything — made it worse rather than better, because a pin outlived the card it named.

The cause of the second is worth naming on its own: **a pin names a row, and rows can leave.**
Nothing checked. A collapsed card kept its pins, so arrows stayed lit from an endpoint that was
no longer on screen, and the row you would have clicked to release them was gone with it.

## 1. The rule

Four states, one decision point (`edgeVis`), asked in order:

| state | opacity | means |
|---|---|---|
| **lit** | 0.85 – 0.95 | incident on a pin or the hover — you asked for this one |
| **scaffolding** | 0.20 | both ends are open rows you can see |
| **ghost** | 0.07 | one end dies on the closed border of a shut card |
| **off** | — | nowhere honest to draw it, or uninformative *en masse* |

Three questions get you there.

**Is there an honest place to draw it?** Both ends fell back to their cards with no visible
anchor, or an intra-card rung has a node scrolled out: off. Geometry, not policy.

**If it isn't lit, is it scaffolding at all?** Two clauses, kept deliberately apart because they
are different arguments and neither subsumes the other:

- *Legibility.* An edge whose two anchors **do not fit on the glass at once** is off. This clause
  was simply missing, and it is most of the mess (the 155-of-187 above). It is measured in glass
  pixels, which buys two properties for free: it is **zoom-aware** — zoom out until both ends fit
  and the edge comes back, which is the board's existing "zoom out and it becomes a map" idea
  applied to the edge layer — and it tests the *distance* between anchors and never their
  *position*, so no arrow flickers as you scroll.
- *Density.* An edge touching the **synthesis band** stays dark until you ask. Every paper throws
  one; the fan they make only ever said "many things generalize", which you already knew.

**Are both ends open?** An arrow between two slice rows you can see says *which claim rests on
which*. An arrow dying on the closed border of a card says only *"something in here"* — it cannot
name its own endpoint, because you have not opened the thing it lands on. Those are different
statements, so they do not get the same ink. The second is a **ghost**.

## 2. Why "both ends", when the ask was "at least one"

The ask was *"for an edge to be visible, at least one of the two nodes has to be expanded."*
Taken literally that clause **ghosts nothing**: an edge is only ever born from an open card
(`expandCard` is the only producer), so *every* edge already has at least one open end. Measured
with three papers open:

| both ends open | one end shut | neither open |
|---|---|---|
| 150 | 43 | **0** |

So the rule is implemented from the side that has members — **both** ends open is scaffolding,
otherwise ghost. Same idea, one operator away, and it catches the 43 arrows running into shut
cards that were previously indistinguishable from real structure.

It is properly reversible, which is the state-derived part doing its job: open a ghost's far end
and the split moves to 156/41; close it again and it returns to **exactly** 150/43.

**"Open" is a class check** (`endOpen`), deliberately *not* "did the row rect resolve". The
latter also goes null for a row merely scrolled sideways inside an open card — the two agree
exactly on the resting board, but only one of them holds still while you scroll.

## 3. State, not gesture

Every input to `edgeVis` is current state: what is open, what is pinned, where the anchors are.
Nothing reads *how you got there*. That is the property that makes the layer predictable — the
same board draws the same arrows regardless of the path taken to it, and an expand or a collapse
moves the edge layer *because it moved the state*, not because a handler remembered to.

The suspicion that prompted this — that `fold to graph` and `show statements` left the edge layer
stale — turned out **not** to be a bug. Measured: `fold to graph`, the band's `show statements`,
a per-slice fold and showing a claim each leave a path set **byte-identical to a full
`rebuild()`**. The drawn set was already a pure function of state. What was missing is that
**expansion was never an input to the rule at all** — hence §1's third question. The property is
now asserted in the comment rather than left to luck.

## 4. The way out, and why it is two doors

`releaseArrows()` drops every pinned row and every shown claim. Two callers, nested:

- **`clear arrows · N`** in the HUD, or bare **`c`**. Carries its count, and is *absent* when
  there is nothing held — so the affordance itself reports whether the board is holding anything,
  which is the question you actually have when it looks busy.
- The landing column's **`clear`** is that plus the stubs you summoned by name. A summoned stub is
  a search result, not an arrow, so it survives the smaller door and not the larger one.

Both go through one function, so they cannot drift apart.

Not on `Escape`, on purpose: `Escape` already dismisses the library, the walk, the views menu and
the search box, and overloading it with a fifth meaning makes it unpredictable rather than
convenient. Clicking empty board space still thaws row pins — it stays as the quick one, it is no
longer the only one.

`syncClearBtn()` is called at the end of `redraw()` rather than at each mutation site, because
every state change already ends there. That is the one place the way out can be sure it knows
whether there is anything to clear.

**`pinLive`** is the other half. A pin is dropped the moment its row leaves the board. Both
obvious tests are wrong and it is worth recording why: DOM presence is **too weak** (`.slices` is
`display:none` until the card is open, so a collapsed card still answers a `[data-sid]` query with
every row it ever rendered — this was measured failing), and the row rect is **too strong** (null
for a row merely scrolled sideways). `offsetParent !== null` is the one that means what we want.

## 5. What it cost

Measured against the real library, four papers open: resting drawn edges **350 → 189**. Zoomed to
58%: **189 → 202**, the legibility clause handing edges back as the glass gets roomier.

A three-round stress — eight papers, pin rows, show and un-show ten claims, collapse everything —
left the old build holding **8 stale pins**; the new one ends at 0 pins, 0 shown, 0 drawn, button
hidden, console clean.

## 6. Deliberately not decided

- **The ghost weight, 0.07.** It is the one number here picked by eye rather than measured. It
  sits next to `OP_SCAFFOLD` at the top of the rule for exactly that reason.
- **Whether a ghost should be reachable.** It currently cannot be hovered or clicked into
  usefulness; it is a hint that something lands there. Making a ghost a target for "open the far
  end" is plausible and unbuilt.
- **Whether the band's density clause should be a threshold rather than a flag.** Right now band
  edges are dark unless lit, full stop. A count-based version ("show them when few enough are in
  play") is more nuanced and more surprising; not attempted.

---

## 7. Addendum, 2026-08-19: quiet mode — the reader gets a hand on the rule

**Status:** built · `viewer/js/12-landing.js` (`setQuiet`, the HUD's `quiet arrows`, `q`) ·
`08-edges.js` (`quietEdges`, clause **2c**)

§4 gave the board one exit — `clear arrows`, which **releases what you are holding**. That is the
right door when the mess is yours. It does nothing at all when the mess is the *resting* board:
scaffolding and ghosts you never asked for, which by construction survive a clear because there is
nothing to release.

So there is now a second, orthogonal control: **quiet arrows** (HUD toggle, `q`). It hides every
edge that is not **lit** — the resting board goes dark, and a pinned row or the row under the
pointer keeps its full fan. Together they cover the two halves of one complaint, and neither does
the other's job: clearing a board with no pins changes nothing, and quieting one does not release
the pins it is deliberately keeping.

Three properties worth keeping true:

- **It is one clause, in the one place.** `if(quietEdges) return E_OFF;` sits immediately after
  the lit test in `edgeVis` — not a second pass over the edge list, not a class on the SVG. The
  whole point of §1 is that one function answers "why is that arrow there"; a mode that answered
  it somewhere else would undo that.
- **It is state, not a gesture** (§3). A standing preference, read the same way on every redraw,
  so the board still draws the same arrows however you arrived at it. `redraw()` alone applies it:
  nothing about the layout moved.
- **It sits after `lit`, on purpose.** Quiet is a claim about the *resting* board. A mode that
  also darkened the pinned and hovered fans would not be quiet, it would be off — and the hover
  fan is exactly how you ask a quiet board a question.

Measured, real library, two papers open with one slice graph unfolded: resting **14 → 0** drawn
edges; pinning one row brings back **4**.
