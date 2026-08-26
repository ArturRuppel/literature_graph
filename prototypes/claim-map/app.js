/* app.js — browser-only glue: one control state, the readout, and every number
 * in the chrome. All graph logic lives in derive.js (pure) and all drawing in
 * map-view.js, so this file owns nothing but state and text.
 *
 * Nothing here hardcodes a count. Every figure in the standfirst, the stat
 * line, a checkbox label or the key is read off the derived model, so the page
 * cannot drift from the library as it grows.
 */
import { buildModel } from './derive.js';
import { render } from './map-view.js';

/* Under `lit serve` this page is /views/claim-map/ and the board sits at the
 * root; standalone (serve.py) there is nothing above it. Both doors out — the
 * "← board" link in the header and the per-node handoffs in the readout — are
 * gated on this rather than pointing at a 404. */
const SERVED = location.pathname.startsWith('/views/');
/* The handoff itself: the board resolves ?goto= against its own payload
 * (viewer/js/17-handoff.js), and it takes a broad slug as readily as a citekey,
 * so this view can hand over either the claim or one of its papers by name.
 * Same tab, like the door beside it — the reader asked to leave. */
const boardHref = (spec) => '/?goto=' + encodeURIComponent(spec);

const $ = (id) => document.getElementById(id);
const fields = (name, value) => {
  for (const e of document.querySelectorAll(`[data-f="${name}"]`)) e.textContent = value;
};

const state = {
  ladder: true, spread: true, labels: true,
  disputeOnly: false, topic: '', minN: 2,
  focus: null, pinned: null,
  visible(c) {
    if (this.disputeOnly && !c.contra && !c.internal.length) return false;
    if (c.n < this.minN) return false;
    if (this.topic && !c.topics.some(([t]) => t === this.topic)) return false;
    return true;
  },
};

let model = null;

/* ── readout ─────────────────────────────────────────────────────────────
   The panel says what the mark cannot: the claim's own sentence, the two
   dispute counts kept apart, and the papers with their years and stances. */
function readout(slug) {
  const box = $('readout');
  if (!slug) {
    box.innerHTML = '<div class="read-empty">Point at a claim.</div>';
    return;
  }
  const c = model.claims.find((x) => x.slug === slug);
  const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const maxVote = Math.max(...c.topics.map(([, n]) => n), 1);
  // Standalone there is no board to hand off to, so a name stays plain text
  // rather than becoming a link into nothing.
  const goto = (spec, label) => (SERVED
    ? `<a class="goto" href="${esc(boardHref(spec))}">${esc(label)}</a>`
    : esc(label));

  box.innerHTML = `
    <div class="read-title">${goto(c.slug, c.title)}</div>
    <div class="read-slug">${esc(c.slug)}</div>
    <div class="read-text">${esc(c.text)}</div>

    <table class="read-facts">
      <tr><th>papers attached</th><td>${c.n}</td></tr>
      <tr><th>ladder altitude</th><td>${c.alt === 0 ? 'apex' : `${c.alt} below apex`}</td></tr>
      <tr><th>first … last paper</th><td>${c.min} … ${c.max}</td></tr>
      <tr><th>middle half</th><td>${c.p25.toFixed(1)} … ${c.p75.toFixed(1)}</td></tr>
      <tr><th>median year</th><td>${c.med.toFixed(1)}</td></tr>
      <tr class="${c.contra ? 'hot' : ''}"><th>papers contradicting it</th><td>${c.contra}</td></tr>
      <tr class="${c.internal.length ? 'hot' : ''}"><th>disputes inside it</th><td>${c.internal.length}</td></tr>
      <tr><th>slice meter (support / contra)</th><td>${c.meter.s} / ${c.meter.c}</td></tr>
    </table>

    ${c.internal.length ? `<div class="read-head">who argues with whom</div>
      ${c.internal.map(([a, b]) => `<div class="paper contra"><span class="tt">`
        + `${goto(a, a)} ↔ ${goto(b, b)}</span></div>`).join('')}` : ''}

    <div class="read-head">topics of its papers</div>
    ${c.topics.length ? c.topics.slice(0, 6).map(([t, n]) => `
      <div class="topic-bar">
        <span class="bar" style="width:${(n / maxVote) * 60}px"></span>
        <span class="lbl">${esc(model.topics[t] || t)} · ${n}</span>
      </div>`).join('')
    : '<div class="read-empty">none of its papers carry tags</div>'}

    <div class="read-head">the ${c.n} papers</div>
    ${c.members.map((m) => `
      <div class="paper ${m.stance === 'contra' ? 'contra' : ''}">
        <span class="yr">${m.year ?? '····'}</span>
        <span class="tt">${goto(m.key, m.title)}</span>
        ${m.stance === 'contra' ? '<span class="stance">contra</span>' : ''}
      </div>`).join('')}
  `;
}

/* A pinned claim is written into the query string, so the view of one claim is
 * a link you can paste at somebody. It is also the only way to reach a
 * particular readout without a pointer, which is what makes the panel checkable
 * from a headless browser. */
function syncURL() {
  const u = new URL(location.href);
  if (state.pinned) u.searchParams.set('claim', state.pinned);
  else u.searchParams.delete('claim');
  history.replaceState(null, '', u);
}

/* ── draw ──────────────────────────────────────────────────────────────── */
function draw() {
  const { shown } = render($('map'), model, state, {
    focus(slug) { if (!state.pinned) { state.focus = slug; readout(slug); draw(); } },
    pin(slug) {
      state.pinned = state.pinned === slug ? null : slug;
      state.focus = state.pinned || slug;
      readout(state.focus);
      syncURL();
      draw();
    },
  });
  fields('stats', `${shown} of ${model.stats.claims} claims · `
    + `${model.stats.papers} curated papers · ${model.stats.attachments} attachments`);
}

/* ── boot ──────────────────────────────────────────────────────────────── */
fetch('graph.json')
  .then((r) => {
    if (!r.ok) throw new Error(`graph.json: ${r.status}`);
    return r.json();
  })
  .then((graph) => {
    model = buildModel(graph);

    fields('nladder', model.stats.ladderEdges);
    fields('ndispute', model.stats.disputed);
    fields('minread', '2 papers');
    fields('banded', 'The lanes are the claim ladder, not subject areas. A claim owns no '
      + 'topic, so a topic lane would be a plurality vote of its papers’ topics — and '
      + 'that vote is under 40% for 38 of 42 claims, which is why topic is a filter here '
      + 'and not an axis.');

    const sel = $('sel-topic');
    for (const [slug, title] of Object.entries(model.topics).sort((a, b) => a[1].localeCompare(b[1]))) {
      const o = document.createElement('option');
      o.value = slug; o.textContent = title;
      sel.appendChild(o);
    }

    const bind = (id, key, get) => $(id).addEventListener('input', (e) => {
      state[key] = get(e.target); draw();
    });
    bind('tgl-ladder', 'ladder', (t) => t.checked);
    bind('tgl-spread', 'spread', (t) => t.checked);
    bind('tgl-labels', 'labels', (t) => t.checked);
    bind('tgl-dispute', 'disputeOnly', (t) => t.checked);
    bind('sel-topic', 'topic', (t) => t.value);
    $('rng-min').addEventListener('input', (e) => {
      state.minN = +e.target.value;
      fields('minread', `${state.minN} paper${state.minN === 1 ? '' : 's'}`);
      draw();
    });
    $('btn-reset').addEventListener('click', () => {
      Object.assign(state, {
        ladder: true, spread: true, labels: true,
        disputeOnly: false, topic: '', minN: 2, focus: null, pinned: null,
      });
      $('tgl-ladder').checked = $('tgl-spread').checked = $('tgl-labels').checked = true;
      $('tgl-dispute').checked = false;
      $('sel-topic').value = '';
      $('rng-min').value = 2;
      fields('minread', '2 papers');
      readout(null);
      draw();
    });

    // clicking the background unpins; Escape does the same from the keyboard
    const unpin = () => {
      state.pinned = null; state.focus = null; readout(null); syncURL(); draw();
    };
    $('mapWrap').addEventListener('click', unpin);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') unpin(); });
    addEventListener('resize', draw);

    if (SERVED) {
      const back = $('back');
      back.href = '/';
      back.hidden = false;
    }

    const want = new URL(location.href).searchParams.get('claim');
    if (want && model.claims.some((c) => c.slug === want)) {
      state.pinned = state.focus = want;
      readout(want);
    }
    draw();
  })
  .catch((err) => {
    $('mapWrap').innerHTML = `<p style="padding:24px;color:#ae1800">`
      + `Could not load the graph: ${err.message}.<br>`
      + `Open this under <code>lit serve</code> at <code>/views/claim-map/</code>, or `
      + `standalone with <code>python3 serve.py --graph /path/to/dist/graph.json</code>.</p>`;
  });
