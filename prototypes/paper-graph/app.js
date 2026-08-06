// paper-graph — View A prototype (docs/2026-08-05-additive-graph-views.md §2)
//
// Every edge here is a PROJECTION computed from graph.json's authored edge
// lists (`grounds`, `cons`, `lateral`) — the data model has no bare
// paper→paper edge (CONCEPT §10.4). Nothing is inferred beyond simple
// collapsing/de-duping of those authored lists; the underlying quotes and
// slices remain the source of truth.
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const NODE_MIN_R = 5;
const NODE_MAX_R = 30;

/* Under `lit serve` this page is /views/<slug>/ and the board sits at the root; standalone
   (serve.py on 8001) there is nothing above it. Both ways back — the door in the header and
   the per-paper handoff in the pin panel — are gated on this rather than pointing at a 404. */
const SERVED = location.pathname.startsWith("/views/");
/* The handoff itself: the board resolves ?goto= against its own payload (viewer/js/17-handoff),
   so a citekey is the whole message. Same tab, like the ← board door beside it — the reader
   asked to leave, and on a phone a new tab is a room with no way out. */
const boardHref = (spec) => "/?goto=" + encodeURIComponent(spec);

// ---------------------------------------------------------------------
// State
// ---------------------------------------------------------------------
const state = {
  graph: null,        // raw graph.json
  papers: null,        // { key: paper }
  stubs: null,          // { key: stub }
  mode: "A1",           // "A1" | "A2"
  threshold: 2,          // in-degree (A1) or weight (A2)
  lateralOn: false,
  projections: null,       // computed once on load: { a1: {...}, a2: {...} }
  lateralPairs: null,       // computed once on load
  nodes: new Map(),          // id -> simulation node (persists across filter changes)
  pinned: null,                // id of pinned node, or null
  hovered: null,
  svg: null,
  viewport: null,                // <g> that carries pan/zoom transform
  pan: { x: 0, y: 0, k: 1 },
  simTimer: null,
  alpha: 1,
};

// ---------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------
async function main() {
  setStatus("loading graph.json…");
  const res = await fetch("graph.json");
  if (!res.ok) {
    setStatus("failed to load graph.json: " + res.status);
    return;
  }
  state.graph = await res.json();
  state.papers = state.graph.papers;
  state.stubs = state.graph.stubs;

  state.projections = {
    a1: buildA1(state.papers),
    a2: buildA2(state.papers),
  };
  state.lateralPairs = buildLateralPairs(state.papers);

  initSvg();
  buildLegendPies();
  wireControls();
  applyModeDefaults();
  rebuildAndRestart();

  setStatus(
    `${Object.keys(state.papers).length} curated papers · ` +
    `${Object.keys(state.stubs).length} stubs · ` +
    `A1: ${state.projections.a1.targets.size} targets / ` +
    `${state.projections.a1.edges.length} edges · ` +
    `A2: ${state.projections.a2.edges.length} pairs`
  );
}

// ---------------------------------------------------------------------
// A1 — grounding projection: paper -(grounds)-> target, de-duped per pair.
// Directed. Node in-degree is the quantity the threshold slider filters on.
// ---------------------------------------------------------------------
function buildA1(papers) {
  const pairSet = new Set(); // "source|target"
  const edges = [];
  for (const [pkey, p] of Object.entries(papers)) {
    for (const e of p.grounds || []) {
      const key = `${pkey}|${e.key}`;
      if (pairSet.has(key)) continue;
      pairSet.add(key);
      edges.push({ source: pkey, target: e.key });
    }
  }
  const indeg = new Map();
  const outdeg = new Map();
  for (const e of edges) {
    indeg.set(e.target, (indeg.get(e.target) || 0) + 1);
    outdeg.set(e.source, (outdeg.get(e.source) || 0) + 1);
  }
  const targets = new Set(edges.map((e) => e.target));
  let maxIndeg = 0;
  for (const v of indeg.values()) maxIndeg = Math.max(maxIndeg, v);
  return { edges, indeg, outdeg, targets, maxIndeg };
}

// ---------------------------------------------------------------------
// A2 — co-support projection: two papers link when slices in each
// `leads_to` (cons) the same broad node. Undirected, weighted by number
// of broad nodes shared. Derived entirely from `cons`.
// ---------------------------------------------------------------------
function buildA2(papers) {
  const paperToBroads = new Map(); // pkey -> Set(slug)
  for (const [pkey, p] of Object.entries(papers)) {
    const slugs = new Set((p.cons || []).map((e) => e.slug));
    if (slugs.size > 0) paperToBroads.set(pkey, slugs);
  }
  const broadToPapers = new Map(); // slug -> Set(pkey)
  for (const [pkey, slugs] of paperToBroads) {
    for (const s of slugs) {
      if (!broadToPapers.has(s)) broadToPapers.set(s, new Set());
      broadToPapers.get(s).add(pkey);
    }
  }
  const weight = new Map(); // "a|b" (a<b) -> count
  for (const pset of broadToPapers.values()) {
    const list = Array.from(pset).sort();
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const key = `${list[i]}|${list[j]}`;
        weight.set(key, (weight.get(key) || 0) + 1);
      }
    }
  }
  const edges = Array.from(weight.entries()).map(([k, w]) => {
    const [a, b] = k.split("|");
    return { source: a, target: b, weight: w };
  });
  const onGraph = new Set(paperToBroads.keys());
  const offGraph = Object.keys(papers).filter((k) => !onGraph.has(k));
  let maxWeight = 0;
  for (const w of weight.values()) maxWeight = Math.max(maxWeight, w);
  return { edges, weight, onGraph, offGraph, maxWeight };
}

// ---------------------------------------------------------------------
// Lateral overlay — corroborate/contradict, projected from slice-level
// `lateral` (CONCEPT §4/§9: signed, never part of the support walk).
// Only paper<->paper entries (those carrying `key`) are drawn here; a
// `slug` entry points at a broad node, not a paper, and is out of scope
// for this view. Self-referential entries (a paper laterally comparing
// two of its own slices) are dropped — not a between-papers relation.
// No mixed-sign pair exists in the current library, but if one appears
// we draw both strands rather than silently pick one.
// ---------------------------------------------------------------------
function buildLateralPairs(papers) {
  const bySign = new Map(); // "a|b|sign" -> true (a<b)
  for (const [pkey, p] of Object.entries(papers)) {
    for (const e of p.lateral || []) {
      if (!("key" in e)) continue; // slug entries target a broad node, skip
      if (e.key === pkey) continue; // self-referential, skip
      const [a, b] = [pkey, e.key].sort();
      bySign.set(`${a}|${b}|${e.sign}`, true);
    }
  }
  const pairs = [];
  for (const k of bySign.keys()) {
    const [a, b, sign] = k.split("|");
    pairs.push({ source: a, target: b, sign });
  }
  return pairs;
}

// ---------------------------------------------------------------------
// Node metadata lookup (curated paper or stub)
// ---------------------------------------------------------------------
function nodeInfo(id) {
  if (state.papers[id]) {
    const p = state.papers[id];
    return {
      id,
      curated: true,
      title: p.title,
      authors: p.authors,
      year: p.year,
      journal: null, // not carried for curated papers in graph.json
      type: p.type,
      pass: p.pass == null ? 0 : p.pass, // pass 0 (ingested) serialises as null
    };
  }
  if (state.stubs[id]) {
    const s = state.stubs[id];
    return {
      id,
      curated: false,
      title: s.title,
      authors: s.authors,
      year: s.year,
      journal: s.journal,
      type: s.type,
      pass: null,
    };
  }
  return { id, curated: false, title: id, authors: [], year: null, journal: null, pass: null };
}

function authorLine(authors) {
  if (!authors || authors.length === 0) return "";
  const names = authors.map((a) => a[0]);
  if (names.length <= 3) return names.join(", ");
  return `${names.slice(0, 3).join(", ")}, et al.`;
}

// ---------------------------------------------------------------------
// Filtering: turn a projection + threshold into the node/edge set to draw
// ---------------------------------------------------------------------
function currentFiltered() {
  if (state.mode === "A1") {
    const { edges, indeg } = state.projections.a1;
    const shown = edges.filter((e) => (indeg.get(e.target) || 0) >= state.threshold);
    const ids = new Set();
    for (const e of shown) {
      ids.add(e.source);
      ids.add(e.target);
    }
    // curated papers with zero grounds (or all below threshold) still
    // appear as isolated points — the frontier includes "grounds nothing
    // shown yet", not just "grounds a lot".
    for (const k of Object.keys(state.papers)) ids.add(k);
    return { ids, edges: shown, directed: true };
  } else {
    const { edges } = state.projections.a2;
    const shown = edges.filter((e) => e.weight >= state.threshold);
    const ids = new Set();
    for (const e of shown) {
      ids.add(e.source);
      ids.add(e.target);
    }
    // on-graph papers below threshold but above weight>=1 would otherwise
    // vanish; keep every paper that touches >=1 broad node visible as a
    // point even if none of its pairs clear the current threshold.
    for (const k of state.projections.a2.onGraph) ids.add(k);
    return { ids, edges: shown, directed: false };
  }
}

function computeDegree(ids, edges, directed) {
  const deg = new Map();
  for (const id of ids) deg.set(id, 0);
  for (const e of edges) {
    deg.set(e.source, (deg.get(e.source) || 0) + 1);
    deg.set(e.target, (deg.get(e.target) || 0) + 1);
  }
  return deg;
}

function radiusFor(degree, maxDegree) {
  if (maxDegree <= 0) return NODE_MIN_R;
  const t = Math.sqrt(degree / maxDegree);
  return NODE_MIN_R + t * (NODE_MAX_R - NODE_MIN_R);
}

// ---------------------------------------------------------------------
// Force simulation — a small hand-rolled n-body layout (no d3, per the
// no-CDN/no-npm constraint). Coulomb repulsion + spring edges + weak
// centering, integrated with velocity damping and an alpha cooldown.
// ---------------------------------------------------------------------
const SIM = {
  repulsion: 2600,
  springK: 0.06,
  springLen: 70,
  centerK: 0.015,
  damping: 0.82,
  alphaDecay: 0.02,
  alphaMin: 0.003,
};

function stepSimulation(nodes, edges, width, height) {
  const cx = width / 2, cy = height / 2;
  const a = state.alpha;

  for (const n of nodes) {
    n.fx0 = 0;
    n.fy0 = 0;
  }

  // repulsion (O(n^2); fine at prototype scale — a few hundred nodes)
  for (let i = 0; i < nodes.length; i++) {
    const ni = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const nj = nodes[j];
      let dx = ni.x - nj.x, dy = ni.y - nj.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 1) d2 = 1;
      const d = Math.sqrt(d2);
      const f = (SIM.repulsion * a) / d2;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      ni.fx0 += fx; ni.fy0 += fy;
      nj.fx0 -= fx; nj.fy0 -= fy;
    }
  }

  // springs along edges
  for (const e of edges) {
    const s = e._s, t = e._t;
    if (!s || !t) continue;
    let dx = t.x - s.x, dy = t.y - s.y;
    let d = Math.sqrt(dx * dx + dy * dy) || 0.01;
    const rest = SIM.springLen + s.r + t.r;
    const f = SIM.springK * (d - rest) * a;
    const fx = (dx / d) * f, fy = (dy / d) * f;
    s.fx0 += fx; s.fy0 += fy;
    t.fx0 -= fx; t.fy0 -= fy;
  }

  // centering
  for (const n of nodes) {
    n.fx0 += (cx - n.x) * SIM.centerK * a;
    n.fy0 += (cy - n.y) * SIM.centerK * a;
  }

  for (const n of nodes) {
    if (n.fixed) continue;
    n.vx = (n.vx + n.fx0) * SIM.damping;
    n.vy = (n.vy + n.fy0) * SIM.damping;
    n.x += n.vx;
    n.y += n.vy;
  }
}

// ---------------------------------------------------------------------
// SVG scaffolding
// ---------------------------------------------------------------------
function initSvg() {
  state.svg = document.getElementById("canvas");
  state.viewport = document.createElementNS(SVG_NS, "g");
  state.viewport.setAttribute("id", "viewport");
  state.svg.appendChild(state.viewport);

  state.edgeLayer = document.createElementNS(SVG_NS, "g");
  state.edgeLayer.setAttribute("id", "edge-layer");
  state.lateralLayer = document.createElementNS(SVG_NS, "g");
  state.lateralLayer.setAttribute("id", "lateral-layer");
  state.nodeLayer = document.createElementNS(SVG_NS, "g");
  state.nodeLayer.setAttribute("id", "node-layer");
  state.viewport.appendChild(state.edgeLayer);
  state.viewport.appendChild(state.lateralLayer);
  state.viewport.appendChild(state.nodeLayer);

  wirePanZoom();
  state.svg.addEventListener("click", () => unpin());
}

function applyTransform() {
  const { x, y, k } = state.pan;
  state.viewport.setAttribute("transform", `translate(${x},${y}) scale(${k})`);
}

function wirePanZoom() {
  let panning = false;
  let lastX = 0, lastY = 0;

  state.svg.addEventListener("mousedown", (ev) => {
    if (ev.target.closest(".node")) return; // node drag handles itself
    panning = true;
    lastX = ev.clientX;
    lastY = ev.clientY;
    state.svg.classList.add("panning");
  });
  window.addEventListener("mousemove", (ev) => {
    if (!panning) return;
    state.pan.x += ev.clientX - lastX;
    state.pan.y += ev.clientY - lastY;
    lastX = ev.clientX;
    lastY = ev.clientY;
    applyTransform();
  });
  window.addEventListener("mouseup", () => {
    panning = false;
    state.svg.classList.remove("panning");
  });

  state.svg.addEventListener(
    "wheel",
    (ev) => {
      ev.preventDefault();
      const rect = state.svg.getBoundingClientRect();
      const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      const factor = ev.deltaY < 0 ? 1.1 : 0.9;
      const newK = Math.min(4, Math.max(0.15, state.pan.k * factor));
      // zoom about cursor
      state.pan.x = mx - ((mx - state.pan.x) * newK) / state.pan.k;
      state.pan.y = my - ((my - state.pan.y) * newK) / state.pan.k;
      state.pan.k = newK;
      applyTransform();
    },
    { passive: false }
  );
}

// ---------------------------------------------------------------------
// Pie glyph — fill = pass (0..4 -> ○ ◔ ◑ ◕ ●), null pass = stub (dashed
// empty ring, per the mark spec in §2 of the design doc).
// ---------------------------------------------------------------------
function pieSlicePath(cx, cy, r, fraction) {
  if (fraction <= 0.001) return null;
  if (fraction >= 0.999) return { full: true };
  const start = -Math.PI / 2;
  const end = start + fraction * 2 * Math.PI;
  const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
  const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
  const large = fraction > 0.5 ? 1 : 0;
  return { d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z` };
}

function buildLegendPies() {
  const g = document.getElementById("legend-pies");
  const passes = [0, 1, 2, 3, 4];
  passes.forEach((pass, i) => {
    const cx = 10 + i * 22, cy = 8, r = 7;
    const ring = document.createElementNS(SVG_NS, "circle");
    ring.setAttribute("cx", cx);
    ring.setAttribute("cy", cy);
    ring.setAttribute("r", r);
    ring.setAttribute("fill", "#14161a");
    ring.setAttribute("stroke", "#e8ecf4");
    ring.setAttribute("stroke-width", "1.3");
    g.appendChild(ring);
    const slice = pieSlicePath(cx, cy, r, pass / 4);
    if (slice && slice.full) {
      ring.setAttribute("fill", "#e8ecf4");
    } else if (slice) {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", slice.d);
      path.setAttribute("fill", "#e8ecf4");
      g.appendChild(path);
    }
  });
}

// ---------------------------------------------------------------------
// Rebuild the drawn graph from current mode/threshold and (re)start sim
// ---------------------------------------------------------------------
function rebuildAndRestart() {
  const { ids, edges, directed } = currentFiltered();
  const degree = computeDegree(ids, edges, directed);
  let maxDegree = 0;
  for (const d of degree.values()) maxDegree = Math.max(maxDegree, d);

  const rect = state.svg.getBoundingClientRect();
  const width = rect.width || 1000, height = rect.height || 700;

  // materialize / reuse simulation nodes
  const nodes = [];
  for (const id of ids) {
    let n = state.nodes.get(id);
    if (!n) {
      n = {
        id,
        x: width / 2 + (Math.random() - 0.5) * 200,
        y: height / 2 + (Math.random() - 0.5) * 200,
        vx: 0,
        vy: 0,
        fixed: false,
      };
      state.nodes.set(id, n);
    }
    n.info = nodeInfo(id);
    n.degree = degree.get(id) || 0;
    n.r = radiusFor(n.degree, maxDegree);
    nodes.push(n);
  }
  // drop stale nodes not currently shown, so the map doesn't grow forever
  for (const key of Array.from(state.nodes.keys())) {
    if (!ids.has(key)) state.nodes.delete(key);
  }

  const byId = new Map(nodes.map((n) => [n.id, n]));
  for (const e of edges) {
    e._s = byId.get(e.source);
    e._t = byId.get(e.target);
  }

  const lateralEdges = [];
  if (state.lateralOn) {
    for (const lp of state.lateralPairs) {
      const s = byId.get(lp.source), t = byId.get(lp.target);
      if (s && t) lateralEdges.push({ ...lp, _s: s, _t: t });
    }
  }

  state.current = { nodes, edges, lateralEdges, directed, width, height, maxDegree };
  renderStatic();
  state.alpha = 1;
  startSimLoop();
  updateTray();
}

function startSimLoop() {
  if (state.simTimer) cancelAnimationFrame(state.simTimer);
  const tick = () => {
    const { nodes, edges, width, height } = state.current;
    stepSimulation(nodes, edges, width, height);
    state.alpha *= 1 - SIM.alphaDecay;
    renderPositions();
    if (state.alpha > SIM.alphaMin) {
      state.simTimer = requestAnimationFrame(tick);
    }
  };
  state.simTimer = requestAnimationFrame(tick);
}

// ---------------------------------------------------------------------
// Rendering — build DOM once per rebuild (renderStatic), then just move
// things each tick (renderPositions) for performance.
// ---------------------------------------------------------------------
function renderStatic() {
  state.edgeLayer.textContent = "";
  state.lateralLayer.textContent = "";
  state.nodeLayer.textContent = "";

  const { nodes, edges, lateralEdges, directed } = state.current;

  // arrowhead marker for A1 (directed)
  ensureArrowMarker();

  for (const e of edges) {
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("class", "edge");
    line.setAttribute("stroke-width", directed ? 1 : Math.min(4, 0.7 + e.weight * 0.6));
    if (directed) line.setAttribute("marker-end", "url(#arrow)");
    e._el = line;
    state.edgeLayer.appendChild(line);
  }

  for (const e of lateralEdges) {
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("class", `edge lateral ${e.sign === "corr" ? "corr" : "contra"}`);
    line.setAttribute("stroke-width", 1.6);
    e._el = line;
    state.lateralLayer.appendChild(line);
  }

  for (const n of nodes) {
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", "node");
    g.dataset.id = n.id;

    const ring = document.createElementNS(SVG_NS, "circle");
    ring.setAttribute("class", "ring");
    ring.setAttribute("r", n.r);
    ring.setAttribute("fill", "#14161a");
    if (n.info.curated) {
      ring.setAttribute("stroke", "#e8ecf4");
      ring.setAttribute("stroke-width", "1.4");
    } else {
      ring.setAttribute("stroke", "#4b515e");
      ring.setAttribute("stroke-width", "1.4");
      ring.setAttribute("stroke-dasharray", "3 2");
    }
    g.appendChild(ring);

    const fraction = n.info.pass == null ? 0 : n.info.pass / 4;
    const slice = pieSlicePath(0, 0, n.r, fraction);
    if (slice && slice.full) {
      ring.setAttribute("fill", "#e8ecf4");
    } else if (slice) {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", slice.d);
      path.setAttribute("fill", "#e8ecf4");
      path.setAttribute("stroke", "none");
      g.appendChild(path);
    }

    const hit = document.createElementNS(SVG_NS, "circle");
    hit.setAttribute("class", "disc");
    hit.setAttribute("r", Math.max(n.r, 8));
    hit.setAttribute("fill", "transparent");
    g.appendChild(hit);

    g.addEventListener("mouseenter", (ev) => onNodeHover(n, ev));
    g.addEventListener("mousemove", (ev) => positionTooltip(ev));
    g.addEventListener("mouseleave", onNodeUnhover);
    g.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onNodeClick(n);
    });
    g.addEventListener("mousedown", (ev) => startDrag(ev, n));

    n._el = g;
    state.nodeLayer.appendChild(g);
  }

  renderPositions();
  applyPinDim();
}

function ensureArrowMarker() {
  if (document.getElementById("arrow")) return;
  const defs = document.createElementNS(SVG_NS, "defs");
  const marker = document.createElementNS(SVG_NS, "marker");
  marker.setAttribute("id", "arrow");
  marker.setAttribute("viewBox", "0 0 8 8");
  marker.setAttribute("refX", "7");
  marker.setAttribute("refY", "4");
  marker.setAttribute("markerWidth", "5");
  marker.setAttribute("markerHeight", "5");
  marker.setAttribute("orient", "auto-start-reverse");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", "M0,0 L8,4 L0,8 z");
  path.setAttribute("fill", "#5a6272");
  marker.appendChild(path);
  defs.appendChild(marker);
  state.svg.appendChild(defs);
}

function renderPositions() {
  const { edges, lateralEdges, nodes } = state.current;
  for (const e of edges) {
    if (!e._s || !e._t) continue;
    e._el.setAttribute("x1", e._s.x);
    e._el.setAttribute("y1", e._s.y);
    e._el.setAttribute("x2", e._t.x);
    e._el.setAttribute("y2", e._t.y);
  }
  for (const e of lateralEdges) {
    e._el.setAttribute("x1", e._s.x);
    e._el.setAttribute("y1", e._s.y);
    e._el.setAttribute("x2", e._t.x);
    e._el.setAttribute("y2", e._t.y);
  }
  for (const n of nodes) {
    n._el.setAttribute("transform", `translate(${n.x},${n.y})`);
  }
}

// ---------------------------------------------------------------------
// Interaction — hover tooltip, click-to-pin-and-dim, drag
// ---------------------------------------------------------------------
function onNodeHover(n, ev) {
  state.hovered = n;
  const tt = document.getElementById("tooltip");
  const info = n.info;
  const kindTag = info.curated ? `curated · pass ${info.pass}/4 · ${info.type || "—"}` : "stub";
  const journalLine = info.journal ? `<div class="tt-line">${escapeHtml(info.journal)}</div>` : "";
  tt.innerHTML = `
    <div class="tt-title">${escapeHtml(info.title || info.id)}</div>
    <div class="tt-line">${escapeHtml(authorLine(info.authors))}</div>
    <div class="tt-line">${info.year || "—"}</div>
    ${journalLine}
    <div class="tt-line">degree in current view: ${n.degree}</div>
    <span class="tt-tag">${kindTag}</span>
  `;
  tt.classList.remove("hidden");
  positionTooltip(ev);
}
function positionTooltip(ev) {
  const tt = document.getElementById("tooltip");
  if (tt.classList.contains("hidden")) return;
  const pad = 14;
  tt.style.left = ev.clientX + pad + "px";
  tt.style.top = ev.clientY + pad + "px";
}
function onNodeUnhover() {
  state.hovered = null;
  document.getElementById("tooltip").classList.add("hidden");
}

function onNodeClick(n) {
  if (state.pinned === n.id) {
    unpin();
    return;
  }
  state.pinned = n.id;
  showPinPanel(n);
  applyPinDim();
}
function unpin() {
  state.pinned = null;
  document.getElementById("pin-panel").classList.add("hidden");
  applyPinDim();
}
function showPinPanel(n) {
  const info = n.info;
  document.getElementById("pin-title").textContent = info.title || info.id;
  const bits = [];
  bits.push(authorLine(info.authors));
  bits.push(String(info.year || "—"));
  bits.push(info.curated ? `curated · pass ${info.pass}/4` : "stub");
  document.getElementById("pin-meta").textContent = bits.join(" · ");
  document.getElementById("pin-citekey").value = info.id;
  // The citekey is the seam: the field is for copying it into a terminal, the link for taking it
  // to the board. A stub gets the link too — "a big empty ring is the next paper to curate" is
  // this view's headline reading, and the board mints a landing card for a stub on demand.
  const go = document.getElementById("pin-board");
  go.href = boardHref(info.id);
  go.hidden = !SERVED;
  document.getElementById("pin-panel").classList.remove("hidden");
}

function neighborsOf(id) {
  const { edges, lateralEdges } = state.current;
  const nb = new Set([id]);
  for (const e of edges) {
    if (e.source === id) nb.add(e.target);
    if (e.target === id) nb.add(e.source);
  }
  for (const e of lateralEdges) {
    if (e.source === id) nb.add(e.target);
    if (e.target === id) nb.add(e.source);
  }
  return nb;
}

function applyPinDim() {
  const { nodes, edges, lateralEdges } = state.current;
  if (!state.pinned) {
    for (const n of nodes) n._el.classList.remove("dim", "pinned");
    for (const e of edges) e._el.classList.remove("dim");
    for (const e of lateralEdges) e._el.classList.remove("dim");
    return;
  }
  const nb = neighborsOf(state.pinned);
  for (const n of nodes) {
    n._el.classList.toggle("dim", !nb.has(n.id));
    n._el.classList.toggle("pinned", n.id === state.pinned);
  }
  for (const e of edges) {
    e._el.classList.toggle("dim", !(nb.has(e.source) && nb.has(e.target)));
  }
  for (const e of lateralEdges) {
    e._el.classList.toggle("dim", !(nb.has(e.source) && nb.has(e.target)));
  }
}

function startDrag(ev, n) {
  ev.stopPropagation();
  n.fixed = true;
  const svgRect = state.svg.getBoundingClientRect();
  const move = (mv) => {
    const px = mv.clientX - svgRect.left, py = mv.clientY - svgRect.top;
    n.x = (px - state.pan.x) / state.pan.k;
    n.y = (py - state.pan.y) / state.pan.k;
    n.vx = 0;
    n.vy = 0;
    renderPositions();
  };
  const up = () => {
    n.fixed = false;
    state.alpha = Math.max(state.alpha, 0.3);
    startSimLoop();
    window.removeEventListener("mousemove", move);
    window.removeEventListener("mouseup", up);
  };
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", up);
}

// ---------------------------------------------------------------------
// Off-graph tray (A2 only) — curated papers with zero `cons` entries.
// A paper with no rung is a curation signal, not a bug (2026-08-03).
// ---------------------------------------------------------------------
function updateTray() {
  const tray = document.getElementById("tray");
  const list = document.getElementById("tray-list");
  if (state.mode !== "A2") {
    tray.classList.add("hidden");
    return;
  }
  tray.classList.remove("hidden");
  list.textContent = "";
  const offGraph = state.projections.a2.offGraph;
  for (const id of offGraph) {
    const info = nodeInfo(id);
    const row = document.createElement("div");
    row.className = "tray-item";
    const pieSvg = document.createElementNS(SVG_NS, "svg");
    pieSvg.setAttribute("width", "16");
    pieSvg.setAttribute("height", "16");
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("transform", "translate(8,8)");
    const ring = document.createElementNS(SVG_NS, "circle");
    ring.setAttribute("r", 6.5);
    ring.setAttribute("fill", "#14161a");
    ring.setAttribute("stroke", "#e8ecf4");
    ring.setAttribute("stroke-width", "1.2");
    g.appendChild(ring);
    const fraction = info.pass == null ? 0 : info.pass / 4;
    const slice = pieSlicePath(0, 0, 6.5, fraction);
    if (slice && slice.full) ring.setAttribute("fill", "#e8ecf4");
    else if (slice) {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", slice.d);
      path.setAttribute("fill", "#e8ecf4");
      g.appendChild(path);
    }
    pieSvg.appendChild(g);
    row.appendChild(pieSvg);
    const title = document.createElement("div");
    title.className = "tray-title";
    title.innerHTML = `${escapeHtml(info.title || id)} <span class="tray-year">(${info.year || "—"})</span>`;
    row.appendChild(title);
    list.appendChild(row);
  }
  const h2 = tray.querySelector("h2");
  h2.innerHTML = `off-graph <span class="sub">— ${offGraph.length} curated, no <code>cons</code></span>`;
}

// ---------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------
function applyModeDefaults() {
  const label = document.getElementById("threshold-label");
  const slider = document.getElementById("threshold-slider");
  if (state.mode === "A1") {
    slider.min = 1;
    slider.max = Math.max(2, state.projections.a1.maxIndeg);
    state.threshold = 2;
    slider.value = 2;
    label.textContent = `in-degree ≥ ${state.threshold}`;
  } else {
    slider.min = 1;
    slider.max = Math.max(2, state.projections.a2.maxWeight);
    state.threshold = 2;
    slider.value = 2;
    label.textContent = `weight ≥ ${state.threshold}`;
  }
}

function wireControls() {
  document.querySelectorAll('input[name="mode"]').forEach((r) => {
    r.addEventListener("change", (ev) => {
      if (!ev.target.checked) return;
      state.mode = ev.target.value;
      state.pinned = null;
      document.getElementById("pin-panel").classList.add("hidden");
      applyModeDefaults();
      rebuildAndRestart();
    });
  });

  const slider = document.getElementById("threshold-slider");
  slider.addEventListener("input", () => {
    state.threshold = Number(slider.value);
    const label = document.getElementById("threshold-label");
    label.textContent =
      state.mode === "A1" ? `in-degree ≥ ${state.threshold}` : `weight ≥ ${state.threshold}`;
    rebuildAndRestart();
  });

  document.getElementById("lateral-toggle").addEventListener("change", (ev) => {
    state.lateralOn = ev.target.checked;
    rebuildAndRestart();
  });

  document.getElementById("pin-close").addEventListener("click", unpin);

  window.addEventListener("resize", () => {
    if (state.current) {
      const rect = state.svg.getBoundingClientRect();
      state.current.width = rect.width;
      state.current.height = rect.height;
    }
  });
}

function setStatus(text) {
  document.getElementById("status-text").textContent = text;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

main().catch((err) => {
  console.error(err);
  setStatus("error: " + err.message);
});

/* The way back (see SERVED at the top): standalone there is no board above this page, so the
   link stays hidden rather than pointing at a 404. On a phone this is the whole of the way
   back — the board's menu opens views in the same tab on touch, so the back gesture works too,
   but a visible door beats a remembered gesture. */
if (SERVED) {
  const back = document.getElementById('back');
  if (back) { back.href = '/'; back.hidden = false; }
}
