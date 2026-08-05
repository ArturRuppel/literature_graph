/* Claim sphere — scene.js. Builds the three.js scene graph from a model.js
 * `buildModel()` result. Deliberately kept import-clean (only three.module.js
 * + model.js) so this file can be `import`ed and exercised from Node with NO
 * renderer/canvas/WebGL context — jsdom won't give a real GL context, and
 * the task doesn't need one: constructing Scene / Group / BufferGeometry /
 * InstancedMesh / LineSegments objects and populating their attribute
 * arrays needs no GPU. That's what the headless verifier (verify_headless.mjs)
 * exercises: this module's construction path, node/edge counts, nothing more.
 *
 * RULE 2 (colour is read, not derived) applies here too: every fill colour
 * below comes from the PALETTE table keyed off graph.json's own `color`
 * field, or off `is_floor`/`answered`/broad `kind` — never recomputed.
 *
 * RULE 3 (LOD merges along the authored ladder only): the three detail
 * levels of the returned THREE.LOD are drawn from the SAME position map
 * model.js already computed for slices/broad/families — nothing here
 * clusters by distance or re-derives a merge target.
 */
import * as THREE from './vendor/three.module.js';

// Palette matches prototypes/claim-graph/app.js exactly — same accent hues
// mean the same thing in both prototypes, and both trace back to dist's own
// CSS custom properties. Not re-invented here.
export const PALETTE = {
  floor: 0xb5822f,
  model: 0x8a6db1,
  grounded: 0x27735f,
  borrowed: 0x286b9f,
  question: 0xa15c1e,
  plausible: 0x8a97a4,
  broadClaim: 0x7a4fb0,
  broadMethod: 0x8a6db1,
  broadQuestion: 0xa15c1e,
  cross: 0x9a3b3b,
  corr: 0x27735f,
  line: 0xc3cbd2,
  halo: 0x8a97a4,
  family: 0xe0c264,
};

function sliceColor(s) {
  if (s.sliceKind === 'question' && !s.answered) return 0xffffff;
  return PALETTE[s.color] !== undefined ? PALETTE[s.color] : 0x999999;
}
function broadColor(b) {
  if (b.broadKind === 'broad claim') return PALETTE.broadClaim;
  if (b.broadKind === 'broad method') return PALETTE.broadMethod;
  return PALETTE.broadQuestion;
}

const SHAPE_GEOM = {
  claim: new THREE.SphereGeometry(0.1, 8, 6),
  method: new THREE.BoxGeometry(0.16, 0.16, 0.16),
  question: new THREE.ConeGeometry(0.11, 0.2, 6),
};
const BROAD_GEOM = new THREE.OctahedronGeometry(0.26, 0);
const FAMILY_GEOM = new THREE.IcosahedronGeometry(0.55, 1);
const HALO_GEOM_POINT = 0.06; // point size for halo clouds, see buildHalo()

function instancedFor(geom, count) {
  const mat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true });
  const mesh = new THREE.InstancedMesh(geom, mat, Math.max(count, 1));
  mesh.count = count;
  mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(Math.max(count, 1) * 3), 3);
  return mesh;
}

const _m = new THREE.Matrix4();
const _c = new THREE.Color();

// -----------------------------------------------------------------------
// Full-resolution level (867): every slice + broad node IN THE SHELL
// (halo nodes are drawn separately, see buildHalo — they never merge and
// are never part of the ladder-based LOD, RULE 3).
// -----------------------------------------------------------------------
function buildFullLevel(model) {
  const group = new THREE.Group();
  group.name = 'lod-full-867';
  const pickIndex = []; // parallel: [{mesh, instanceId, key}]

  const byKind = { claim: [], method: [], question: [] };
  for (const [key, s] of model.slices) {
    if (s.inHalo) continue;
    byKind[s.sliceKind]?.push(key);
  }
  for (const [kind, keys] of Object.entries(byKind)) {
    const mesh = instancedFor(SHAPE_GEOM[kind], keys.length);
    keys.forEach((key, i) => {
      const s = model.slices.get(key);
      const p = model.position.get(key);
      _m.makeTranslation(p.x, p.y, p.z);
      mesh.setMatrixAt(i, _m);
      mesh.setColorAt(i, _c.setHex(sliceColor(s)));
      pickIndex.push({ mesh, instanceId: i, key, pos: p, scale: 1 });
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    group.add(mesh);
  }

  const broadKeys = [...model.broad.keys()].filter((k) => !model.broad.get(k).inHalo);
  const broadMesh = instancedFor(BROAD_GEOM, broadKeys.length);
  broadKeys.forEach((key, i) => {
    const b = model.broad.get(key);
    const p = model.position.get(key);
    _m.makeTranslation(p.x, p.y, p.z);
    broadMesh.setMatrixAt(i, _m);
    broadMesh.setColorAt(i, _c.setHex(broadColor(b)));
    pickIndex.push({ mesh: broadMesh, instanceId: i, key, pos: p, scale: 1 });
  });
  broadMesh.instanceMatrix.needsUpdate = true;
  if (broadMesh.instanceColor) broadMesh.instanceColor.needsUpdate = true;
  group.add(broadMesh);

  return { group, pickIndex, nNodes: [...Object.values(byKind)].reduce((a, k) => a + k.length, 0) + broadKeys.length };
}

// -----------------------------------------------------------------------
// Broad level (45): one marker per broad node, at its OWN shell position.
// A slice, at this LOD, visually reads as "collapsed into" whichever
// broad marker sits at its `broadSlug` — but we don't move slices here;
// we simply stop drawing them and show the 45 instead. That satisfies
// RULE 3 ("collapses into its nearest ancestor, nothing else") without
// needing to fake a slice-count-weighted size on the broad marker
// (quantitative readouts stay 2D HTML, per the doc).
// -----------------------------------------------------------------------
function buildBroadLevel(model) {
  const group = new THREE.Group();
  group.name = 'lod-broad-45';
  const keys = [...model.broad.keys()].filter((k) => !model.broad.get(k).inHalo);
  const mesh = instancedFor(BROAD_GEOM, keys.length);
  const pickIndex = [];
  keys.forEach((key, i) => {
    const b = model.broad.get(key);
    const p = model.position.get(key);
    _m.compose(new THREE.Vector3(p.x, p.y, p.z), new THREE.Quaternion(), new THREE.Vector3(1.6, 1.6, 1.6));
    mesh.setMatrixAt(i, _m);
    mesh.setColorAt(i, _c.setHex(broadColor(b)));
    pickIndex.push({ mesh, instanceId: i, key, pos: p, scale: 1.6 });
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  group.add(mesh);
  return { group, pickIndex, nNodes: keys.length };
}

// -----------------------------------------------------------------------
// Family level (16): one marker per top-level family, Fibonacci-distributed.
// Positioned at the family's own shell/halo position (families 3/16 are
// themselves unfloored questions and sit in the halo — see report).
// -----------------------------------------------------------------------
function buildFamilyLevel(model) {
  const group = new THREE.Group();
  group.name = 'lod-family-16';
  const mesh = instancedFor(FAMILY_GEOM, model.families.length);
  const pickIndex = [];
  model.families.forEach((f, i) => {
    const key = 'b::' + f.slug;
    const p = model.position.get(key);
    _m.makeTranslation(p.x, p.y, p.z);
    mesh.setMatrixAt(i, _m);
    mesh.setColorAt(i, _c.setHex(PALETTE.family));
    pickIndex.push({ mesh, instanceId: i, key });
  });
  mesh.instanceMatrix.needsUpdate = true;
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  group.add(mesh);
  return { group, pickIndex, nNodes: model.families.length };
}

// -----------------------------------------------------------------------
// Halo — always-on diffuse cloud, never part of LOD merging (nothing
// authored to merge INTO). Two Points objects (slice halo / broad halo)
// so picking can still tell them apart.
// -----------------------------------------------------------------------
function buildHalo(model) {
  const group = new THREE.Group();
  group.name = 'halo';
  const build = (keys, colorFn) => {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(keys.length * 3);
    const col = new Float32Array(keys.length * 3);
    keys.forEach((key, i) => {
      const p = model.position.get(key);
      pos[i * 3] = p.x; pos[i * 3 + 1] = p.y; pos[i * 3 + 2] = p.z;
      _c.setHex(colorFn(key));
      col[i * 3] = _c.r; col[i * 3 + 1] = _c.g; col[i * 3 + 2] = _c.b;
    });
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const mat = new THREE.PointsMaterial({ size: HALO_GEOM_POINT, vertexColors: true, transparent: true, opacity: 0.55, sizeAttenuation: true });
    const pts = new THREE.Points(geo, mat);
    return pts;
  };
  const sliceHaloKeys = [...model.slices.keys()].filter((k) => model.slices.get(k).inHalo);
  const broadHaloKeys = [...model.broad.keys()].filter((k) => model.broad.get(k).inHalo);
  const slicePts = build(sliceHaloKeys, (k) => sliceColor(model.slices.get(k)));
  const broadPts = build(broadHaloKeys, (k) => broadColor(model.broad.get(k)));
  slicePts.userData.indexToKey = sliceHaloKeys;
  broadPts.userData.indexToKey = broadHaloKeys;
  group.add(slicePts, broadPts);
  return { group, slicePts, broadPts, nSlice: sliceHaloKeys.length, nBroad: broadHaloKeys.length };
}

// -----------------------------------------------------------------------
// Edges — one LineSegments per kind, built from model.position directly.
// -----------------------------------------------------------------------
const EDGE_COLOR = {
  up: PALETTE.line, gen: PALETTE.line,
  cons: 0xb6a4d6, ladder: PALETTE.broadClaim, cite: PALETTE.borrowed,
};
function buildEdgeLines(model) {
  const out = {};
  for (const kind of ['up', 'gen', 'cons', 'ladder', 'cite']) {
    const list = model.edges[kind];
    const pos = new Float32Array(list.length * 6);
    let n = 0;
    for (const e of list) {
      const a = model.position.get(e.from), b = model.position.get(e.to);
      if (!a || !b) continue;
      pos[n * 6] = a.x; pos[n * 6 + 1] = a.y; pos[n * 6 + 2] = a.z;
      pos[n * 6 + 3] = b.x; pos[n * 6 + 4] = b.y; pos[n * 6 + 5] = b.z;
      n++;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos.subarray(0, n * 6), 3));
    const mat = new THREE.LineBasicMaterial({ color: EDGE_COLOR[kind], transparent: true, opacity: 0.35 });
    const line = new THREE.LineSegments(geo, mat);
    line.name = 'edges-' + kind;
    out[kind] = { line, count: n };
  }
  // lateral: signed, drawn distinctly, colour by sign
  {
    const list = model.edges.lateral;
    const pos = new Float32Array(list.length * 6);
    const col = new Float32Array(list.length * 6);
    let n = 0;
    for (const e of list) {
      const a = model.position.get(e.a), b = model.position.get(e.b);
      if (!a || !b) continue;
      pos[n * 6] = a.x; pos[n * 6 + 1] = a.y; pos[n * 6 + 2] = a.z;
      pos[n * 6 + 3] = b.x; pos[n * 6 + 4] = b.y; pos[n * 6 + 5] = b.z;
      _c.setHex(e.sign === 'contra' ? PALETTE.cross : PALETTE.corr);
      col[n * 6] = _c.r; col[n * 6 + 1] = _c.g; col[n * 6 + 2] = _c.b;
      col[n * 6 + 3] = _c.r; col[n * 6 + 4] = _c.g; col[n * 6 + 5] = _c.b;
      n++;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos.subarray(0, n * 6), 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col.subarray(0, n * 6), 3));
    const mat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.6 });
    const line = new THREE.LineSegments(geo, mat);
    line.name = 'edges-lateral';
    out.lateral = { line, count: n };
  }
  return out;
}

// -----------------------------------------------------------------------
// MAIN
// -----------------------------------------------------------------------
export function buildScene(model) {
  const scene = new THREE.Scene();

  const full = buildFullLevel(model);
  const broadLevel = buildBroadLevel(model);
  const familyLevel = buildFamilyLevel(model);

  const lod = new THREE.LOD();
  lod.name = 'claim-sphere-lod';
  // distances tuned against GEOM.OUTER_R=12: far -> families, mid -> broad,
  // near -> full resolution. Camera distance drives level of detail (§3.1).
  lod.addLevel(familyLevel.group, 46);
  lod.addLevel(broadLevel.group, 20);
  lod.addLevel(full.group, 0);
  scene.add(lod);

  const halo = buildHalo(model);
  scene.add(halo.group);

  const edgeLines = buildEdgeLines(model);
  const edgeGroup = new THREE.Group();
  edgeGroup.name = 'edges';
  for (const { line } of Object.values(edgeLines)) edgeGroup.add(line);
  scene.add(edgeGroup);

  // Radial shell-window peel — the altitude control AND the occlusion fix
  // (§3.1): zero-scale any instance whose *authored* radius (rank-derived,
  // straight from model.position — never re-measured off the matrix) falls
  // outside [rMin,rMax]. Recomputed only on slider change, not per-frame:
  // positions are static once built. Scoped to the shell (full + broad LOD
  // levels) — the halo is deliberately left un-peeled: it is diffuse by
  // construction, not the "filled ball" occlusion problem this control
  // solves, and it always sits outside r = GEOM.OUTER_R regardless.
  const radiusOf = (p) => Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z);
  function applyToLevel(pickIndex, rMin, rMax) {
    for (const entry of pickIndex) {
      const r = radiusOf(entry.pos);
      const visible = r >= rMin && r <= rMax;
      const s = visible ? entry.scale : 0;
      _m.compose(
        new THREE.Vector3(entry.pos.x, entry.pos.y, entry.pos.z),
        new THREE.Quaternion(),
        new THREE.Vector3(s, s, s),
      );
      entry.mesh.setMatrixAt(entry.instanceId, _m);
    }
    const touched = new Set(pickIndex.map((e) => e.mesh));
    for (const mesh of touched) mesh.instanceMatrix.needsUpdate = true;
  }
  function applyRadialWindow(rMin, rMax) {
    applyToLevel(full.pickIndex, rMin, rMax);
    applyToLevel(broadLevel.pickIndex, rMin, rMax);
    // family level (16) is always shown whole at its own LOD distance —
    // peeling 16 dots isn't the occlusion problem either.
  }

  return {
    scene, lod, halo, edgeLines, edgeGroup,
    fullLevel: full, broadLevel, familyLevel,
    applyRadialWindow,
    pickables: [lod, halo.slicePts, halo.broadPts],
    stats: {
      nFullNodes: full.nNodes,
      nBroadLevelNodes: broadLevel.nNodes,
      nFamilyLevelNodes: familyLevel.nNodes,
      nHaloSlice: halo.nSlice,
      nHaloBroad: halo.nBroad,
      edgeCounts: Object.fromEntries(Object.entries(edgeLines).map(([k, v]) => [k, v.count])),
    },
  };
}
