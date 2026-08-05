/* Claim sphere — app.js. Browser-only glue: control state, the branch list,
 * the selection readouts, and every number in the chrome.
 *
 * All graph logic lives in derive-model.js (pure) and all drawing in
 * sphere-view.js (one renderer, three layouts). This file owns nothing but
 * state and text. Spec: docs/2026-08-05-additive-graph-views.md §3.1.
 *
 * Nothing here hardcodes a count. Every figure in a standfirst, a stat line, a
 * checkbox label or a plate table is read off the derived model, so the page
 * cannot drift from the library as it grows.
 */
import './sphere-view.js';

const $ = (id) => document.getElementById(id);
const fields = (name, value) => {
  for (const el of document.querySelectorAll(`[data-f="${name}"]`)) el.textContent = value;
};

/* the six edge kinds, in the order the control column lists them */
const EDGE_KINDS = ['up', 'cons', 'ladder', 'gen', 'cite', 'lat'];

let MODEL = null;

const state = {
  a: { min: 0, max: 100, halo: true, edges: new Set(EDGE_KINDS) },
  b: { explode: 45, iso: null, halo: false },
  c: { halo: true, edges: new Set(['up', 'cons', 'ladder']) },
};

const view = { a: $('v-a'), b: $('v-b'), c: $('v-c') };

const kindTally = (families) => {
  const by = families.reduce((a, f) => (a[f.kind] = (a[f.kind] || 0) + 1, a), {});
  const plural = { 'broad claim': 'broad claims', 'broad question': 'broad questions', 'broad method': 'broad methods' };
  return Object.entries(by).map(([k, n]) => `${n} ${plural[k] || k}`).join(', ');
};

/* ── controls ─────────────────────────────────────────────────────────────
   Each handler writes one attribute; the renderer redraws on its own. */

const edgeAttr = (set) => [...set].join(',') || 'none';

function syncA() {
  const s = state.a;
  view.a.setAttribute('shell-min', s.min);
  view.a.setAttribute('shell-max', s.max);
  view.a.setAttribute('edges', edgeAttr(s.edges));
  view.a.setAttribute('halo', s.halo ? '1' : '0');
  fields('aShell', `r ∈ [${(s.min / 100 * 1.7).toFixed(2)}, ${(s.max / 100 * 1.7).toFixed(2)}]`);
}
$('a-min').addEventListener('input', e => {
  state.a.min = Math.min(+e.target.value, state.a.max);
  e.target.value = state.a.min;
  syncA();
});
$('a-max').addEventListener('input', e => {
  state.a.max = Math.max(+e.target.value, state.a.min);
  e.target.value = state.a.max;
  syncA();
});
$('a-halo').addEventListener('change', e => { state.a.halo = e.target.checked; syncA(); });
$('a-reset').addEventListener('click', () => view.a.resetView());
for (const box of $('a-edges').querySelectorAll('input[data-edge]')) {
  box.addEventListener('change', () => {
    box.checked ? state.a.edges.add(box.dataset.edge) : state.a.edges.delete(box.dataset.edge);
    syncA();
  });
}

function syncB() {
  const s = state.b;
  view.b.setAttribute('explode', String(s.explode / 100));
  view.b.setAttribute('halo', s.halo ? '1' : '0');
  if (s.iso == null) view.b.removeAttribute('isolate');
  else view.b.setAttribute('isolate', String(s.iso));
  for (const btn of document.querySelectorAll('#b-branches .branch')) {
    btn.setAttribute('aria-pressed', String(+btn.dataset.i === s.iso));
  }
  if (!MODEL) return;
  const f = s.iso == null ? null : MODEL.families[s.iso];
  fields('bIsoLine', f
    ? `${f.title} — ${f.members} slices ladder into this branch. Isolated: every other family is hidden, including the haze.`
    : `All ${MODEL.families.length} branches shown. ${kindTally(MODEL.families)}.`);
}
$('b-explode').addEventListener('input', e => { state.b.explode = +e.target.value; syncB(); });
$('b-halo').addEventListener('change', e => { state.b.halo = e.target.checked; syncB(); });
$('b-all').addEventListener('click', () => { state.b.iso = null; syncB(); });
$('b-reset').addEventListener('click', () => view.b.resetView());

function syncC() {
  const s = state.c;
  view.c.setAttribute('edges', edgeAttr(s.edges));
  view.c.setAttribute('halo', s.halo ? '1' : '0');
}
$('c-halo').addEventListener('change', e => { state.c.halo = e.target.checked; syncC(); });
$('c-reset').addEventListener('click', () => view.c.resetView());
for (const box of $('c-edges').querySelectorAll('input[data-edge]')) {
  box.addEventListener('change', () => {
    box.checked ? state.c.edges.add(box.dataset.edge) : state.c.edges.delete(box.dataset.edge);
    syncC();
  });
}

/* ── selection readouts ───────────────────────────────────────────────────
   One handler for both views that carry a readout; the event names its view. */

const EMPTY = {
  Kind: 'Nothing selected',
  Text: 'Click a mark to read the claim it stands for. Everything here is a quote-welded assertion from a paper you curated, or a broad node you authored.',
  Quote: '', Coord: '', Fam: '', Paper: '', Key: '',
};

function selVals(n) {
  if (!n) return { ...EMPTY };
  const fam = (n.fam || []).map(i => MODEL.families[i] && MODEL.families[i].title).filter(Boolean).join(' · ');
  return {
    Kind: n.t === 'b'
      ? n.kind
      : n.kind + (n.floor ? ' · floor' : n.grounded ? ' · grounded' : ' · plausible') + (n.borrowed ? ' · borrowed' : ''),
    Text: n.t === 'b' ? n.title + ' — ' + n.text : n.text,
    Quote: n.quote ? '“' + n.quote + '”' : '',
    Coord: n.halo
      ? 'no authored coordinate — in the haze'
      : (n.t === 'b' ? 'broad, ladder tier ' + n.lvl : 'distance to floor: ' + n.lvl) + ' · r = ' + n.r,
    Fam: fam ? 'family: ' + fam + (n.famSrc === 'inherited' ? ' (inherited)' : ' (authored)') : 'family: none authored',
    Paper: n.t === 'b' ? 'authored broad node' : (n.a1 || '') + ' ' + (n.year || '') + ' · pass ' + n.pass,
    Key: n.t === 'b' ? n.slug : n.k,
  };
}

document.addEventListener('sv-select', e => {
  const { view: id, node } = e.detail || {};
  if (id !== 'a' && id !== 'c') return;
  const v = selVals(node);
  for (const [k, text] of Object.entries(v)) fields(id + 'Sel' + k, text);
});

/* ── the chrome's numbers, once the model lands ───────────────────────────── */

function buildBranches(m) {
  const host = $('b-branches');
  host.textContent = '';
  /* the ladder's own order, never sorted by size, so the claim/method
     asymmetry stays visible */
  const most = Math.max(...m.families.map(f => f.members), 1);
  m.families.forEach((f, i) => {
    const btn = document.createElement('button');
    btn.className = 'branch';
    btn.dataset.i = i;
    btn.setAttribute('aria-pressed', 'false');
    btn.innerHTML =
      '<span class="branch-row"><span class="branch-title"></span><span class="branch-count"></span></span>' +
      '<span class="branch-kind"></span><span class="branch-bar"></span>';
    btn.querySelector('.branch-title').textContent = f.title;
    btn.querySelector('.branch-count').textContent = f.members;
    btn.querySelector('.branch-kind').textContent = f.kind;
    btn.querySelector('.branch-bar').style.width = Math.max(2, f.members / most * 100) + '%';
    btn.addEventListener('click', () => {
      state.b.iso = state.b.iso === i ? null : i;
      syncB();
    });
    host.appendChild(btn);
  });
}

/* the plate table, bottom up — and the total that sits on the stack */
function buildPlates(m) {
  const nS = m.stats.maxSlice;
  const rankSlices = m.nodes.filter(n => n.t === 's' && n.lvl != null && n.lvl > 0).length;
  const midBroad = m.nodes.filter(n => n.t === 'b' && n.lvl > 0).length;
  const top = m.nodes.filter(n => n.t === 'b' && n.lvl === 0).length;
  const rows = [
    ['floors', m.stats.floors, false],
    [`ranks 1–${nS} · slices`, rankSlices, false],
    [`broad tiers ${m.stats.maxTier}–1`, midBroad, false],
    ['top level', top, false],
    ['the slab · no rank', m.stats.unfloored, true],
  ];
  const host = $('c-plates');
  host.textContent = '';
  for (const [label, n, slab] of rows) {
    const a = document.createElement('span');
    const b = document.createElement('b');
    a.textContent = label; b.textContent = n;
    if (slab) { a.className = 'slab'; b.className = 'slab'; }
    host.append(a, b);
  }
  return m.stats.floors + rankSlices + midBroad + top;
}

function fillChrome(m) {
  const s = m.stats;
  const totalEdges = Object.values(s.edges).reduce((a, b) => a + b, 0);
  const familied = s.famAuthored + s.famInherited;
  const placed = m.nodes.length - s.halo;
  const biggest = m.families.reduce((a, f) => (f.members > a.members ? f : a), m.families[0]);
  const small = m.families.filter(f => f.members < 20).length;
  const nPlates = (s.maxSlice + 1) + (s.maxTier + 1);

  /* 1a — splits on both coordinates */
  fields('aStats', `${s.slices} slices · ${s.broad} broad · ${s.papers} papers · ${totalEdges} authored edges`);
  fields('aFamCount', s.families === 16 ? 'sixteen' : String(s.families));
  fields('aLede', `${placed} nodes have both coordinates. ${s.halo} slices have neither and sit in the haze outside the sphere.`);
  fields('aHaloN', s.halo);
  for (const k of EDGE_KINDS) fields('e' + k[0].toUpperCase() + k.slice(1), s.edges[k] || 0);

  /* 1b */
  fields('bStats', `${familied} slices carry a family · ${s.famAuthored} authored, ${s.famInherited} inherited`);
  fields('bLede', `${biggest.members} of the ${familied} familied slices hang off one branch — ${biggest.title.toLowerCase()}.`);
  fields('bSmall', `${small} branches hold fewer than twenty.`);
  fields('bFoot',
    `${m.families.filter(f => f.kind === 'broad method').length} of the ${m.families.length} are broad methods. ` +
    'A method branch counts instruments, not conclusions — the asymmetry between the two kinds is the ' +
    'second thing this view shows.');

  /* 1c — splits on rank alone, because height is the only axis it draws */
  const onPlates = buildPlates(m);
  fields('cStats', `${s.floors} floors · ${s.ranked} ranked slices · ${s.maxSlice} slice ranks · ${s.maxTier + 1} broad tiers`);
  fields('cLede', `${nPlates} plates carry ${onPlates} nodes; the ${s.unfloored} claims with no rank at all stand beside them as a slab, in red.`);

  buildBranches(m);
  for (const k of Object.keys(EMPTY)) { fields('aSel' + k, EMPTY[k]); fields('cSel' + k, EMPTY[k]); }
}

/* the renderer announces the model once, from whichever view loaded first */
document.addEventListener('sv-model', e => {
  if (MODEL) return;
  MODEL = e.detail.model;
  fillChrome(MODEL);
  syncA(); syncB(); syncC();
});

syncA();
