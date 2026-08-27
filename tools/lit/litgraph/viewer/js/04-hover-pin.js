// Hover-isolate: hovering a slice row (or a broad synthesis node) LIGHTS the edges incident on
// it — the rest of the board drops to scaffolding or goes out entirely, per edgeVis — and each
// counterpart card lights up (.hl), so the paper an edge touches is visible even while its slice
// is still folded. (It does not make every other arrow disappear; that comment was two rewrites
// stale. Nothing here decides visibility — edgeVis is the only place that does.)
function setHover(h){
  if (samePin(h, unpinned)) return;                 // still on the target we just released
  unpinned = null;
  if (h ? (hover && h.cardId === hover.cardId && h.sid === hover.sid) : !hover) return;
  hover = h; redraw();
  aimDockFromHover(h);          // if the docked PDF viewer is open, aim it at this claim's source
}
function hoverRow(el, e){
  let h = null;
  if (el && el.classList.contains("open")) {
    const row = e.target.closest(".slice");
    if (row) h = {cardId: el.id, sid: row.dataset.sid};
  }
  setHover(h);
}
// Click-to-pin: harden a target so it stays bright after the pointer leaves. Pins accumulate;
// clicking the same target again releases just it, a click on empty board space thaws them all.
function togglePin(t){
  const i=pin.findIndex(p=>samePin(p,t));
  if(i>=0){ pin.splice(i,1); unpinned=t; if(samePin(hover,t)) hover=null; }  // release, and stay released
  else { pin.push(t); unpinned=null; }
  redraw();
}
const SID_CLASS = {floor: "fl", model: "fl", grounded: "cl", borrowed: "bo",
                   plausible: "cl", question: "q",
                   // programme layer: a claim's modality, then the feasibility kinds.
                   // "established" reuses the borrowed blue — it *is* grounded elsewhere.
                   established: "bo", proposed: "pr", speculation: "sp",
                   test: "te", "test-at-risk": "ri",
                   capability: "ca", "capability-aspirational": "ri"};

// ── folding in place ─────────────────────────────────────────────────────────────────────
// Folding is a local edit to one node, so the view must not move under it. It did: renderSlices
// replaces the card body wholesale, which destroys the sideways-scrolled `.snodes` and reborns
// it at scrollLeft 0 — every click on a node in column 3 threw the card back to its floors. And
// a whole-card fold halves every column's width, so even a preserved scrollLeft would land
// somewhere else entirely.
//
// So don't preserve a scroll offset; preserve a *node*. The one the human just clicked is where
// their eye is, and it is the same node before and after. Pin its screen position, re-render,
// then put the scrollers back until it is where it was — the card's own `.snodes` first, and
// the board for whatever the card could not absorb (a clamped scroller, or the column above it
// changing height).
const nodeSel = sid => `.snodes .slice[data-sid="${CSS.escape(sid)}"]`;
const grpSel  = g   => `.sgrp[data-grp="${CSS.escape(g)}"]`;
function cornerNode(box){                       // no click to anchor on → the top-left-most node
  const nodes = box.querySelector(".snodes");
  if (!nodes) return null;
  const r0 = nodes.getBoundingClientRect();
  let best = null, bd = Infinity;
  for (const el of nodes.querySelectorAll(".slice[data-sid]")) {
    const r = el.getBoundingClientRect();
    if (r.right < r0.left || r.left > r0.right) continue;      // scrolled out of the body
    const d = (r.left - r0.left) ** 2 + (r.top - r0.top) ** 2;
    if (d < bd) { bd = d; best = el; }
  }
  return best;
}
// `sel` names the anchor inside the card body — it has to be a selector, not the element, because
// the re-render throws that element away and we need to find its replacement.
function renderSlicesInPlace(id, sel){
  const card = document.getElementById("card-" + id);
  const box = card && card.querySelector(".slices");
  if (!box) { renderSlices(id); return; }
  if (!sel) { const c = cornerNode(box); sel = c && nodeSel(c.dataset.sid); }
  const anchor = sel && box.querySelector(sel);
  const r0 = anchor && anchor.getBoundingClientRect();
  renderSlices(id);
  const el = r0 && box.querySelector(sel);
  if (!el) return;
  const nodes = box.querySelector(".snodes");
  let r = el.getBoundingClientRect();
  if (nodes && nodes.contains(el)) {
    // .snodes lives INSIDE the zoomed stage, so its scroll offsets are stage pixels while the
    // rects above are glass pixels — the delta has to come back down through the zoom. The board
    // below doesn't: it is the scroll port the transform hangs under, so its own space is glass.
    const bz = boardZoom();
    nodes.scrollLeft += (r.left - r0.left) / bz;
    nodes.scrollTop  += (r.top  - r0.top) / bz;  // no-op while .snodes only scrolls sideways
    r = el.getBoundingClientRect();
  }
  board.scrollLeft += r.left - r0.left;          // the remainder is the board's to make up
  board.scrollTop  += r.top  - r0.top;
}

// Click routing on a curated card: closed → click anywhere focuses it; open → the header
// collapses it (or promotes a context-opened card to focus), and slice rows fold (a paper's
// graph) or drill (an aim's outline).
function cardClick(e, el, level, key){
  const id = `${level}:${key}`;
  if (e.target.closest(".cabsx") && el.classList.contains("open")) {
    // the abstract fold. Keyed by citekey, so every instance of this paper on the board turns
    // together — and applied by toggling a class rather than re-rendering, because the abstract is
    // the only thing on the card that changes.
    if (absOpen.has(key)) absOpen.delete(key); else absOpen.add(key);
    const on = absOpen.has(key);
    document.querySelectorAll(`.card.curated[data-key="${CSS.escape(key)}"]`)
      .forEach(c => c.classList.toggle("absopen", on));
    redraw();                                     // the card's height moved → its arcs re-anchor
    return;
  }
  if (e.target.closest(".sfold") && el.classList.contains("open")) {
    // the whole card at once: fold every slice to its badge, or give the text back. Folded is
    // how the graph is READ — 26 rows of prose is a scroll, 26 badges is a diagram.
    const {rows} = localDag(PAPERS[key]);
    const s = sFold.get(id) || new Set();
    if (rows.length && rows.every(n => s.has(n))) s.clear(); else rows.forEach(n => s.add(n));
    sFold.set(id, s);
    renderSlicesInPlace(id); redraw();
    return;
  }
  if (e.target.closest(".sbar") && el.classList.contains("open")) {
    // the slice-graph fold — the bar itself, checked after `.sfold` because that toggle sits
    // inside it. Rows appear/vanish, so this is a real re-render and the edge layer re-decides
    // every arc from the new state (see renderGraph).
    if (sliceOpen.has(id)) sliceOpen.delete(id); else sliceOpen.add(id);
    renderSlicesInPlace(id); redraw();
    return;
  }
  const grp = e.target.closest(".sgrp");
  if (grp && el.classList.contains("open")) {          // fold/unfold an entry sub-group
    const gkey = `${id}::${grp.dataset.grp}`;
    if (grpCollapsed.has(gkey)) grpCollapsed.delete(gkey); else grpCollapsed.add(gkey);
    renderSlicesInPlace(id, grpSel(grp.dataset.grp));
    redraw();                                          // rows appear/vanish → edges re-anchor
    return;
  }
  const row = e.target.closest(".slice");
  if (row && el.classList.contains("open")) {
    togglePin({cardId: el.id, sid: row.dataset.sid});   // harden/release this row (accumulates)
    // A quote-slice click aims the PDF at that exact quote. This used to be hover-only in the
    // browse view, which meant a phone could never see a highlighted quote at all: there is no
    // hover to aim with, so the dock sat on page 1 of the paper no matter what you tapped. Click
    // now aims it everywhere — on desktop that's a no-op confirming what the hover already did
    // (aimDock early-returns when it's already parked on this claim). Aiming never OPENS the
    // PDF: with the dock shut the aim is just remembered, and the next explicit 📄 lands on it.
    if (row.classList.contains("pdf-src")) aimDock(key, row.dataset.sid);
    // an aim's row drills its branch; a paper's row has no branch to drill — every slice is
    // already on screen — so the click trades that row's text for its badge instead.
    if (row.classList.contains("drillable")) toggleDrill(id, row.dataset.path);  // drill + rebuild
    // …and a narrative's row is neither: a bullet has no branch and no badge worth trading a
    // sentence for. The togglePin above is the whole gesture — click a line, its citations stay lit.
    else if (row.dataset.sid && !PAPERS[key].aim && !PAPERS[key].narr) {
      const s = sFold.get(id) || new Set();
      if (s.has(row.dataset.sid)) s.delete(row.dataset.sid); else s.add(row.dataset.sid);
      sFold.set(id, s);
      renderSlicesInPlace(id, nodeSel(row.dataset.sid));
      redraw();                                        // row height changed → arcs re-anchor
    }
    return;
  }
  if (el.classList.contains("open")) {
    if (e.target.closest(".chd")) {
      if (open.has(id)) {
        open.delete(id); drill.delete(id); grpSeeded.delete(id); sFold.delete(id);
        sliceOpen.delete(id); sliceSeeded.delete(id);   // reopen lands on the default view
        for (const g of [...grpCollapsed]) if (g.startsWith(id + "::")) grpCollapsed.delete(g);
      }
      else open.add(id);                      // context-opened card → promote to focused
      rebuild(id);                            // the card you clicked stays where you clicked it
    }
    return;
  }
  open.add(id); rebuild(id);                   // collapsed card clicked open — reading the graph, not the PDF
}

function toggleDrill(id, path){
  let s = drill.get(id);
  if (!s) { s = new Set(); drill.set(id, s); }
  if (s.has(path))                       // fold the whole branch under this row
    for (const p of [...s]) { if (p === path || p.startsWith(path + "/")) s.delete(p); }
  else s.add(path);
  rebuild(id);
}

