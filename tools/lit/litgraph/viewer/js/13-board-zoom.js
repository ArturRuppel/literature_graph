// ── board zoom: the camera ───────────────────────────────────────────────────────────────
// The width slider above changes the LAYOUT — how wide a card sets its text. This changes only
// how far away you stand from it. They are next to each other in the HUD and deliberately
// different shapes (slider vs stepper) because they answer different questions: "how should this
// be laid out" and "how much of it do I want on screen".
// Zoomed out, the board stops being readable and becomes a MAP — which column fans where, how
// far an arrow reaches, whether the ladder you just hoisted actually gathered anything. That is
// a question the reader has at 40%, and one the 500px-wide-column view could never answer on a
// paper with 58 cards.
// It is its own zoom, sharing nothing with the PDF viewer's (see wireZoom): two surfaces the
// reader looks at side by side, each with its own distance, each remembered separately.
const BOARD_ZOOM = (function(){
  // 1/3 … 3 rather than 0.3 … 3: a geometrically symmetric range puts 100% exactly mid-track on
  // the log slider, so "back to normal" is a place the hand can find without reading the number.
  const MIN = 1 / 3, MAX = 3, STEP = 1.2, KEY = "lit.board.zoom";
  const ctl = document.getElementById("bzoom");
  const val = ctl && ctl.querySelector(".zval");
  const slider = ctl && ctl.querySelector("input");
  let z = 1;
  const clamp = v => Math.max(MIN, Math.min(MAX, v));
  const paint = () => {
    if (!ctl) return;
    val.textContent = Math.round(z * 100) + "%";
    slider.value = String(zoomSlider.toTrack(z, MIN, MAX));
  };
  // (cx,cy) is the point on the glass, relative to the board's own box, to keep fixed — the
  // pointer for a wheel-zoom, the middle of the port for the slider and the keys. Everything else
  // follows from "the stage coordinate under that point must not move".
  function set(z1, cx, cy){
    z1 = clamp(z1);
    const r = board.getBoundingClientRect();
    if (cx == null) { cx = r.width / 2; cy = r.height / 2; }
    const z0 = z, ax = board.scrollLeft + cx, ay = board.scrollTop + cy;
    z = z1;
    document.documentElement.style.setProperty("--bz", String(z));
    hudQuiet = performance.now() + 250;          // the scroll below is the zoom's, not the reader's
    board.scrollLeft = ax / z0 * z - cx;         // the browser clamps if the extent shrank
    board.scrollTop  = ay / z0 * z - cy;
    paint();
    try { localStorage.setItem(KEY, String(z)); } catch {}
    redraw();                                    // the overlay's viewport cover is BZ-dependent
  }
  // Restored, not reset, on load: the distance you were standing at is part of where you were.
  try { const v = parseFloat(localStorage.getItem(KEY)); if (v > 0) z = clamp(v); } catch {}
  document.documentElement.style.setProperty("--bz", String(z));
  paint();
  if (z !== 1) redraw();                         // the columns were laid out before this ran
  // Dragging the track zooms about the middle of the port — the board you can see stays the board
  // you can see, which is what makes sweeping for a distance work at all.
  if (ctl) {
    slider.addEventListener("input", () => set(zoomSlider.toZoom(+slider.value, MIN, MAX)));
    val.addEventListener("click", () => set(1));
  }
  // ctrl/⌘-wheel (and trackpad pinch) over the board, exactly as over a PDF page — same gesture,
  // and which one it lands on is simply which one you are pointing at.
  board.addEventListener("wheel", e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const r = board.getBoundingClientRect();
    set(z * Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  return {set, get z(){ return z; }, in(){ set(z * STEP); }, out(){ set(z / STEP); }, reset(){ set(1); }};
})();

// + / − / 0 zoom whichever surface you are pointing at. The PDF only ever claims the keys while
// the pointer is over it — or in a PDF-only window, where there is no board to mean instead.
// Bare keys, not ctrl-+: the browser's own page zoom stays available and unshadowed, and it is
// still the right tool when what you want is bigger chrome rather than a wider view.
addEventListener("keydown", e => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (!/^[+\-=_0]$/.test(e.key)) return;
  // Typing beats zooming — but a range input is not typing, and after dragging a zoom slider the
  // slider is what has focus, which was quietly eating the very keys that do the same job.
  const el = e.target, tag = el.tagName || "";
  if (el.isContentEditable || tag === "TEXTAREA" || (tag === "INPUT" && el.type !== "range")) return;
  const pw = document.querySelector(".pw");
  const pdf = pw && pw._zoom &&
              (document.body.classList.contains("detached") || pw.matches(":hover")) ? pw._zoom : null;
  const t = pdf || BOARD_ZOOM;
  if (!pdf && (document.body.classList.contains("library") || document.body.classList.contains("walk"))) return;
  e.preventDefault();
  if (e.key === "0") t.reset(); else if (e.key === "-" || e.key === "_") t.out(); else t.in();
});

