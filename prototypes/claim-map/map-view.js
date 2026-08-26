/* map-view.js — one renderer, the whole map. No state of its own.
 *
 *   render(svg, model, state, handlers) -> void
 *
 * The two axes, and why they are the two axes:
 *
 *   x  the median publication year of the papers attached to a claim, with the
 *      first-to-last span and the middle half drawn behind it. A single year
 *      for a claim is a summary, and drawing the spread it summarises is what
 *      stops it being read as a measurement. This is the "is the claim live or
 *      finished" axis.
 *
 *   y  the claim ladder — `leads_to` between broad claims, apex at the top.
 *      Authored, so no vote and no tie-break. The obvious alternative, a topic
 *      band, was measured and thrown out: a claim owns no topic, so its band
 *      would be a plurality of its members' topics, and that plurality is under
 *      40% for 38 of 42 claims. Topic is a filter here instead, which is a use
 *      that does not require picking a winner.
 *
 * Area, not radius, carries the paper count, so a claim with four times the
 * support looks four times the size rather than sixteen.
 *
 * Packing: marks are boxed with their labels and greedily dropped into rows
 * within their lane, left to right. A lane is as tall as the rows it needed, so
 * turning labels off genuinely compacts the map instead of leaving holes.
 */

import { quantile } from './derive.js';

const NS = 'http://www.w3.org/2000/svg';
const el = (name, attrs = {}) => {
  const n = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  return n;
};

const M = { top: 22, right: 26, bottom: 42, left: 132 };
const ROW = 36;                 // one packing row; the largest mark is ~34 tall
const LANE_PAD = 14;
// Labels sit to the right of their mark, always, and the x scale stops short of
// the frame by GUTTER so the rightmost mark still has room for one. Flipping
// long labels to the left was tried instead and packed badly: a left-hand label
// widens the mark's box backwards into the marks it was meant to sit beside,
// which pushed the map to one claim per row. Truncating to a fixed width and
// keeping one side is what lets a lane hold several claims per row; the full
// title is in the readout and in the mark's tooltip.
const GUTTER = 218;
const MAXLAB = 38;
const radius = (n) => 3.5 + 2.0 * Math.sqrt(n);
const trim = (s) => (s.length > MAXLAB ? s.slice(0, MAXLAB - 1).trimEnd() + '…' : s);
const labelWidth = (s) => trim(s).length * 5.3 + 6;

const LANE_NAME = ['apex', 'one below', 'two below', 'three below'];
const LANE_SUB = [
  'nothing generalizes these',
  'generalize into an apex',
  'two steps under an apex',
  'most specific rung',
];

export function render(svg, model, state, handlers) {
  const width = Math.max(720, svg.parentNode.clientWidth);
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const shown = model.claims.filter((c) => state.visible(c));

  // ---- x scale ---------------------------------------------------------
  // The left edge comes off the 5th percentile of the claims' first papers,
  // not off the minimum and not off the quartiles. The minimum would let one
  // 1978 paper squeeze every median into the right third; the quartiles were
  // tried and clamped twelve whiskers, which turns a truncation mark from a
  // flag into wallpaper. At the 5th percentile exactly one claim is cut, and
  // it is cut visibly.
  const mins = model.claims.map((c) => c.min).sort((a, b) => a - b);
  const lo = Math.floor(quantile(mins, 0.05)) - 1;
  const hi = Math.ceil(Math.max(...model.claims.map((c) => c.p75))) + 1;
  const plotW = width - M.left - M.right - GUTTER;
  const x = (yr) => M.left + ((Math.min(hi, Math.max(lo, yr)) - lo) / (hi - lo)) * plotW;
  const clamped = (yr) => yr < lo || yr > hi;

  // ---- pack each lane --------------------------------------------------
  const lanes = model.rungs.map((alt) => {
    const items = shown.filter((c) => c.alt === alt)
      .sort((a, b) => a.med - b.med || b.n - a.n);
    const rows = [];
    for (const c of items) {
      const r = radius(c.n);
      const lab = state.labels ? 4 + labelWidth(c.title) : 0;
      const left = x(c.med) - r;
      const right = x(c.med) + r + lab;
      let ri = rows.findIndex((row) => row.every((o) => left > o.right + 5 || right < o.left - 5));
      if (ri === -1) { rows.push([]); ri = rows.length - 1; }
      rows[ri].push({ c, r, left, right, row: ri });
    }
    return { alt, rows, items };
  });

  let cursor = M.top;
  const place = new Map();      // slug -> {cx, cy, r}
  for (const lane of lanes) {
    lane.top = cursor;
    lane.height = Math.max(ROW, lane.rows.length * ROW) + LANE_PAD * 2;
    for (const row of lane.rows) {
      for (const it of row) {
        place.set(it.c.slug, {
          cx: x(it.c.med),
          cy: lane.top + LANE_PAD + it.row * ROW + ROW / 2,
          r: it.r,
          label: it.c.title,
        });
      }
    }
    cursor += lane.height;
  }
  const height = cursor + M.bottom;
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);

  // ---- lanes and the year grid ----------------------------------------
  const gGrid = el('g');
  for (let yr = Math.ceil(lo); yr <= hi; yr++) {
    const major = yr % 5 === 0;
    if (!major && (hi - lo) > 24) continue;
    gGrid.appendChild(el('line', {
      x1: x(yr), x2: x(yr), y1: M.top - 6, y2: cursor,
      class: major ? 'grid-decade' : 'grid-year',
    }));
    if (major || (hi - lo) <= 26) {
      const t = el('text', { x: x(yr), y: cursor + 15, class: 'axis-txt', 'text-anchor': 'middle' });
      t.textContent = yr;
      gGrid.appendChild(t);
    }
  }
  const xt = el('text', { x: M.left, y: cursor + 32, class: 'axis-title' });
  xt.textContent = 'median year of the papers attached to the claim';
  gGrid.appendChild(xt);
  svg.appendChild(gGrid);

  const gLane = el('g');
  for (const lane of lanes) {
    gLane.appendChild(el('line', {
      x1: 0, x2: width - M.right, y1: lane.top, y2: lane.top, class: 'lane-sep',
    }));
    const nm = el('text', { x: 34, y: lane.top + 16, class: 'lane-name' });
    nm.textContent = LANE_NAME[lane.alt] ?? `rung ${lane.alt}`;
    gLane.appendChild(nm);
    const sub = el('text', { x: 34, y: lane.top + 30, class: 'lane-sub' });
    sub.textContent = LANE_SUB[lane.alt] || `${lane.items.length} claims`;
    gLane.appendChild(sub);
    const cnt = el('text', { x: 34, y: lane.top + 44, class: 'lane-sub' });
    cnt.textContent = `${lane.items.length} claim${lane.items.length === 1 ? '' : 's'}`;
    gLane.appendChild(cnt);
  }
  gLane.appendChild(el('line', {
    x1: 0, x2: width - M.right, y1: cursor, y2: cursor, class: 'lane-sep',
  }));
  const yt = el('text', {
    x: 0, y: 0, class: 'axis-title',
    transform: `translate(13 ${cursor - 6}) rotate(-90)`,
  });
  yt.textContent = 'ladder altitude — general above';
  gLane.appendChild(yt);
  svg.appendChild(gLane);

  // ---- the ladder ------------------------------------------------------
  // Drawn under the marks. Every edge points from a claim to something more
  // general, so on this y axis every edge runs upward; that is checked
  // numerically in verify.py rather than assumed here.
  const gLadder = el('g');
  if (state.ladder) {
    for (const c of shown) {
      const a = place.get(c.slug);
      for (const t of c.leads_to) {
        const b = place.get(t);
        if (!a || !b) continue;      // target filtered out; edge is simply absent
        const mid = (a.cy + b.cy) / 2;
        const on = state.focus === c.slug || state.focus === t;
        gLadder.appendChild(el('path', {
          d: `M ${a.cx} ${a.cy - a.r} C ${a.cx} ${mid}, ${b.cx} ${mid}, ${b.cx} ${b.cy + b.r}`,
          class: on ? 'ladder on' : 'ladder',
        }));
      }
    }
  }
  svg.appendChild(gLadder);

  // ---- the marks -------------------------------------------------------
  const gMarks = el('g');
  for (const c of shown) {
    const p = place.get(c.slug);
    const dim = state.focus && state.focus !== c.slug
      && !c.leads_to.includes(state.focus)
      && !model.claims.find((o) => o.slug === state.focus)?.leads_to.includes(c.slug);
    const g = el('g', {
      class: 'mark' + (dim ? ' dim' : '') + (state.focus === c.slug ? ' on' : ''),
      tabindex: 0, role: 'button',
      'aria-label': `${c.title}, ${c.n} papers, median year ${c.med.toFixed(0)}`,
    });

    if (state.spread) {
      g.appendChild(el('line', {
        x1: x(c.min), x2: x(c.max), y1: p.cy, y2: p.cy, class: 'whisk',
      }));
      // a span that runs off the left edge gets a tick, so a clamped whisker
      // is never read as the claim's real first paper
      if (clamped(c.min)) {
        g.appendChild(el('line', {
          x1: x(lo) + 1, x2: x(lo) + 1, y1: p.cy - 4, y2: p.cy + 4, class: 'whisk',
        }));
      }
      g.appendChild(el('line', {
        x1: x(c.p25), x2: x(c.p75), y1: p.cy, y2: p.cy, class: 'iqr',
      }));
    }

    const cls = ['dot'];
    if (c.contra) cls.push('contra');
    else if (c.internal.length) cls.push('internal');
    g.appendChild(el('circle', { cx: p.cx, cy: p.cy, r: p.r, class: cls.join(' ') }));

    if (state.labels) {
      const t = el('text', { x: p.cx + p.r + 4, y: p.cy + 3.6, class: 'label' });
      t.textContent = trim(c.title);
      g.appendChild(t);
    }
    // the untruncated title, for a pointer that rests on the mark
    const tip = el('title');
    tip.textContent = `${c.title} — ${c.n} papers, ${c.min}…${c.max}`;
    g.appendChild(tip);

    const enter = () => handlers.focus(c.slug);
    g.addEventListener('mouseenter', enter);
    g.addEventListener('focus', enter);
    g.addEventListener('click', (e) => { e.stopPropagation(); handlers.pin(c.slug); });
    g.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handlers.pin(c.slug); }
    });
    gMarks.appendChild(g);
  }
  svg.appendChild(gMarks);

  return { shown: shown.length, height };
}
