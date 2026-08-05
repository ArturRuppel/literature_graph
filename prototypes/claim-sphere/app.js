/* Claim sphere — app.js. Browser-only glue: renderer, camera, controls,
 * picking, HUD wiring. All graph logic lives in model.js (pure data) and
 * scene.js (three.js scene-graph construction) — this file just drives
 * them. See docs/2026-08-05-additive-graph-views.md §3.1 for the spec.
 */
import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { FlyControls } from './vendor/FlyControls.js';
import { buildModel, GEOM } from './model.js';
import { buildScene } from './scene.js';

const $ = (id) => document.getElementById(id);

let MODEL = null, SCENE = null, model_edges_visible = {};
let renderer, camera, orbitControls, flyControls, mode = 'orbit';
let raycaster = new THREE.Raycaster();
raycaster.params.Points.threshold = 0.25;
let meshKeyLookup = new Map(); // InstancedMesh -> [key indexed by instanceId]
let selectedKey = null;
let quoteLabelPool = [];
let hoverLabelEl = null;

fetch('graph.json')
  .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
  .then((raw) => {
    MODEL = buildModel(raw);
    SCENE = buildScene(MODEL);
    registerPickIndex(SCENE.fullLevel.pickIndex);
    registerPickIndex(SCENE.broadLevel.pickIndex);
    registerPickIndex(SCENE.familyLevel.pickIndex);
    initRenderer();
    initControls();
    wireHUD();
    reportStats();
    animate();
  })
  .catch((err) => {
    $('stats').textContent = 'failed to load graph.json — ' + err.message;
    console.error(err);
  });

function registerPickIndex(pickIndex) {
  for (const entry of pickIndex) {
    if (!meshKeyLookup.has(entry.mesh)) meshKeyLookup.set(entry.mesh, []);
    meshKeyLookup.get(entry.mesh)[entry.instanceId] = entry.key;
  }
}

// =============================================================================
// RENDERER / CAMERA
// =============================================================================
function initRenderer() {
  const canvas = $('gl');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));

  camera = new THREE.PerspectiveCamera(55, 1, 0.05, 500);
  camera.position.set(0, 8, 34);

  const ambient = new THREE.AmbientLight(0xffffff, 1.0); // MeshBasicMaterial ignores lights, but harmless
  SCENE.scene.add(ambient);
  SCENE.scene.background = new THREE.Color(0x0b0e12);

  resize();
  window.addEventListener('resize', resize);
}
function resize() {
  const wrap = $('canvasWrap');
  const w = wrap.clientWidth, h = wrap.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}

// =============================================================================
// CONTROLS — orbit AND fly (§3.1: "so 'move inside' works").
// =============================================================================
function initControls() {
  orbitControls = new OrbitControls(camera, renderer.domElement);
  orbitControls.enableDamping = true;
  orbitControls.dampingFactor = 0.08;
  orbitControls.minDistance = 0.3;
  orbitControls.maxDistance = 200;

  flyControls = new FlyControls(camera, renderer.domElement);
  flyControls.movementSpeed = 10;
  flyControls.rollSpeed = 0.6;
  flyControls.dragToLook = true;
  flyControls.autoForward = false;
  flyControls.enabled = false;

  $('camera-mode').addEventListener('change', (e) => setMode(e.target.value));
  $('btn-reset-cam').addEventListener('click', () => {
    camera.position.set(0, 8, 34);
    camera.up.set(0, 1, 0);
    camera.lookAt(0, 0, 0);
    orbitControls.target.set(0, 0, 0);
  });
}
function setMode(m) {
  mode = m;
  orbitControls.enabled = (m === 'orbit');
  flyControls.enabled = (m === 'fly');
  $('gl').classList.toggle('flying', m === 'fly');
  $('crosshair').classList.toggle('show', m === 'fly');
}

// =============================================================================
// HUD WIRING
// =============================================================================
function wireHUD() {
  for (const kind of ['up', 'gen', 'cons', 'ladder', 'cite', 'lateral']) {
    model_edges_visible[kind] = true;
    $('tgl-' + kind).addEventListener('change', (e) => {
      SCENE.edgeLines[kind].line.visible = e.target.checked;
    });
  }
  $('tgl-halo').addEventListener('change', (e) => { SCENE.halo.group.visible = e.target.checked; });

  const minEl = $('shell-min'), maxEl = $('shell-max');
  const applyShell = () => {
    let a = parseFloat(minEl.value), b = parseFloat(maxEl.value);
    if (a > b) { [a, b] = [b, a]; }
    const rMin = GEOM.INNER_R + (a / 100) * (GEOM.OUTER_R - GEOM.INNER_R);
    const rMax = GEOM.INNER_R + (b / 100) * (GEOM.OUTER_R - GEOM.INNER_R);
    SCENE.applyRadialWindow(rMin, rMax);
    $('shell-readout').textContent = `r ∈ [${rMin.toFixed(1)}, ${rMax.toFixed(1)}]  (shell: ${GEOM.INNER_R}–${GEOM.OUTER_R})`;
  };
  minEl.addEventListener('input', applyShell);
  maxEl.addEventListener('input', applyShell);
  $('btn-shell-reset').addEventListener('click', () => {
    minEl.value = 0; maxEl.value = 100; applyShell();
  });
  applyShell();

  $('panel-close').addEventListener('click', clearSelection);
  $('halo-banner-close').addEventListener('click', () => $('halo-banner').classList.add('hidden'));

  renderer.domElement.addEventListener('click', onClick);
  renderer.domElement.addEventListener('pointermove', onPointerMove);
}

// =============================================================================
// PICKING
// =============================================================================
function pointerNDC(e) {
  const rect = renderer.domElement.getBoundingClientRect();
  return new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1,
  );
}
function pick(e) {
  raycaster.camera = camera; // LOD.raycast needs this
  raycaster.setFromCamera(pointerNDC(e), camera);
  const targets = [SCENE.lod, SCENE.halo.slicePts, SCENE.halo.broadPts];
  const hits = raycaster.intersectObjects(targets, true);
  for (const hit of hits) {
    if (hit.object.isPoints) {
      const idx = hit.object.userData.indexToKey;
      if (idx && idx[hit.index] !== undefined) return idx[hit.index];
      continue;
    }
    if (hit.instanceId !== undefined) {
      const arr = meshKeyLookup.get(hit.object);
      if (arr && arr[hit.instanceId] !== undefined) return arr[hit.instanceId];
    }
  }
  return null;
}
function onClick(e) {
  const key = pick(e);
  if (key) selectKey(key); else clearSelection();
}
let lastHoverAt = 0;
function onPointerMove(e) {
  const now = performance.now();
  if (now - lastHoverAt < 60) return; // throttle
  lastHoverAt = now;
  const key = pick(e);
  showHoverLabel(key, e.clientX, e.clientY);
}

// =============================================================================
// NODE LOOKUP + DETAIL PANEL
// =============================================================================
function nodeOf(key) {
  if (MODEL.slices.has(key)) return { kind: 'slice', n: MODEL.slices.get(key) };
  if (MODEL.broad.has(key)) return { kind: 'broad', n: MODEL.broad.get(key) };
  return null;
}
function escapeHTML(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function truncate(s, n) { return s && s.length > n ? s.slice(0, n - 1) + '…' : s; }

function haloFlagHTML(n) {
  if (!n.inHalo) return '';
  const missing = [];
  if (n.direction === null) missing.push('no authored family direction');
  if (n.rank === null) missing.push('no path to a floor');
  return `<div class="p-halo-flag">⚠ in the halo — ${missing.join(' · ')}. Position here is diffuse and not meaningful beyond "outside the shell".</div>`;
}

function selectKey(key) {
  selectedKey = key;
  const info = nodeOf(key);
  if (!info) return;
  const body = $('panel-body');
  if (info.kind === 'slice') {
    const s = info.n;
    body.innerHTML = `
      <div class="p-kind">${s.sliceKind} · ${s.color}${s.is_floor ? ' · FLOOR' : ''}</div>
      <h2>${escapeHTML(s.text)}</h2>
      ${haloFlagHTML(s)}
      ${s.quote ? `<div class="p-quote">"${escapeHTML(s.quote)}"</div>` : ''}
      <div class="p-row"><b>paper</b> ${escapeHTML(s.paperTitle)} (${s.paperYear})</div>
      <div class="p-row"><b>citekey</b> <code>${escapeHTML(s.paper)}</code></div>
      <div class="p-row"><b>slice</b> <code>${s.id}</code></div>
      <div class="p-row"><b>generality rank</b> ${s.rank === null ? 'unfloored' : `${s.rank} of ${MODEL.maxRank} (0 = floor)`}</div>
      <div class="p-row"><b>family</b> ${s.broadSlug ? `<code>${s.broadSlug}</code> (${s.familySource})` : 'none authored'}</div>
      <div class="p-row"><b>grounded</b> ${s.grounded} · <b>borrowed</b> ${s.borrowed} · <b>answered</b> ${s.answered}</div>
    `;
  } else {
    const b = info.n;
    body.innerHTML = `
      <div class="p-kind">${b.broadKind}${b.isTopLevel ? ' · TOP-LEVEL FAMILY' : ''}</div>
      <h2>${escapeHTML(b.title)}</h2>
      ${haloFlagHTML(b)}
      <div class="p-quote">${escapeHTML(b.text)}</div>
      <div class="p-row p-meter"><span><b>corroborate</b> ${b.meter?.s ?? 0}</span><span><b>contradict</b> ${b.meter?.c ?? 0}</span></div>
      <div class="p-row"><b>slug</b> <code>${b.slug}</code></div>
      <div class="p-row"><b>ladder rank</b> ${b.rank === null ? 'unfloored' : `${b.rank} of ${MODEL.maxRank}`}</div>
      <div class="p-row"><b>nearest top-level family</b> ${b.nearestTopSlug ? `<code>${b.nearestTopSlug}</code>` : '—'}</div>
    `;
  }
  $('panel').classList.add('open');
}
function clearSelection() { selectedKey = null; $('panel').classList.remove('open'); }

function showHoverLabel(key, x, y) {
  if (!hoverLabelEl) {
    hoverLabelEl = document.createElement('div');
    hoverLabelEl.className = 'hover-label';
    document.querySelector('main').appendChild(hoverLabelEl);
  }
  if (!key) { hoverLabelEl.style.display = 'none'; return; }
  const info = nodeOf(key);
  if (!info) { hoverLabelEl.style.display = 'none'; return; }
  const n = info.n;
  const title = info.kind === 'slice' ? truncate(n.text, 90) : n.title;
  hoverLabelEl.textContent = (n.inHalo ? '(halo) ' : '') + title;
  hoverLabelEl.style.display = 'block';
  hoverLabelEl.style.left = x + 'px';
  hoverLabelEl.style.top = y + 'px';
}

// =============================================================================
// QUOTE OVERLAY — "inside -> quote text on nearby nodes" (§3.1).
// Pure HTML labels projected from world space; only shown for the closest
// few full-resolution nodes once the camera is near enough that individual
// nodes would resolve anyway. No 3D text mesh needed.
// =============================================================================
const QUOTE_RANGE = 3.2;
const QUOTE_MAX_LABELS = 10;
function updateQuoteOverlay() {
  const main = document.querySelector('main');
  const camPos = camera.position;
  const near = [];
  for (const entry of SCENE.fullLevel.pickIndex) {
    const dx = entry.pos.x - camPos.x, dy = entry.pos.y - camPos.y, dz = entry.pos.z - camPos.z;
    const d2 = dx * dx + dy * dy + dz * dz;
    if (d2 < QUOTE_RANGE * QUOTE_RANGE) near.push({ entry, d2 });
  }
  near.sort((a, b) => a.d2 - b.d2);
  const show = near.slice(0, QUOTE_MAX_LABELS);

  while (quoteLabelPool.length < show.length) {
    const el = document.createElement('div');
    el.className = 'quote-label';
    main.appendChild(el);
    quoteLabelPool.push(el);
  }
  quoteLabelPool.forEach((el, i) => {
    if (i >= show.length) { el.style.display = 'none'; return; }
    const { entry } = show[i];
    const node = nodeOf(entry.key);
    if (!node) { el.style.display = 'none'; return; }
    const text = node.kind === 'slice' ? (node.n.quote || node.n.text) : node.n.text;
    const v = new THREE.Vector3(entry.pos.x, entry.pos.y, entry.pos.z).project(camera);
    if (v.z > 1) { el.style.display = 'none'; return; }
    const rect = main.getBoundingClientRect();
    const sx = (v.x * 0.5 + 0.5) * rect.width;
    const sy = (-v.y * 0.5 + 0.5) * rect.height;
    el.textContent = truncate(text, 100);
    el.style.left = sx + 'px';
    el.style.top = sy + 'px';
    el.style.display = 'block';
  });
}

// =============================================================================
// LOD READOUT
// =============================================================================
function updateLodReadout() {
  const d = camera.position.length();
  const levels = SCENE.lod.levels; // sorted ascending by distance
  let active = levels[0];
  for (const l of levels) if (d >= l.distance) active = l;
  const label = { 'lod-full-867': 'full resolution (867)', 'lod-broad-45': 'broad nodes (45)', 'lod-family-16': 'families (16)' }[active.object.name] || active.object.name;
  $('lod-readout').textContent = `camera r=${d.toFixed(1)} → ${label}`;
}

// =============================================================================
// STATS (loaded once)
// =============================================================================
function reportStats() {
  const st = MODEL.stats;
  $('stats').innerHTML =
    `<b>${st.nSlices}</b> slices · <b>${st.nBroad}</b> broad · <b>${st.nTopLevelFamilies}</b> families · ` +
    `<span class="warn">${st.nHaloSlices + st.nHaloBroad}/${st.nSlices + st.nBroad} nodes in the halo</span>`;
  console.log('[claim-sphere] stats', st);
}

// =============================================================================
// RENDER LOOP
// =============================================================================
const clock = new THREE.Clock();
let lastQuoteUpdate = 0;
function animate() {
  requestAnimationFrame(animate);
  const dt = clock.getDelta();
  if (mode === 'orbit') orbitControls.update();
  if (mode === 'fly') flyControls.update(dt);
  SCENE.lod.update(camera);
  updateLodReadout();
  const now = performance.now();
  if (now - lastQuoteUpdate > 100) { updateQuoteOverlay(); lastQuoteUpdate = now; }
  renderer.render(SCENE.scene, camera);
}
