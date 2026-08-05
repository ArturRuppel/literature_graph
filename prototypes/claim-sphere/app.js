/* Claim sphere — app.js. Browser-only glue: one control state, the branch
 * strip, the colour key, the selection readout, and every number in the chrome.
 *
 * All graph logic lives in derive-model.js (pure), all drawing in sphere-view.js
 * (one renderer, three layouts) and all colour in colour.js (pure). This file
 * owns nothing but state and text.
 * Spec: docs/2026-08-05-additive-graph-views.md §3.1–§3.3.
 *
 * The panel is single by design. Rendering and colour are two settings over one
 * view, so a claim you selected, a branch you isolated and a peel you set all
 * survive switching between the readings — which is the whole reason to be able
 * to switch at all.
 *
 * Nothing here hardcodes a count. Every figure in a standfirst, a stat line, a
 * checkbox label or a plate table is read off the derived model, so the page
 * cannot drift from the library as it grows.
 */
import './sphere-view.js';
import { BOARD, STATUS_KEYS, STATUS_LABEL, ramp, MUTED } from './colour.js';

const $ = (id) => document.getElementById(id);
const fields = (name, value) => {
  for (const el of document.querySelectorAll(`[data-f="${name}"]`)) el.textContent = value;
};

/* the six edge kinds, in the order the control column lists them */
const EDGE_KINDS = ['up', 'cons', 'ladder', 'gen', 'cite', 'lat'];

let MODEL = null, FAMS = [];

const state = {
  layout: 'sphere',
  colour: 'status',
  min: 0, max: 100,
  explode: 45,
  iso: null,
  halo: true,
  edges: new Set(EDGE_KINDS),
};

const view = $('v');

/* ── the three readings, in words ─────────────────────────────────────────
   Held here rather than in the markup because each one is a function of the
   model: the sentence and the number it quotes are written together, so they
   cannot fall out of step. */
const COPY = {
  sphere: {
    kicker: 'Reading one · what the library establishes',
    title: 'The ball and the haze',
    lede: m => `Radius is generality — floors on the surface, the ${m.stats.families} top-level ` +
      `entries at the centre. Direction is family. ${m.nodes.length - m.stats.halo} nodes have both ` +
      `coordinates; ${m.stats.halo} slices have neither and sit in the haze outside the sphere. ` +
      `Nothing out there was placed by a vote or a similarity — it is diffuse because the library ` +
      `does not say where it goes.`,
    help: 'Drag to orbit · wheel to fly in toward the apexes · click a mark to read it. ' +
      'Position within a shell is packing, not meaning.',
    halo: m => `show the haze (${m.stats.halo})`,
  },
  sectors: {
    kicker: 'Reading two · where the mass sits',
    title: 'The branches, pulled apart',
    lede: m => {
      const familied = m.stats.famAuthored + m.stats.famInherited;
      const big = m.families.reduce((a, f) => (f.members > a.members ? f : a), m.families[0]);
      const small = m.families.filter(f => f.members < 20).length;
      return `Same coordinates, families exploded along their own axis so a solid angle becomes a ` +
        `limb. ${big.members} of the ${familied} familied slices hang off one branch — ` +
        `${big.title.toLowerCase()}. ${small} branches hold fewer than twenty. ` +
        `${m.families.filter(f => f.kind === 'broad method').length} of the ${m.families.length} are ` +
        `broad methods, and a method branch counts instruments, not conclusions.`;
    },
    help: 'Drag to orbit · wheel to fly down a limb · click a branch in the strip to isolate it. ' +
      'The haze has no family by construction, so it belongs to no limb — turn it off to read this one.',
    halo: m => `show the haze (${m.stats.halo})`,
  },
  shells: {
    kicker: 'Reading three · the ladder, unrolled',
    title: 'The stack and the slab',
    lede: m => {
      const nP = (m.stats.maxSlice + 1) + (m.stats.maxTier + 1);
      const on = m.nodes.filter(n => n.lvl != null).length;
      return `The same radius, cut into plates and stacked: distance-to-floor becomes height, so ` +
        `the ladder can be read edge-on. ${nP} plates carry ${on} nodes; the ${m.stats.unfloored} ` +
        `claims with no rank at all stand beside them as a slab, in red. A claim whose chain never ` +
        `reaches a measurement is not on the floor — it is off the building.`;
    },
    help: 'Height is authored: distance to a measurement floor for a slice, ladder tier for a broad ' +
      'node. Position on a plate is packing — the ring only groups a claim with its family, and a ' +
      'claim with no authored family sits at the plate’s centre.',
    halo: m => `show the slab (${m.stats.unfloored})`,
  },
};

const COLOUR_NOTE = {
  status: 'The board’s own emergent colours (SCHEMA §7). A claim that is green on its card is ' +
    'green here — this view invents no palette.',
  family: 'One hue per top-level entry, golden-angle spaced exactly as the axes are, so neighbours ' +
    'on the ladder are far apart in colour. The strip under the view is the key.',
  generality: 'Distance to a measurement floor: ochre on the floor, indigo at the top-level entries. ' +
    'The same quantity the radius already draws — here as a second channel.',
  ink: 'Monochrome. Shape alone carries kind, which is how the view was first drawn.',
};

/* ── one sync: state → attributes → redraw ───────────────────────────────── */

const edgeAttr = (set) => [...set].join(',') || 'none';

function sync() {
  view.setAttribute('layout', state.layout);
  view.setAttribute('colour', state.colour);
  view.setAttribute('shell-min', state.min);
  view.setAttribute('shell-max', state.max);
  view.setAttribute('explode', String(state.explode / 100));
  view.setAttribute('edges', edgeAttr(state.edges));
  view.setAttribute('halo', state.halo ? '1' : '0');
  if (state.iso == null) view.removeAttribute('isolate');
  else view.setAttribute('isolate', String(state.iso));

  /* controls that only mean something in some renderings */
  for (const el of document.querySelectorAll('[data-when]')) {
    el.hidden = !el.dataset.when.split(' ').includes(state.layout);
  }
  for (const btn of $('layout').querySelectorAll('.seg-btn')) {
    btn.setAttribute('aria-pressed', String(btn.dataset.v === state.layout));
  }
  for (const btn of $('colour').querySelectorAll('.seg-btn')) {
    btn.setAttribute('aria-pressed', String(btn.dataset.v === state.colour));
  }
  for (const btn of document.querySelectorAll('#branches .branch')) {
    btn.setAttribute('aria-pressed', String(+btn.dataset.i === state.iso));
  }
  fields('shell', `r ∈ [${(state.min / 100 * 1.7).toFixed(2)}, ${(state.max / 100 * 1.7).toFixed(2)}]`);
  fields('colourNote', COLOUR_NOTE[state.colour]);

  if (!MODEL) return;
  const c = COPY[state.layout];
  fields('kicker', c.kicker);
  fields('title', c.title);
  fields('lede', c.lede(MODEL));
  fields('help', c.help);
  fields('haloLabel', c.halo(MODEL));
  buildKey();
  const f = state.iso == null ? null : MODEL.families[state.iso];
  fields('isoLine', f
    ? `${f.title} — ${f.members} slices ladder into this branch. Isolated: every other branch is ` +
      'hidden, including the haze.'
    : `All ${MODEL.families.length} branches shown.`);
}

/* ── controls ─────────────────────────────────────────────────────────────── */

$('layout').addEventListener('click', e => {
  const btn = e.target.closest('.seg-btn'); if (!btn) return;
  state.layout = btn.dataset.v; sync();
});
$('colour').addEventListener('click', e => {
  const btn = e.target.closest('.seg-btn'); if (!btn) return;
  state.colour = btn.dataset.v; sync();
});
$('s-min').addEventListener('input', e => {
  state.min = Math.min(+e.target.value, state.max); e.target.value = state.min; sync();
});
$('s-max').addEventListener('input', e => {
  state.max = Math.max(+e.target.value, state.min); e.target.value = state.max; sync();
});
$('explode').addEventListener('input', e => { state.explode = +e.target.value; sync(); });
$('halo').addEventListener('change', e => { state.halo = e.target.checked; sync(); });
$('all').addEventListener('click', () => { state.iso = null; sync(); });
$('reset').addEventListener('click', () => view.resetView());
for (const box of $('edges').querySelectorAll('input[data-edge]')) {
  box.addEventListener('change', () => {
    box.checked ? state.edges.add(box.dataset.edge) : state.edges.delete(box.dataset.edge);
    sync();
  });
}

/* ── selection readout ────────────────────────────────────────────────────── */

const EMPTY = {
  Kind: 'Nothing selected',
  Text: 'Click a mark to read the claim it stands for. Everything here is a quote-welded assertion ' +
    'from a paper you curated, or a broad node you authored.',
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
  const v = selVals((e.detail || {}).node);
  for (const [k, text] of Object.entries(v)) fields('sel' + k, text);
});

/* ── the chrome ───────────────────────────────────────────────────────────── */

/* The colour key is a function of the mode, so it can never explain a palette
   the view is not drawing. `family` has no key here — the branch strip is it. */
function buildKey() {
  const host = $('key');
  host.textContent = '';
  host.hidden = false;
  if (state.colour === 'status') {
    for (const k of STATUS_KEYS) {
      const sw = document.createElement('span');
      sw.className = 'ksw'; sw.style.background = BOARD[k];
      const lab = document.createElement('span');
      lab.textContent = STATUS_LABEL[k];
      host.append(sw, lab);
    }
    const sw = document.createElement('span');
    sw.className = 'ksw'; sw.style.background = BOARD.broad;
    const lab = document.createElement('span');
    lab.textContent = 'broad node';
    host.append(sw, lab);
  } else if (state.colour === 'generality') {
    const bar = document.createElement('span');
    bar.className = 'kramp';
    /* built from the same ramp() the marks use, sampled — not a CSS gradient
       written by hand, which would be a second palette to keep in step */
    const stops = Array.from({ length: 9 }, (_, i) => ramp(i / 8) + ' ' + (i / 8 * 100) + '%');
    bar.style.background = `linear-gradient(90deg, ${stops.join(', ')})`;
    const lab = document.createElement('span');
    lab.className = 'kramp-lab';
    lab.innerHTML = '<span>floors</span><span>top level</span>';
    host.append(bar, lab);
  } else {
    host.hidden = true;
  }
  host.className = state.colour === 'generality' ? 'key key-ramp' : 'key';
}

function buildBranches(m) {
  const host = $('branches');
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
      '<span class="branch-kind"></span><span class="branch-bar"><i></i></span>';
    btn.querySelector('.branch-title').textContent = f.title;
    btn.querySelector('.branch-count').textContent = f.members;
    btn.querySelector('.branch-kind').textContent = f.kind;
    const bar = btn.querySelector('.branch-bar i');
    bar.style.width = Math.max(3, f.members / most * 100) + '%';
    /* the family's own hue, in every colour mode — it is the branch's identity,
       and in `family` mode this strip is literally the legend */
    bar.style.background = FAMS[i] || MUTED;
    btn.addEventListener('click', () => {
      state.iso = state.iso === i ? null : i;
      sync();
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
  const host = $('plates');
  host.textContent = '';
  for (const [label, n, slab] of rows) {
    const a = document.createElement('span');
    const b = document.createElement('b');
    a.textContent = label; b.textContent = n;
    if (slab) { a.className = 'slab'; b.className = 'slab'; }
    host.append(a, b);
  }
}

function fillChrome(m) {
  const s = m.stats;
  const totalEdges = Object.values(s.edges).reduce((a, b) => a + b, 0);
  fields('stats', `${s.slices} slices · ${s.broad} broad · ${s.papers} papers · ${totalEdges} authored edges`);
  for (const k of EDGE_KINDS) fields('e' + k[0].toUpperCase() + k.slice(1), s.edges[k] || 0);
  buildPlates(m);
  buildBranches(m);
  for (const k of Object.keys(EMPTY)) fields('sel' + k, EMPTY[k]);
}

/* the renderer announces the model once it has parsed graph.json */
document.addEventListener('sv-model', e => {
  if (MODEL) return;
  MODEL = e.detail.model;
  FAMS = e.detail.fams;
  fillChrome(MODEL);
  sync();
});

/* Under `lit serve` this page is /views/claim-sphere/ and the board is at the
   root; standalone (serve.py) there is nothing above it, so no dead link. */
if (location.pathname.startsWith('/views/')) {
  const back = $('back');
  back.href = '/';
  back.hidden = false;
}

sync();
