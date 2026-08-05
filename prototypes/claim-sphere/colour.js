/* colour.js — the four colour readings of a node, and nothing else.
 *
 * Pure: no DOM, no I/O, no dependencies. Shared by sphere-view.js (the marks)
 * and app.js (the legend and the family strip), so a swatch in the chrome and
 * the dot it explains cannot disagree.
 *
 *   colourOf(mode, node, fams) -> css colour
 *   familyColours(n)           -> n hexes, one per top-level family
 *
 * Two rules govern everything here:
 *
 * 1. **The status palette is not ours.** `grounded` / `borrowed` / `plausible` /
 *    `question` / `floor` / `model` are the emergent colours the board already
 *    computes (`graph._slice_color`, SCHEMA §7) and already draws. A claim that
 *    is green on the board is green here. The hexes below are copied from
 *    `viewer/template.html`'s `:root` and must track it — that file's comment
 *    calls the variable names load-bearing, and this is the second reader.
 *
 * 2. **Red still means one thing.** A node with no authored coordinate is drawn
 *    in the accent in *every* mode, because that is the finding the view exists
 *    to show. Colour is a second channel over the placed nodes; it never
 *    reaches the haze.
 */

export const INK = '#201e1d';
export const RED = '#ec3013';
export const MUTED = '#8f8a89';

/* verbatim from viewer/template.html :root — see rule 1 above */
export const BOARD = {
  floor: '#b5822f', model: '#8a6db1', grounded: '#27735f', borrowed: '#286b9f',
  question: '#a15c1e', broad: '#7a4fb0', cross: '#9a3b3b', plausible: '#8a97a4',
};

export const STATUS_KEYS = ['floor', 'grounded', 'plausible', 'borrowed', 'question', 'model'];
export const STATUS_LABEL = {
  floor: 'measurement floor', grounded: 'grounded claim', plausible: 'plausible claim',
  borrowed: 'borrowed claim', question: 'question', model: 'method · model',
};

/* ── OKLCH → sRGB ───────────────────────────────────────────────────────────
   Hand-rolled rather than handed to the browser's `oklch()`: this file has to
   give the same hex to a canvas fill, a CSS background and Node under the
   headless check, and a colour that silently fails to parse in one of the
   three leaves the previous fillStyle standing — a bug that looks like a
   drawing bug. Out-of-gamut clips per channel, which is why the constants
   below stay conservative. */
export function oklch(L, C, Hdeg) {
  const h = Hdeg * Math.PI / 180;
  const a = C * Math.cos(h), b = C * Math.sin(h);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
  const lin = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
  ];
  return '#' + lin.map(v => {
    const c = v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(Math.max(v, 0), 1 / 2.4) - 0.055;
    return Math.round(Math.min(1, Math.max(0, c)) * 255).toString(16).padStart(2, '0');
  }).join('');
}

/* One hue per top-level family, golden-angle-spaced — the same trick that
   distributes the family *axes* over the sphere, applied to the hue circle, so
   consecutive ladder entries are as far apart in colour as they are in space.
   Constant OKLCH lightness and chroma: no family reads as louder than another,
   which matters because the ordering here is the ladder's, not importance. */
export function familyColours(n) {
  return Array.from({ length: n }, (_, i) => oklch(0.56, 0.125, (i * 137.508) % 360));
}

/* generality ramp: floors (r≈1) → the top-level entries (r≈0.13), ochre to
   indigo through green. Ordered, single sweep, never a rainbow. */
export function ramp(t) {
  const u = Math.min(1, Math.max(0, t));
  return oklch(0.70 - 0.24 * u, 0.10 + 0.04 * u, 84 + 190 * u);
}

const RMIN = 0.13;   /* derive-model.js rule 1 — the apex radius */

/**
 * `mode` is one of status | family | generality | ink.
 * `fams` is the familyColours() array; only `family` mode reads it.
 * A node whose kind or family the mode cannot resolve falls back to muted ink
 * rather than to a neighbouring meaning.
 */
export function colourOf(mode, n, fams) {
  if (n.halo) return RED;                       // rule 2
  if (mode === 'ink') return INK;
  /* A broad node is violet in every mode but `family` — where it is the thing
     the families are made of, so it takes its own branch's hue instead. */
  if (mode === 'family') return (n.fam && n.fam.length) ? fams[n.fam[0]] : MUTED;
  if (n.t === 'b') return BOARD.broad;
  if (mode === 'status') return BOARD[n.color] || MUTED;
  if (mode === 'generality') return n.r == null ? MUTED : ramp((1 - n.r) / (1 - RMIN));
  return INK;
}
