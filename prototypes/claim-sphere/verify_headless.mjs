#!/usr/bin/env node
/* Throwaway verification script — NOT part of the shipped prototype.
 *
 * Runs the REAL browser code path (model.js -> scene.js) under plain Node,
 * with no renderer/canvas/WebGL context at all. jsdom wouldn't give a real
 * GL context either, so there is nothing to gain from it here — three.js's
 * Scene/Group/BufferGeometry/InstancedMesh/LOD/Points classes are pure JS
 * data structures; only rendering needs a GPU, and this script never calls
 * renderer.render(). It exercises exactly the scene-graph construction path
 * app.js runs on load, confirms nothing throws, and cross-checks node/edge
 * counts against the model those objects were built from.
 *
 * Usage: node verify_headless.mjs --graph /path/to/graph.json
 */
import { readFileSync } from 'node:fs';
import { buildModel } from './model.js';
import { buildScene } from './scene.js';

const graphArgIdx = process.argv.indexOf('--graph');
if (graphArgIdx === -1 || !process.argv[graphArgIdx + 1]) {
  console.error('usage: node verify_headless.mjs --graph /path/to/graph.json');
  process.exit(2);
}
const graphPath = process.argv[graphArgIdx + 1];

let failures = 0;
function check(label, cond, detail) {
  const ok = !!cond;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}${detail !== undefined ? '  (' + detail + ')' : ''}`);
  if (!ok) failures++;
}

console.log('=== loading graph.json ===');
const raw = JSON.parse(readFileSync(graphPath, 'utf8'));
console.log(`papers=${Object.keys(raw.papers).length} broad=${Object.keys(raw.broad).length}`);

console.log('\n=== buildModel() ===');
const t0 = Date.now();
const model = buildModel(raw);
console.log(`ok, ${Date.now() - t0}ms`);
console.log(model.stats);

console.log('\n=== buildScene() — the real scene-graph construction path ===');
const t1 = Date.now();
const scene = buildScene(model);
console.log(`ok, ${Date.now() - t1}ms, no throw`);
console.log(scene.stats);

console.log('\n=== cross-checks: scene counts vs model counts ===');
const inShellSlices = [...model.slices.values()].filter((n) => !n.inHalo).length;
const inShellBroad = [...model.broad.values()].filter((n) => !n.inHalo).length;
check('full-resolution LOD node count == model in-shell count',
  scene.stats.nFullNodes === inShellSlices + inShellBroad,
  `scene=${scene.stats.nFullNodes} model=${inShellSlices + inShellBroad}`);
check('broad-level LOD node count == model in-shell broad count',
  scene.stats.nBroadLevelNodes === inShellBroad,
  `scene=${scene.stats.nBroadLevelNodes} model=${inShellBroad}`);
check('family-level LOD node count == 16',
  scene.stats.nFamilyLevelNodes === 16,
  `scene=${scene.stats.nFamilyLevelNodes}`);
check('halo point counts match model halo counts',
  scene.stats.nHaloSlice === model.stats.nHaloSlices && scene.stats.nHaloBroad === model.stats.nHaloBroad,
  `scene=${scene.stats.nHaloSlice}/${scene.stats.nHaloBroad} model=${model.stats.nHaloSlices}/${model.stats.nHaloBroad}`);
check('position map covers every slice + broad node (no orphans)',
  model.position.size === model.slices.size + model.broad.size,
  `position=${model.position.size} nodes=${model.slices.size + model.broad.size}`);

const expectedEdgeUp = model.edges.up.length;
const expectedEdgeGen = model.edges.gen.length;
const expectedEdgeCons = model.edges.cons.length;
const expectedEdgeLadder = model.edges.ladder.length;
const expectedEdgeCite = model.edges.cite.length;
const expectedEdgeLateral = model.edges.lateral.length;
check('edge line counts match model edge lists',
  scene.stats.edgeCounts.up === expectedEdgeUp &&
  scene.stats.edgeCounts.gen === expectedEdgeGen &&
  scene.stats.edgeCounts.cons === expectedEdgeCons &&
  scene.stats.edgeCounts.ladder === expectedEdgeLadder &&
  scene.stats.edgeCounts.cite === expectedEdgeCite &&
  scene.stats.edgeCounts.lateral === expectedEdgeLateral,
  JSON.stringify(scene.stats.edgeCounts) + ' vs model ' + JSON.stringify({
    up: expectedEdgeUp, gen: expectedEdgeGen, cons: expectedEdgeCons,
    ladder: expectedEdgeLadder, cite: expectedEdgeCite, lateral: expectedEdgeLateral,
  }));

console.log('\n=== exercising applyRadialWindow() (the shell-peel control) ===');
try {
  scene.applyRadialWindow(model.families ? 1.6 : 0, 100);
  scene.applyRadialWindow(6, 9);
  scene.applyRadialWindow(0, 0); // degenerate window — everything should hide, must not throw
  console.log('PASS  applyRadialWindow() across several windows, no throw');
} catch (e) {
  console.log('FAIL  applyRadialWindow() threw:', e.message);
  failures++;
}

console.log('\n=== LOD level distances (ascending, family furthest) ===');
const dists = scene.lod.levels.map((l) => l.distance);
check('LOD levels are strictly increasing (full < broad < family)',
  dists[0] < dists[1] && dists[1] < dists[2], dists.join(' < '));

console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : failures + ' CHECK(S) FAILED'}`);
process.exit(failures === 0 ? 0 : 1);
