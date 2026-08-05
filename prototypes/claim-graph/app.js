/* Claim graph — support-skeleton diagnostic (View B, additive-graph-views.md §3).
 *
 * Slice-centric: nodes are the 822 slices + 45 broad nodes. Papers demote to
 * an attribute (hover / side panel text), never a node. Layout is layered
 * left->right by distance-to-floor, NOT a force layout — the DAG's depth
 * axis is the point. Colour is read straight off graph.json's own emergent
 * fields (color/is_floor/grounded/borrowed/answered) — nothing here re-derives
 * "is this grounded", per the design doc's explicit instruction.
 *
 * Consumes exactly one file: /graph.json, proxied by serve.py from whatever
 * --graph path it was started with. No other coupling.
 */
(function () {
  'use strict';

  // ---- palette, read once, reused everywhere ---------------------------
  // Values match dist/index.html's own CSS custom properties (--floor,
  // --model, --grounded, --borrowed, --question, --cross) so an accent hue
  // means the same thing here as it already does on the board.
  const COLOR = {
    floor: '#b5822f',
    model: '#8a6db1',
    grounded: '#27735f',
    borrowed: '#286b9f',
    question: '#a15c1e',
    plausible: '#8a97a4',
  };
  const BROAD_COLOR = { 'broad claim': '#7a4fb0', 'broad method': '#8a6db1', 'broad question': '#a15c1e' };
  const CROSS = '#9a3b3b';
  const CORR = '#27735f';
  const LINE = '#c3cbd2';

  const SEP = '::';
  const sliceKey = (paper, id) => paper + SEP + id;
  const broadKey = (slug) => 'b' + SEP + slug;

  const svgNS = 'http://www.w3.org/2000/svg';
  const $ = (id) => document.getElementById(id);

  let MODEL = null, RANKS = null, LAYOUT = null;
  let selectedKey = null;
  let scale = 1;

  fetch('graph.json')
    .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then((data) => {
      MODEL = buildModel(data);
      RANKS = computeRanks(MODEL);
      LAYOUT = layout(MODEL, RANKS);
      renderLegend();
      render();
      wireControls();
      reportStats();
    })
    .catch((err) => {
      $('stats').textContent = 'failed to load graph.json — ' + err.message;
      console.error(err);
    });

  // =======================================================================
  // 1. MODEL — every node and edge, straight off the authored fields.
  //    CONCEPT.md §4: leads-to is one edge doing four jobs (grounding,
  //    derivation, generalization, citation), always ground -> derived.
  //    §9: corroborate/contradict are lateral, never part of the walk.
  // =======================================================================
  function buildModel(data) {
    const slices = new Map();
    const broad = new Map();
    const edges = { up: [], gen: [], cons: [], ladder: [], cite: [], lateral: [] };
    const floors = new Set();

    for (const [pkey, paper] of Object.entries(data.papers)) {
      const idsInPaper = new Set(paper.slices.map((s) => s.id));
      for (const s of paper.slices) {
        const key = sliceKey(pkey, s.id);
        slices.set(key, {
          key, paper: pkey, paperTitle: paper.title, paperYear: paper.year, paperType: paper.type,
          id: s.id, kind: s.kind, text: s.text, quote: s.quote, color: s.color,
          is_floor: s.is_floor, grounded: s.grounded, borrowed: s.borrowed,
          answered: s.answered, answers: s.answers || [],
        });
        if (s.is_floor) floors.add(key);
      }
      for (const s of paper.slices) {
        const key = sliceKey(pkey, s.id);
        for (const u of (s.up || [])) {
          if (idsInPaper.has(u)) edges.up.push({ from: sliceKey(pkey, u), to: key });
        }
        for (const g of (s.gen || [])) {
          if (idsInPaper.has(g)) edges.gen.push({ from: key, to: sliceKey(pkey, g) });
        }
      }
      for (const c of (paper.cons || [])) {
        if (idsInPaper.has(c.via) && data.broad[c.slug]) {
          edges.cons.push({ from: sliceKey(pkey, c.via), to: broadKey(c.slug) });
        }
      }
      for (const g of (paper.grounds || [])) {
        // Only the SHARPENED refs (tid set) resolve to a real slice on the
        // other end — a wildcard (tid null) points at a paper container,
        // and papers aren't nodes here, so it can't be drawn. §3 is explicit
        // about this: "grounds with tid set -> the sharpened ... edges."
        if (g.tid && idsInPaper.has(g.via) && data.papers[g.key]) {
          const srcIds = new Set(data.papers[g.key].slices.map((s) => s.id));
          if (srcIds.has(g.tid)) {
            edges.cite.push({ from: sliceKey(g.key, g.tid), to: sliceKey(pkey, g.via), srcPaper: g.key });
          }
        }
      }
      for (const l of (paper.lateral || [])) {
        if (!idsInPaper.has(l.via)) continue;
        const from = sliceKey(pkey, l.via);
        if (l.tid && data.papers[l.key]) {
          const srcIds = new Set(data.papers[l.key].slices.map((s) => s.id));
          if (srcIds.has(l.tid)) edges.lateral.push({ a: from, b: sliceKey(l.key, l.tid), sign: l.sign });
        } else if (l.slug && data.broad[l.slug]) {
          edges.lateral.push({ a: from, b: broadKey(l.slug), sign: l.sign });
        }
        // else: wildcard onto an un-sliced paper container — no node to draw to.
      }
    }

    for (const [slug, b] of Object.entries(data.broad)) {
      const key = broadKey(slug);
      broad.set(key, { key, slug, kind: b.kind, title: b.title, text: b.text, meter: b.meter });
    }
    for (const [slug, b] of Object.entries(data.broad)) {
      for (const t of (b.leads_to || [])) {
        if (data.broad[t]) edges.ladder.push({ from: broadKey(slug), to: broadKey(t) });
      }
    }

    return { slices, broad, edges, floors, raw: data };
  }

  // =======================================================================
  // 2. RANK = distance-to-floor. Multi-source BFS from every floor, walking
  //    forward along the DAG edges (up/gen/cons/ladder/cite) — lateral is
  //    deliberately excluded, CONCEPT §9: "never part of the walk". A node
  //    the BFS never reaches has NO rank from below: that absence is the
  //    view's diagnostic, so it is never quietly folded into rank 0.
  // =======================================================================
  function computeRanks(model) {
    const adj = new Map();
    const add = (a, b) => { if (!adj.has(a)) adj.set(a, []); adj.get(a).push(b); };
    for (const e of model.edges.up) add(e.from, e.to);
    for (const e of model.edges.gen) add(e.from, e.to);
    for (const e of model.edges.cons) add(e.from, e.to);
    for (const e of model.edges.ladder) add(e.from, e.to);
    for (const e of model.edges.cite) add(e.from, e.to);

    const rank = new Map();
    const q = [];
    for (const f of model.floors) { rank.set(f, 0); q.push(f); }
    let head = 0;
    while (head < q.length) {
      const u = q[head++];
      for (const v of (adj.get(u) || [])) {
        if (!rank.has(v)) { rank.set(v, rank.get(u) + 1); q.push(v); }
      }
    }

    // Local depth *within the unfloored set only* — its own induced sub-DAG
    // (any node it points at via up/gen/cite is, by construction, unfloored
    // too, else the BFS above would have reached it). Keeps the "stranded"
    // band from being an undifferentiated pile: derivation among ungrounded
    // claims still reads left-to-right.
    const unfSlices = [...model.slices.keys()].filter((k) => !rank.has(k));
    const unfSet = new Set(unfSlices);
    const localAdj = new Map();
    const indeg = new Map(unfSlices.map((k) => [k, 0]));
    const addLocal = (a, b) => {
      if (!unfSet.has(a) || !unfSet.has(b)) return;
      if (!localAdj.has(a)) localAdj.set(a, []);
      localAdj.get(a).push(b);
      indeg.set(b, (indeg.get(b) || 0) + 1);
    };
    for (const e of model.edges.up) addLocal(e.from, e.to);
    for (const e of model.edges.gen) addLocal(e.from, e.to);
    for (const e of model.edges.cite) addLocal(e.from, e.to);

    const localDepth = new Map();
    const q2 = unfSlices.filter((k) => (indeg.get(k) || 0) === 0);
    for (const k of q2) localDepth.set(k, 0);
    for (let i = 0; i < q2.length; i++) {
      const u = q2[i];
      for (const v of (localAdj.get(u) || [])) {
        const d = localDepth.get(u) + 1;
        if (!localDepth.has(v) || localDepth.get(v) < d) {
          localDepth.set(v, d);
          q2.push(v);
        }
      }
    }
    for (const k of unfSlices) if (!localDepth.has(k)) localDepth.set(k, 0);

    // Broad tier — longest path from broad "roots" along broad.leads_to
    // only. A purely structural read of the 4-tier ladder, independent of
    // floor-reachability; used only to sub-order the broad band.
    const bAdj = new Map();
    const bIndeg = new Map([...model.broad.keys()].map((k) => [k, 0]));
    for (const e of model.edges.ladder) {
      if (!bAdj.has(e.from)) bAdj.set(e.from, []);
      bAdj.get(e.from).push(e.to);
      bIndeg.set(e.to, (bIndeg.get(e.to) || 0) + 1);
    }
    const broadTier = new Map();
    const q3 = [...model.broad.keys()].filter((k) => (bIndeg.get(k) || 0) === 0);
    for (const k of q3) broadTier.set(k, 0);
    for (let i = 0; i < q3.length; i++) {
      const u = q3[i];
      for (const v of (bAdj.get(u) || [])) {
        const d = broadTier.get(u) + 1;
        if (!broadTier.has(v) || broadTier.get(v) < d) {
          broadTier.set(v, d);
          q3.push(v);
        }
      }
    }
    for (const k of model.broad.keys()) if (!broadTier.has(k)) broadTier.set(k, 0);

    return { rank, localDepth, broadTier, unfSet };
  }

  // =======================================================================
  // 3. LAYOUT — columns left->right: floor (rank 0) .. rank K, then a gap,
  //    the stranded band (unfloored slices, sub-ordered by local depth),
  //    then a gap, then the broad band (sub-ordered by broad tier). Floors
  //    pin left, broad nodes pin right, exactly as the doc asks — and the
  //    stranded band is its own reserved space, not a value that can
  //    collide with a genuinely-floored column.
  // =======================================================================
  const RANK_PITCH = 170;
  const GAP = 90;
  const STRAND_PITCH = 42;
  const BROAD_PITCH = 60;
  const ROW_H = 15;
  const BROAD_ROW_H = 42;
  const PAD = 40;

  function layout(model, ranks) {
    const sliceRanks = [...ranks.rank.entries()].filter(([k]) => model.slices.has(k));
    const maxSliceRank = sliceRanks.reduce((m, [, r]) => Math.max(m, r), 0);
    const maxLocalDepth = [...ranks.localDepth.values()].reduce((m, d) => Math.max(m, d), 0);
    const maxBroadTier = [...ranks.broadTier.values()].reduce((m, t) => Math.max(m, t), 0);

    const strandStart = (maxSliceRank + 1) * RANK_PITCH + GAP;
    const broadStart = strandStart + (maxLocalDepth + 1) * STRAND_PITCH + GAP;

    const colX = (key) => {
      if (model.slices.has(key)) {
        if (ranks.rank.has(key)) return ranks.rank.get(key) * RANK_PITCH;
        return strandStart + ranks.localDepth.get(key) * STRAND_PITCH;
      }
      return broadStart + ranks.broadTier.get(key) * BROAD_PITCH;
    };
    const colKey = (key) => {
      if (model.slices.has(key)) {
        if (ranks.rank.has(key)) return 'r' + ranks.rank.get(key);
        return 'u' + ranks.localDepth.get(key);
      }
      return 'b' + ranks.broadTier.get(key);
    };

    const groups = new Map();
    for (const key of model.slices.keys()) {
      const ck = colKey(key);
      if (!groups.has(ck)) groups.set(ck, []);
      groups.get(ck).push(key);
    }
    for (const key of model.broad.keys()) {
      const ck = colKey(key);
      if (!groups.has(ck)) groups.set(ck, []);
      groups.get(ck).push(key);
    }

    const pos = new Map();
    for (const [ck, keys] of groups) {
      const isBroad = ck[0] === 'b';
      keys.sort((a, b) => {
        if (isBroad) {
          const ba = model.broad.get(a), bb = model.broad.get(b);
          return ba.kind.localeCompare(bb.kind) || ba.title.localeCompare(bb.title);
        }
        const sa = model.slices.get(a), sb = model.slices.get(b);
        return sa.paper.localeCompare(sb.paper) || sa.id.localeCompare(sb.id);
      });
      const rowH = isBroad ? BROAD_ROW_H : ROW_H;
      const x = colX(keys[0]);
      keys.forEach((key, i) => {
        pos.set(key, { x: PAD + x, y: PAD + i * rowH, col: ck });
      });
    }

    const maxY = Math.max(0, ...[...pos.values()].map((p) => p.y)) + 60;
    const maxX = PAD + broadStart + (maxBroadTier + 1) * BROAD_PITCH + 140;
    return { pos, width: maxX, height: maxY, maxSliceRank, maxLocalDepth, maxBroadTier, strandStart, broadStart };
  }

  // =======================================================================
  // 4. RENDER
  // =======================================================================
  function render() {
    const svg = $('graph');
    svg.innerHTML = '';
    svg.setAttribute('viewBox', `0 0 ${LAYOUT.width} ${LAYOUT.height}`);
    svg.setAttribute('width', LAYOUT.width * scale);
    svg.setAttribute('height', LAYOUT.height * scale);

    // band separators + labels, purely decorative
    const bandsG = document.createElementNS(svgNS, 'g');
    addBandLabel(bandsG, 0, 'floors (rank 0)');
    addBandLabel(bandsG, LAYOUT.strandStart, 'unfloored — no path to a floor');
    addBandLabel(bandsG, LAYOUT.broadStart, 'broad nodes (45)');
    svg.appendChild(bandsG);
    const sepLine = (x) => {
      const l = document.createElementNS(svgNS, 'line');
      l.setAttribute('x1', PAD + x - GAP / 2); l.setAttribute('x2', PAD + x - GAP / 2);
      l.setAttribute('y1', 0); l.setAttribute('y2', LAYOUT.height);
      l.setAttribute('stroke', '#dfe4e8'); l.setAttribute('stroke-dasharray', '2,4');
      bandsG.appendChild(l);
    };
    sepLine(LAYOUT.strandStart);
    sepLine(LAYOUT.broadStart);

    const edgeG = document.createElementNS(svgNS, 'g');
    edgeG.setAttribute('id', 'edgeLayer');
    svg.appendChild(edgeG);

    const drawStraight = (e, cls, color) => {
      const p1 = LAYOUT.pos.get(e.from), p2 = LAYOUT.pos.get(e.to);
      if (!p1 || !p2) return;
      const line = document.createElementNS(svgNS, 'line');
      line.setAttribute('x1', p1.x); line.setAttribute('y1', p1.y);
      line.setAttribute('x2', p2.x); line.setAttribute('y2', p2.y);
      line.setAttribute('class', 'edge ' + cls);
      line.setAttribute('stroke', color);
      line.setAttribute('stroke-opacity', '0.5');
      line.dataset.from = e.from; line.dataset.to = e.to;
      edgeG.appendChild(line);
    };
    for (const e of MODEL.edges.up) drawStraight(e, 'edge-up', LINE);
    for (const e of MODEL.edges.gen) drawStraight(e, 'edge-gen', LINE);
    for (const e of MODEL.edges.cons) drawStraight(e, 'edge-cons', '#b6a4d6');
    for (const e of MODEL.edges.ladder) drawStraight(e, 'edge-ladder', BROAD_COLOR['broad claim']);
    for (const e of MODEL.edges.cite) drawStraight(e, 'edge-cite', COLOR.borrowed);

    for (const e of MODEL.edges.lateral) {
      const p1 = LAYOUT.pos.get(e.a), p2 = LAYOUT.pos.get(e.b);
      if (!p1 || !p2) continue;
      const midx = (p1.x + p2.x) / 2, midy = (p1.y + p2.y) / 2 - 22;
      const path = document.createElementNS(svgNS, 'path');
      path.setAttribute('d', `M ${p1.x} ${p1.y} Q ${midx} ${midy} ${p2.x} ${p2.y}`);
      path.setAttribute('class', 'edge edge-lateral');
      path.setAttribute('stroke', e.sign === 'contra' ? CROSS : CORR);
      path.setAttribute('stroke-dasharray', '3,3');
      path.setAttribute('stroke-opacity', '0.7');
      path.dataset.from = e.a; path.dataset.to = e.b;
      edgeG.appendChild(path);
    }

    const nodeG = document.createElementNS(svgNS, 'g');
    nodeG.setAttribute('id', 'nodeLayer');
    svg.appendChild(nodeG);

    for (const [key, s] of MODEL.slices) {
      const p = LAYOUT.pos.get(key);
      if (!p) continue;
      const unfloored = !RANKS.rank.has(key);
      const fill = COLOR[s.color] || '#999';
      const g = document.createElementNS(svgNS, 'g');
      g.setAttribute('class', 'node-slice');
      g.setAttribute('transform', `translate(${p.x},${p.y})`);
      g.dataset.key = key;

      let shape;
      if (s.kind === 'claim') {
        shape = document.createElementNS(svgNS, 'circle');
        shape.setAttribute('r', 4.2);
      } else if (s.kind === 'method') {
        shape = document.createElementNS(svgNS, 'rect');
        shape.setAttribute('x', -4.2); shape.setAttribute('y', -4.2);
        shape.setAttribute('width', 8.4); shape.setAttribute('height', 8.4);
        shape.setAttribute('transform', 'rotate(45)');
      } else {
        shape = document.createElementNS(svgNS, 'polygon');
        shape.setAttribute('points', '0,-5.2 5,4.4 -5,4.4');
      }
      shape.setAttribute('fill', s.kind === 'question' && !s.answered ? 'white' : fill);
      shape.setAttribute('stroke', unfloored ? CROSS : fill);
      shape.setAttribute('stroke-width', unfloored ? 1.4 : 1);
      if (unfloored) shape.setAttribute('stroke-dasharray', '1.6,1.4');
      if (s.kind === 'question') shape.setAttribute('stroke', s.answered ? fill : fill);
      g.appendChild(shape);
      nodeG.appendChild(g);
    }

    for (const [key, b] of MODEL.broad) {
      const p = LAYOUT.pos.get(key);
      if (!p) continue;
      const unfloored = !RANKS.rank.has(key);
      const fill = BROAD_COLOR[b.kind] || COLOR.plausible;
      const g = document.createElementNS(svgNS, 'g');
      g.setAttribute('class', 'node-broad');
      g.setAttribute('transform', `translate(${p.x - 44},${p.y - 12})`);
      g.dataset.key = key;

      const rect = document.createElementNS(svgNS, 'rect');
      rect.setAttribute('width', 88); rect.setAttribute('height', 24);
      rect.setAttribute('rx', 6);
      rect.setAttribute('fill', fill); rect.setAttribute('fill-opacity', '0.16');
      rect.setAttribute('stroke', fill);
      rect.setAttribute('stroke-width', unfloored ? 1.6 : 1.1);
      if (unfloored) rect.setAttribute('stroke-dasharray', '3,2.4');
      g.appendChild(rect);

      const txt = document.createElementNS(svgNS, 'text');
      txt.setAttribute('x', 5); txt.setAttribute('y', 14);
      txt.setAttribute('font-size', '7.4');
      txt.setAttribute('fill', '#27313a');
      txt.textContent = truncate(b.title, 20);
      g.appendChild(txt);

      if (b.meter && (b.meter.s || b.meter.c)) {
        const m = document.createElementNS(svgNS, 'text');
        m.setAttribute('x', 5); m.setAttribute('y', 21.5);
        m.setAttribute('font-size', '6.4');
        m.setAttribute('fill', '#6a7884');
        m.textContent = `+${b.meter.s} / -${b.meter.c}`;
        g.appendChild(m);
      }
      nodeG.appendChild(g);
    }

    wireInteractions();
    applyEdgeToggles();
  }

  function addBandLabel(g, x, label) {
    const t = document.createElementNS(svgNS, 'text');
    t.setAttribute('x', PAD + x); t.setAttribute('y', 16);
    t.setAttribute('font-size', '10'); t.setAttribute('fill', '#8a97a4');
    t.setAttribute('font-weight', '600');
    t.textContent = label;
    g.appendChild(t);
  }

  function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + '…' : s; }

  // =======================================================================
  // 5. INTERACTION — hover tooltip, click to walk-highlight + side panel,
  //    edge-group toggles, zoom/pan.
  // =======================================================================
  function wireInteractions() {
    const svg = $('graph');
    const tooltip = $('tooltip');

    svg.addEventListener('mousemove', (e) => {
      const g = e.target.closest('.node-slice,.node-broad');
      if (!g) { tooltip.style.display = 'none'; return; }
      const key = g.dataset.key;
      tooltip.innerHTML = tooltipHTML(key);
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 16) + 'px';
      tooltip.style.top = (e.clientY + 12) + 'px';
    });
    svg.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });

    svg.addEventListener('click', (e) => {
      const g = e.target.closest('.node-slice,.node-broad');
      if (!g) { clearSelection(); return; }
      selectKey(g.dataset.key);
    });

    $('panel-close').addEventListener('click', clearSelection);
  }

  function tooltipHTML(key) {
    if (MODEL.slices.has(key)) {
      const s = MODEL.slices.get(key);
      const unfloored = !RANKS.rank.has(key);
      let flag = '';
      if (unfloored) flag = `<span class="tt-flag" style="color:${CROSS}">⚠ no floor reached</span>`;
      let extra = '';
      if (s.answers.length) extra += `<div class="tt-meta">answers: ${s.answers.join(', ')}</div>`;
      return `<div class="tt-kind">${s.kind} · ${s.color}${s.is_floor ? ' · FLOOR' : ''}</div>
        ${flag}
        <div class="tt-text">${escapeHTML(s.text)}</div>
        ${s.quote ? `<div class="tt-quote">“${escapeHTML(truncate(s.quote, 160))}”</div>` : ''}
        <div class="tt-meta">${escapeHTML(s.paperTitle)} (${s.paperYear})<br>${escapeHTML(s.paper)} · ${s.id}</div>
        ${extra}`;
    }
    const b = MODEL.broad.get(key);
    const unfloored = !RANKS.rank.has(key);
    const flag = unfloored ? `<span class="tt-flag" style="color:${CROSS}">⚠ no floor reached</span>` : '';
    return `<div class="tt-kind">${b.kind}</div>
      ${flag}
      <div class="tt-text">${escapeHTML(b.title)}</div>
      <div class="tt-quote">${escapeHTML(truncate(b.text, 200))}</div>
      <div class="tt-meta">corroborate ${b.meter.s} · contradict ${b.meter.c} · slug: ${b.slug}</div>`;
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  // Ancestor + descendant walk along the DAG edges only (never lateral),
  // exactly the CONCEPT §9 "walk to root" — reused here for highlighting.
  function walkNeighbors(key) {
    const inAdj = new Map(), outAdj = new Map();
    const addPair = (a, b) => {
      if (!outAdj.has(a)) outAdj.set(a, []);
      outAdj.get(a).push(b);
      if (!inAdj.has(b)) inAdj.set(b, []);
      inAdj.get(b).push(a);
    };
    for (const grp of [MODEL.edges.up, MODEL.edges.gen, MODEL.edges.cons, MODEL.edges.ladder, MODEL.edges.cite]) {
      for (const e of grp) addPair(e.from, e.to);
    }
    const visited = new Set([key]);
    const stack = [key];
    while (stack.length) {
      const u = stack.pop();
      for (const v of (inAdj.get(u) || [])) if (!visited.has(v)) { visited.add(v); stack.push(v); }
    }
    const stack2 = [key];
    while (stack2.length) {
      const u = stack2.pop();
      for (const v of (outAdj.get(u) || [])) if (!visited.has(v)) { visited.add(v); stack2.push(v); }
    }
    return visited;
  }

  function selectKey(key) {
    selectedKey = key;
    const keep = walkNeighbors(key);
    document.querySelectorAll('.node-slice,.node-broad').forEach((g) => {
      g.classList.toggle('dim', !keep.has(g.dataset.key));
    });
    document.querySelectorAll('.edge').forEach((el) => {
      const on = keep.has(el.dataset.from) && keep.has(el.dataset.to);
      el.classList.toggle('dim', !on);
    });
    openPanel(key);
  }

  function clearSelection() {
    selectedKey = null;
    document.querySelectorAll('.dim').forEach((el) => el.classList.remove('dim'));
    $('panel').classList.remove('open');
  }

  function openPanel(key) {
    const body = $('panel-body');
    if (MODEL.slices.has(key)) {
      const s = MODEL.slices.get(key);
      const unfloored = !RANKS.rank.has(key);
      body.innerHTML = `
        <div class="p-kind">${s.kind} · ${s.color}${s.is_floor ? ' · FLOOR' : ''}</div>
        <h2>${escapeHTML(s.text)}</h2>
        ${unfloored ? `<div class="p-row" style="color:${CROSS};font-weight:700">⚠ no path to a floor — this claim's chain dangles in reasoning or an un-sharpened citation.</div>` : ''}
        ${s.quote ? `<div class="p-quote">“${escapeHTML(s.quote)}”</div>` : ''}
        <div class="p-row"><b>paper</b> ${escapeHTML(s.paperTitle)} (${s.paperYear})</div>
        <div class="p-row"><b>citekey</b> <code>${escapeHTML(s.paper)}</code></div>
        <div class="p-row"><b>slice</b> <code>${s.id}</code></div>
        <div class="p-row"><b>rank</b> ${RANKS.rank.has(key) ? RANKS.rank.get(key) : 'unfloored (local depth ' + RANKS.localDepth.get(key) + ')'}</div>
        ${s.answers.length ? `<div class="p-row"><b>answers</b> ${s.answers.join(', ')} (local)</div>` : ''}
      `;
    } else {
      const b = MODEL.broad.get(key);
      const unfloored = !RANKS.rank.has(key);
      body.innerHTML = `
        <div class="p-kind">${b.kind}</div>
        <h2>${escapeHTML(b.title)}</h2>
        ${unfloored ? `<div class="p-row" style="color:${CROSS};font-weight:700">⚠ no path to a floor — nothing feeding this broad node currently grounds out.</div>` : ''}
        <div class="p-quote">${escapeHTML(b.text)}</div>
        <div class="p-row"><b>evidence meter</b> corroborate ${b.meter.s} · contradict ${b.meter.c}</div>
        <div class="p-row"><b>slug</b> <code>${b.slug}</code></div>
        <div class="p-row"><b>rank</b> ${RANKS.rank.has(key) ? RANKS.rank.get(key) : 'unfloored'}</div>
      `;
    }
    $('panel').classList.add('open');
  }

  function applyEdgeToggles() {
    const map = { 'tgl-up': 'edge-up', 'tgl-gen': 'edge-gen', 'tgl-cons': 'edge-cons', 'tgl-ladder': 'edge-ladder', 'tgl-cite': 'edge-cite', 'tgl-lateral': 'edge-lateral' };
    for (const [id, cls] of Object.entries(map)) {
      const on = $(id).checked;
      document.querySelectorAll('.' + cls).forEach((el) => { el.style.display = on ? '' : 'none'; });
    }
  }

  function wireControls() {
    ['tgl-up', 'tgl-gen', 'tgl-cons', 'tgl-ladder', 'tgl-cite', 'tgl-lateral'].forEach((id) => {
      $(id).addEventListener('change', applyEdgeToggles);
    });
    $('btn-reset').addEventListener('click', () => { clearSelection(); fitToView(); });

    $('zoom-in').addEventListener('click', () => setScale(scale * 1.25));
    $('zoom-out').addEventListener('click', () => setScale(scale / 1.25));
    $('zoom-fit').addEventListener('click', fitToView);

    // drag-to-pan
    const wrap = $('canvasWrap');
    let dragging = false, sx = 0, sy = 0, sl = 0, st = 0;
    wrap.addEventListener('mousedown', (e) => {
      if (e.target.closest('.node-slice,.node-broad')) return;
      dragging = true; wrap.classList.add('panning');
      sx = e.clientX; sy = e.clientY; sl = wrap.scrollLeft; st = wrap.scrollTop;
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      wrap.scrollLeft = sl - (e.clientX - sx);
      wrap.scrollTop = st - (e.clientY - sy);
    });
    window.addEventListener('mouseup', () => { dragging = false; wrap.classList.remove('panning'); });

    fitToView();
  }

  function setScale(s) {
    scale = Math.max(0.15, Math.min(3, s));
    const svg = $('graph');
    svg.setAttribute('width', LAYOUT.width * scale);
    svg.setAttribute('height', LAYOUT.height * scale);
  }

  function fitToView() {
    const wrap = $('canvasWrap');
    const fitScale = Math.min(wrap.clientWidth / LAYOUT.width, wrap.clientHeight / LAYOUT.height, 1);
    setScale(fitScale > 0 ? fitScale : 1);
  }

  // =======================================================================
  // 6. LEGEND + STATS
  // =======================================================================
  function renderLegend() {
    const el = $('legend');
    el.innerHTML = `
      <div class="grp"><b>slice fill</b>
        <span class="sw"><i class="dot" style="background:${COLOR.floor}"></i>floor</span>
        <span class="sw"><i class="dot" style="background:${COLOR.model}"></i>model</span>
        <span class="sw"><i class="dot" style="background:${COLOR.grounded}"></i>grounded</span>
        <span class="sw"><i class="dot" style="background:${COLOR.borrowed}"></i>borrowed</span>
        <span class="sw"><i class="dot" style="background:${COLOR.plausible}"></i>plausible</span>
        <span class="sw"><i class="dot" style="background:${COLOR.question}"></i>question</span>
      </div>
      <div class="grp"><b>shape</b>
        <span class="sw"><i class="dot" style="background:#888"></i>claim</span>
        <span class="sw"><i class="diamond" style="background:#888"></i>method</span>
        <span class="sw"><i class="tri" style="border-bottom-color:#888"></i>question (filled = answered)</span>
        <span class="sw"><i class="rect" style="background:#7a4fb0"></i>broad node</span>
      </div>
      <div class="grp"><b>edges</b>
        <span class="sw"><i class="ln" style="border-color:${LINE}"></i>leads-to (walk)</span>
        <span class="sw"><i class="ln dashed" style="border-color:${CORR}"></i>corroborate</span>
        <span class="sw"><i class="ln dashed" style="border-color:${CROSS}"></i>contradict (lateral, not walked)</span>
      </div>
      <div class="grp">
        <span class="sw"><i class="dot hatched" style="background:${CROSS}"></i>dashed outline = no floor reached</span>
      </div>
    `;
  }

  function reportStats() {
    const claims = [...MODEL.slices.values()].filter((s) => s.kind === 'claim');
    const unfClaims = claims.filter((s) => !RANKS.rank.has(s.key));
    const broadTotal = MODEL.broad.size;
    const unfBroad = [...MODEL.broad.keys()].filter((k) => !RANKS.rank.has(k)).length;

    $('stats').innerHTML =
      `<b>${MODEL.slices.size}</b> slices · <b>${broadTotal}</b> broad · ` +
      `<span class="warn">${unfClaims.length}/${claims.length} claims never reach a floor</span> · ` +
      `<span class="warn">${unfBroad}/${broadTotal} broad unfloored</span>`;

    console.log('[claim-graph] slices', MODEL.slices.size, 'broad', MODEL.broad.size);
    console.log('[claim-graph] unfloored claims', unfClaims.length, '/', claims.length);
    console.log('[claim-graph] unfloored broad', unfBroad, '/', broadTotal);
  }

  window.addEventListener('resize', () => { if (LAYOUT) fitToView(); });
})();
