// ── find in the PDF ──────────────────────────────────────────────────────────────────────
// The reader's own text search, and it has to be ours because the page is a raster. The
// browser's Ctrl+F can only see the transparent word overlay, and that is built lazily, for
// the pages you have already visited *in text mode* — so it would search a fraction of the
// document and report the result as if it were all of it. That is the failure worth avoiding:
// not a missing feature, a search that lies. So the server searches the whole PDF instead
// (/search/<key>.json), with the same folded matcher that places a quote's highlight — case,
// spacing, hyphenation seams and ligatures all folded away, which is why "cell-cell" finds a
// line-broken "cell- cell" and why "cell" is also inside "excellent".
//
// A re-aim rebuilds the window from scratch (mountDockDoc), so the hits can't survive one —
// but the QUERY does, and the bar reopens on it, because what you were looking for is still
// what you are looking for after you glance at another claim.
let findQuery = "";
function attachFind(win, key, {body, pages, view}){
  const btn = win.querySelector('.pw-tool[data-t=find]'), bar = win.querySelector(".pw-find");
  if (!btn || !bar) return;
  const input = bar.querySelector("input"), count = bar.querySelector(".pw-fn");
  const steps = bar.querySelectorAll('[data-f=prev],[data-f=next]');
  let hits = [], marks = [], cur = -1, truncated = false, seq = 0, timer = null;
  btn.hidden = false;                              // only the whole-document view offers this

  function clear(){
    for (const els of marks) for (const el of els) el.remove();
    marks = []; hits = []; cur = -1; truncated = false;
  }
  function paint(){
    count.textContent = !input.value.trim() ? ""
      : hits.length ? `${cur + 1}/${hits.length}${truncated ? "+" : ""}` : "none";
    marks.forEach((els, i) => els.forEach(el => el.classList.toggle("on", i === cur)));
    steps.forEach(b => { b.disabled = hits.length < 2; });
  }
  function draw(){                                 // one box per line a hit spans, on its page
    for (const h of hits) {
      const p = pages[h.page], els = [];
      if (p) for (const r of h.rects) {
        const el = document.createElement("div"); el.className = "pw-fh";
        el.style.left = (r[0] * 100) + "%"; el.style.top = (r[1] * 100) + "%";
        el.style.width = ((r[2] - r[0]) * 100) + "%"; el.style.height = ((r[3] - r[1]) * 100) + "%";
        p.div.appendChild(el); els.push(el);
      }
      marks.push(els);
    }
  }
  function go(d){                                  // step to a hit and scroll it into the middle
    if (!hits.length) return;
    cur = (cur + d + hits.length) % hits.length;
    const h = hits[cur], p = pages[h.page];
    if (p) {
      let x0 = 1, x1 = 0, y0 = 1, y1 = 0;
      for (const r of h.rects) { x0 = Math.min(x0, r[0]); x1 = Math.max(x1, r[2]); y0 = Math.min(y0, r[1]); y1 = Math.max(y1, r[3]); }
      const cy = (p.top + (y0 + y1) / 2 * p.h) * view.z;     // base px × the live zoom
      const cx = (x0 + x1) / 2 * view.W0 * view.z;
      body.scrollTop = Math.max(0, Math.min(body.scrollHeight - body.clientHeight, cy - body.clientHeight / 2));
      body.scrollLeft = Math.max(0, Math.min(body.scrollWidth - body.clientWidth, cx - body.clientWidth / 2));
    }
    paint();
  }
  async function run(){
    const q = input.value.trim();
    clear();
    if (q.length < 2) { paint(); return; }         // one character matches half the paper
    const mine = ++seq;
    count.textContent = "…";
    let res = null;
    try { res = await fetch(`search/${key}.json?q=${encodeURIComponent(q)}`).then(r => r.ok ? r.json() : null); }
    catch { res = null; }
    if (mine !== seq || !win.isConnected) return;  // a later keystroke (or a remount) won
    hits = (res && res.hits) || []; truncated = !!(res && res.truncated);
    draw();
    // Land on the hit nearest where the reader already is, not on page 1 — searching for a word
    // you can see on screen should not throw you back to the top of the paper.
    const top = body.scrollTop / (view.z || 1);
    const at = hits.findIndex(h => { const p = pages[h.page]; return p && p.top + h.rects[0][1] * p.h >= top; });
    cur = (at < 0 ? 0 : at) - 1;
    hits.length ? go(1) : paint();
  }
  function open(){
    win.classList.add("finding");
    if (!input.value && findQuery) input.value = findQuery;
    input.focus(); input.select();
    if (input.value.trim() && !hits.length) run();
  }
  function close(){ win.classList.remove("finding"); clear(); paint(); }

  btn.addEventListener("click", () => win.classList.contains("finding") ? close() : open());
  input.addEventListener("input", () => {
    findQuery = input.value;
    clearTimeout(timer); timer = setTimeout(run, 200);
  });
  input.addEventListener("keydown", e => {
    e.stopPropagation();                           // the board's bare-key shortcuts (w, …) must not fire
    if ((e.key === "f" || e.key === "F") && (e.ctrlKey || e.metaKey) && !e.altKey) {
      e.preventDefault(); input.select();          // find-again while already in the box: reselect
    } else if (e.key === "Enter") { e.preventDefault(); clearTimeout(timer); hits.length ? go(e.shiftKey ? -1 : 1) : run(); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  });
  bar.addEventListener("click", e => {
    const b = e.target.closest(".pw-fb"); if (!b) return;
    if (b.dataset.f === "close") close(); else { go(b.dataset.f === "prev" ? -1 : 1); input.focus(); }
  });
  win._find = {open, close};
  paint();
}
// Ctrl/⌘-F belongs to the PDF whenever one is mounted: in the PDF-only window nothing else it
// could mean exists, and in the browse view an open dock IS what you are reading. With no viewer
// on screen we don't touch it, so the browser's own find-in-page still works on the graph.
addEventListener("keydown", e => {
  if ((e.key !== "f" && e.key !== "F") || !(e.ctrlKey || e.metaKey) || e.altKey) return;
  const w = document.querySelector(".pw");
  if (!w || !w._find) return;
  e.preventDefault(); w._find.open();
});
