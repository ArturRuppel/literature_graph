// ── tooltip ────────────────────────────────────────────────────────────────────────────
// Served over HTTP (`lit serve`), the tooltip upgrades: pdfs.json says which curated
// papers have a servable PDF, hovering embeds its first page, clicking the preview opens
// the full PDF in a new tab. Opened from file:// (`lit build` output) it stays inert.
const LIVE = location.protocol.startsWith("http");
// touch/no-hover devices synthesize mouseenter/move on tap (iOS), which would pin a sticky
// tooltip and latch soft previews. Hover-only affordances are gated on a real hover pointer;
// the load-bearing actions (tap to open/pin) are click/pointer-based and unaffected.
const HOVER = matchMedia("(hover: hover)").matches;
const QUERY = new URLSearchParams(location.search);
// A touch-only device cannot meaningfully manage the desktop's three OS windows. Its curation
// route keeps the isolated card and PDF dock together in this one installed-app window.
const MOBILE_CURATE = LIVE && QUERY.has("mobile");
const PHONE_LAUNCH = matchMedia("(hover: none) and (pointer: coarse)").matches;
// A mode marker only — the split layout no longer branches on it. Phone curation used to carry its
// own stacked-pane CSS; the dock now splits on the window's long axis in every mode alike.
if (MOBILE_CURATE) document.body.classList.add("mobile-curate");
// COCKPIT = the server can open a curation terminal window (it found an emulator), injected by
// `lit serve` as GRAPH.cockpit ({terminal: "kitty"}). Entering curation turns this graph window
// into the card, opens the PDF, and asks the server for the terminal. This says whether POST /term
// can produce the terminal. Not a mode: the graph is only replaced after the curator enters.
const COCKPIT = GRAPH.cockpit || null;
// DRIVE: this document is a paper's curation card — /preview.html?key=…&drive=1, opened in its own
// OS window. It shows one paper's isolated subgraph; a quote-click POSTs the weld to the focus wire
// (aiming the separate PDF window) rather than mounting a pane of its own. The graph is never DRIVE.
const DRIVE = LIVE && QUERY.has("drive") && !MOBILE_CURATE;
if (DRIVE) document.body.classList.add("cardwin");
// Hot-reload the DRIVE card IN PLACE on a YAML edit: fetch the freshly-isolated subgraph, refill
// the data objects (const bindings survive — we mutate contents, never reassign), rebuild from the
// preserved reading state (open/drill/grpCollapsed/stacks are untouched), and restore scroll. The
// card window watches the focus wire's `data_version` itself (it's a top-level window now, with no
// parent to tell it) — far gentler than reloading, which tore down the DOM and collapsed the card
// the human was mid-read on.
async function refreshDriveData(){
  const key = new URLSearchParams(location.search).get("key");
  if (!key) return;
  let g; try { g = await fetch(`preview.json?key=${encodeURIComponent(key)}`).then(r => r.ok ? r.json() : null); }
  catch { return; }                                    // server gone / broken edit → keep the last good render
  if (!g || !g.papers) return;
  for (const k in PAPERS) delete PAPERS[k]; Object.assign(PAPERS, g.papers);
  for (const k in BROAD)  delete BROAD[k];  Object.assign(BROAD,  g.broad || {});
  for (const k in STUBS)  delete STUBS[k];  Object.assign(STUBS,  g.stubs || {});
  ORDER.length = 0; ORDER.push(...(g.order || []));
  buildBroadLinks();
  const sc = document.scrollingElement || document.documentElement;
  const y = sc.scrollTop, x = board.scrollLeft;        // rebuild churns the DOM; hold the reading spot
  rebuild();
  sc.scrollTop = y; board.scrollLeft = x;
  // The walk indexes the same objects, so it has to be rebuilt from them too — otherwise a slice
  // the agent just added stays missing from the roster, which is the one thing it must never do.
  const W = window.litWalk;
  if (W) {
    const st = document.getElementById("walkStage"), sy = st ? st.scrollTop : 0;
    W.reindex();
    if (!W.focus || !W.nodes[W.focus]) W.standOnCard();   // focus may have been edited away
    if (W.isOpen()) { W.paint(); if (st) st.scrollTop = sy; }
  }
}
// The card window keeps itself current: poll the focus wire purely for its `data_version` and
// refresh in place when the YAML underneath changes (the agent writing a pass, `lit tag`, an edit
// by hand). Same 500 ms tick the PDF window polls on; unchanged version → no work.
if (DRIVE || MOBILE_CURATE) (function(){
  let seen = null;
  setInterval(async () => {
    let f; try { f = await fetch("focus").then(r => r.ok ? r.json() : null); } catch { return; }
    if (!f || f.data_version == null) return;
    if (seen === null) { seen = f.data_version; return; }   // baseline: first poll after opening
    if (f.data_version !== seen) { seen = f.data_version; refreshDriveData(); }
  }, 500);
})();
// Leaving the card WITHOUT finishing: ✓ finish is a statement about the paper (it comes off the
// worklist), and it was the only way out of this window — so stepping back to the graph to look
// something up meant declaring the curation over. This button is the plain exit: navigate back to
// the browse view and leave `[curation] active` untouched, so the paper is still on the "in
// progress" pill and one click re-enters its card. Nothing else is disturbed — the PDF and terminal
// windows are separate OS windows, and the wire keeps its aim.
if (DRIVE || MOBILE_CURATE) (function(){
  const btn = document.getElementById("backBtn");
  const key = new URLSearchParams(location.search).get("key");
  if (!btn) return;
  btn.hidden = false;
  btn.title = key ? `back to the graph — ${key} stays on the worklist`
                  : `back to the graph`;
  btn.addEventListener("click", () => {
    const u = new URL("index.html", location.href); u.search = ""; u.hash = "";
    location.assign(u.href);
  });
})();
// Finishing from the card: the symmetric close of the move that opened it. Entering curation turned
// the graph window into this card; ✓ finish drops the paper off `[curation] active` (the same POST
// /active the picker row's ✓ makes — one writer, config.set_active) and turns this window back into
// the graph, where the paper is no longer filtered out. The PDF and terminal windows are left alone:
// they're separate OS windows this document never owned a handle on, and closing a terminal
// mid-session is the curator's call, not ours.
if (DRIVE || MOBILE_CURATE) (function(){
  const btn = document.getElementById("finishBtn");
  const key = new URLSearchParams(location.search).get("key");
  if (!btn || !key) return;
  btn.hidden = false;
  btn.title = `finish: return ${key} to the graph and reopen it here`;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    let r = null;
    try {
      r = await fetch("active", {method: "POST",
        body: JSON.stringify({citekey: key, active: false})}).then(r => r.ok ? r.json() : null);
    } catch { /* server gone — fall through to the alert */ }
    if (!(r && r.ok)) { btn.disabled = false; return alert(`could not return ${key} to the graph`); }
    const u = new URL("index.html", location.href); u.search = ""; u.hash = "";
    location.assign(u.href);                       // the card window becomes the graph again
  });
})();
// The PDF-only window: this document renders no graph, just a full-bleed PDF pane. Two ways in,
// one body — DETACHED is the browse view's popped-out dock (mirrored from the graph window over
// the "lit-pdf" BroadcastChannel); FOCUSWIN is curation's paper window (aimed by polling the focus
// wire, so `lit focus` and card clicks both steer it). Either implies LIVE and not DRIVE.
const DETACHED = LIVE && QUERY.has("detached");
const FOCUSWIN = LIVE && QUERY.has("focus");
const PDFWIN = DETACHED || FOCUSWIN;
if (PDFWIN) document.body.classList.add("detached");     // hide graph chrome before it paints
// the move (delta §3): papers on the in-progress worklist are pulled OUT of the browse view —
// they live in their own curation windows, not the graph column. The DRIVE card shows one
// isolated (active) paper, so it must not filter; a static build carries no active list.
const ACTIVE = new Set((DRIVE || MOBILE_CURATE) ? [] : (GRAPH.active || []));
// The collapsible PDF viewer lives in the browse view only. Entering curation already opens the
// separate PDF window and mutates this browse window into the DRIVE card, so the card owns no dock.
const pdfToggle = document.getElementById("pdfToggle");
if (pdfToggle && LIVE && !DRIVE) {
  pdfToggle.hidden = false;
  pdfToggle.addEventListener("click", toggleDock);
}
// search is a browse-view affordance; the DRIVE card window shows one isolated paper, so drop
// the box there (chip clicks then no-op via runSearch's null guard)
if (DRIVE || MOBILE_CURATE) { const sb = document.getElementById("search"); if (sb) sb.remove(); }
let PDFS = null;                       // Set of citekeys with a PDF (null until fetched)
if (LIVE) fetch("pdfs.json").then(r => r.ok ? r.json() : [])
  .then(l => {
    PDFS = new Set(l);
    if (MOBILE_CURATE && ORDER.length) {
      const key = ORDER[0];
      open.add(`0:${key}`); loadDock(key); rebuild();  // arrive with both card and PDF visible
    }
  }).catch(() => { PDFS = new Set(); });
// The tip must survive the hop from card to tip (to click the preview): hiding is
// deferred a beat (dropTip) and cancelled when the pointer arrives (keepTip).
let tipHide = null;
function keepTip(){ if (tipHide) { clearTimeout(tipHide); tipHide = null; } }
function dropTip(){
  keepTip();
  tipHide = setTimeout(() => { tip.style.display = "none"; tip.dataset.key = ""; }, 140);
}
tip.addEventListener("mouseenter", keepTip);
tip.addEventListener("mouseleave", () => { tip.style.display = "none"; tip.dataset.key = ""; });
// touch: a tap-pinned tip (from a stub) has no mouseleave — dismiss it on the next tap that
// isn't inside the tip or on another stub (capture, so it beats the stub's own re-show handler).
addEventListener("click", e => {
  if (!HOVER && tip.style.display === "block"
      && !e.target.closest("#tip") && !e.target.closest(".card.stub")) {
    tip.style.display = "none"; tip.dataset.key = "";
  }
}, true);

// ── stub abstracts (live-fetched on hover, serve-only) ───────────────────────────────────
// A stub carries title/authors/journal/year in stubs.yaml but NOT its abstract — persisting
// 50–100 reference abstracts per curated paper would balloon the diffable YAML. Instead the
// abstract is fetched on demand from OpenAlex (by DOI) the first time a stub card is hovered
// under `lit serve`, cached for the session, and never written to disk. Static `lit build`
// (no server, no LIVE) just shows the bib-only note.
const esc = s => String(s).replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const stubAbsCache = new Map();          // citekey -> string | null (none/failed) | undefined (in-flight)
function stubAbstract(key, p){
  if (!LIVE || !p.doi) return `<div class="nopdf">uncurated stub — bib metadata only</div>`;
  const cached = stubAbsCache.get(key);
  if (typeof cached === "string") return `<div class="tabs">${esc(cached)}</div>`;
  if (cached === null) return `<div class="nopdf">uncurated stub — no abstract available</div>`;
  fetchStubAbstract(key);                // unfetched: kick it off, show a pending note this render
  return `<div class="nopdf" id="tabsPending">fetching abstract…</div>`;
}
async function fetchStubAbstract(key){
  if (stubAbsCache.has(key)) return;     // in-flight or done — don't refetch
  stubAbsCache.set(key, undefined);      // mark in-flight (has() true, so the guard above holds)
  let text = null;
  try {
    const r = await fetch(`stub-abstract?key=${encodeURIComponent(key)}`);
    if (r.ok) { const j = await r.json(); text = j && j.abstract ? j.abstract : null; }
  } catch { text = null; }
  stubAbsCache.set(key, text);
  // patch the live tip in place if it's still showing this stub (dataset.key guards re-render)
  if (tip.dataset.key === key && tip.style.display === "block") {
    const slot = tip.querySelector("#tabsPending");
    if (slot) slot.outerHTML = (typeof text === "string")
      ? `<div class="tabs">${esc(text)}</div>`
      : `<div class="nopdf">uncurated stub — no abstract available</div>`;
  }
}

// The hover preview is a pure metadata card now — title · all authors · journal · year · a
// (non-clickable) first-page thumbnail. Opening the PDF is the docked viewer's job (a card click
// loads it), so the tip no longer opens anything; it's a bib peek that holds still under the pointer.
function showTip(e, key, el, force){
  if (!HOVER && !force) return;        // touch: only the explicit tap-to-pin path (force) shows the tip
  keepTip();
  tip.style.display = "block";
  if (tip.dataset.key === key) return; // pinned: hold still while the same target is hovered
  tip.dataset.key = key;
  const cur = !!(PAPERS[key] && PAPERS[key].cur);
  const p = PAPERS[key] || STUBS[key];
  let thumb;
  if (cur && !LIVE) thumb = `<div class="nopdf">PDF preview needs <code>lit serve</code></div>`;
  else if (cur && (!PDFS || !PDFS.has(key))) thumb = `<div class="nopdf">no PDF served (${key}.pdf)</div>`;
  else if (cur) thumb = `<div class="pdf live"><img src="preview/${key}.png" alt="first page of ${key}.pdf"></div>`;
  else thumb = stubAbstract(key, p);   // uncurated: no PDF — show the abstract (live-fetched) instead
  const auth = (p.authors && p.authors.length) ? `<div class="tauth">${authLine(p.authors)}</div>` : "";
  const bib = [p.journal || venueFromKey(key), p.year].filter(Boolean).join(" · ");
  tip.innerHTML = `<div class="ttitle">${p.title || key}</div>${auth}`
                + `<div class="meta">${bib}</div>${thumb}`;
  // pin beside the hovered card — right of it, flipping left when there's no room — NOT
  // at the cursor, so the pointer can travel into the tip to read a long author list
  const r = ((el && el.closest(".card")) || el || e.target).getBoundingClientRect();
  const pad = 10, w = 300, h = tip.offsetHeight;
  let x = r.right + pad;
  if (x + w > innerWidth) x = r.left - w - pad;
  x = Math.max(8, Math.min(x, innerWidth - w - 8));
  const y = Math.max(54, Math.min(e.clientY - 24, innerHeight - h - 8));
  tip.style.left = x + "px"; tip.style.top = y + "px";
}

