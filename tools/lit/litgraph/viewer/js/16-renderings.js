// ── the alternative renderings ────────────────────────────────────────────────────────────────
// A dropdown of the same graph drawn other ways (docs/2026-08-05-additive-graph-views.md). These
// are separate pages under /views/<slug>/, not board modes, so the menu holds plain links.
//
// On a mouse they open in a new tab: the board keeps its scroll position and whatever the reader
// had open. On a touchscreen they do NOT — a phone has no tab strip worth the name, and the back
// gesture is the only navigation the reader actually has, so a view opened in a new tab is a room
// with no door. Same tab means back returns to the board; each view carries a "← board" link for
// the same reason.
// `GRAPH.views` is set only by `lit serve`; a static build has no key, so the button never shows.
(() => {
  const wrap = document.getElementById("viewsWrap");
  const btn  = document.getElementById("viewsBtn");
  const menu = document.getElementById("viewsMenu");
  const views = Array.isArray(GRAPH.views) ? GRAPH.views : [];
  if (!wrap || !btn || !menu || !views.length) return;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  const tab = matchMedia("(hover:none) and (pointer:coarse)").matches ? "" : ` target="_blank" rel="noopener"`;
  menu.innerHTML = views.map(v =>
    `<a href="/views/${encodeURIComponent(v.slug)}/"${tab}>` +
    `${esc(v.label)}<span class="vn">${esc(v.note || "")}</span></a>`).join("");
  wrap.hidden = false;
  const open = on => { menu.hidden = !on; btn.classList.toggle("on", on); };
  btn.addEventListener("click", e => { e.stopPropagation(); open(menu.hidden); });
  menu.addEventListener("click", () => open(false));       // a chosen link closes the menu behind it
  addEventListener("click", e => { if (!wrap.contains(e.target)) open(false); });
  addEventListener("keydown", e => { if (e.key === "Escape" && !menu.hidden) open(false); });
})();

// read-only introspection for headless tests; not used by the UI
window.litDebug={get edges(){return edges},get cols(){return cols},open,drill,stacks,
  absOpen,sliceOpen,stubOpen,
  walk:WALK,
  get ctxOpen(){return ctxOpen},get ctxDrill(){return ctxDrill},get hover(){return hover},
  get pin(){return pin},anchorRect};
