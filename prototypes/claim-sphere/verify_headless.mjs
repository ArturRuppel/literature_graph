#!/usr/bin/env node
/* Throwaway verification script — NOT part of the shipped prototype.
 *
 * Runs the REAL browser code path (derive-model.js) under plain Node, with no
 * DOM and no canvas. deriveModel is pure — it reads a parsed graph.json and
 * returns plain data — so the whole coordinate derivation is testable here;
 * only the drawing needs a browser, and this script never touches it.
 *
 * It checks the invariants the renderer depends on rather than pinning the
 * counts, which move every time a paper is curated:
 *
 *   - every node has finite coordinates and an r in the expected band;
 *   - in-ball nodes have BOTH coordinates, haze nodes are missing at least
 *     one, and no node is quietly given a family it was not authored into;
 *   - the plate index is injective across slices and broad nodes (the
 *     collision a fifth slice rank would otherwise introduce);
 *   - every edge names two real node indices;
 *   - the family axes are unit vectors and pairwise distinct.
 *
 * Cross-check the counts against verify.py, which re-derives them in Python
 * from scratch — a match between the two is a real check, not the same bug
 * twice.
 *
 * Usage: node verify_headless.mjs --graph /path/to/graph.json
 */
import { readFileSync } from 'node:fs';
import { deriveModel } from './derive-model.js';

const i = process.argv.indexOf('--graph');
if (i === -1 || !process.argv[i + 1]) {
  console.error('usage: node verify_headless.mjs --graph /path/to/graph.json');
  process.exit(2);
}

const t0 = Date.now();
const m = deriveModel(JSON.parse(readFileSync(process.argv[i + 1], 'utf8')));
const ms = Date.now() - t0;
const s = m.stats;
let bad = 0;
const check = (ok, label, detail = '') => {
  if (!ok) bad++;
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${label}${detail ? '  — ' + detail : ''}`);
};

console.log('=== derived model ===');
console.log(`nodes ${m.nodes.length} (${s.slices} slices + ${s.broad} broad) · edges ${m.edges.length}  [${ms} ms]`);
console.log(`floors ${s.floors} · ranked ${s.ranked} · unfloored ${s.unfloored}`);
console.log(`family: ${s.famAuthored} authored + ${s.famInherited} inherited · halo ${s.halo}`);
console.log(`families ${s.families} · maxSlice ${s.maxSlice} · maxTier ${s.maxTier}`);
console.log(`edges by kind: ${JSON.stringify(s.edges)}`);

console.log('\n=== invariants ===');

check(m.nodes.every(n => [n.x, n.y, n.z, n.r].every(Number.isFinite)), 'every node has finite coordinates');

const inBall = m.nodes.filter(n => !n.halo);
const haze = m.nodes.filter(n => n.halo);
check(inBall.every(n => n.r >= 0.129 && n.r <= 1.001), 'in-ball radii lie in [0.13, 1]',
  `min ${Math.min(...inBall.map(n => n.r))} max ${Math.max(...inBall.map(n => n.r))}`);
check(haze.every(n => n.r >= 1.09 && n.r <= 2.06), 'haze radii lie outside the sphere',
  haze.length ? `min ${Math.min(...haze.map(n => n.r))} max ${Math.max(...haze.map(n => n.r))}` : 'none');

/* rule 4: the ball is exactly the nodes with both coordinates */
check(inBall.every(n => n.lvl != null && n.fam && n.fam.length), 'every in-ball node has both coordinates');
check(haze.every(n => n.lvl == null || !n.fam || !n.fam.length), 'every haze node is missing at least one');
check(haze.every(n => n.t === 's'), 'no broad node is in the haze');

/* rule 3: a family is authored or inherited through the local ladder — never invented */
check(m.nodes.every(n => !n.fam || !n.fam.length || n.famSrc === 'authored' || n.famSrc === 'inherited'),
  'every family is marked authored or inherited');
check(m.nodes.filter(n => n.t === 'b').every(n => n.famSrc === 'authored'), 'every broad node’s family is authored');
check(m.nodes.every(n => !n.fam || n.fam.every(k => k >= 0 && k < s.families)), 'family indices are in range');

/* the plate index the shells layout uses must not collide */
const nP = (s.maxSlice + 1) + (s.maxTier + 1);
const plateOf = n => (n.t === 'b' ? (s.maxSlice + 1) + (s.maxTier - n.lvl) : n.lvl);
const ranked = m.nodes.filter(n => n.lvl != null);
check(ranked.every(n => { const k = plateOf(n); return k >= 0 && k < nP; }), `plate index stays in [0, ${nP - 1}]`);
const sliceP = new Set(ranked.filter(n => n.t === 's').map(plateOf));
const broadP = new Set(ranked.filter(n => n.t === 'b').map(plateOf));
check([...sliceP].every(k => !broadP.has(k)), 'no plate holds both slices and broad nodes',
  `slices ${[...sliceP].sort((a, b) => a - b)} · broad ${[...broadP].sort((a, b) => a - b)}`);

/* edges */
check(m.edges.every(e => m.nodes[e.a] && m.nodes[e.b]), 'every edge names two real nodes');
check(m.edges.every(e => e.a !== e.b), 'no self-edges');
check(m.edges.filter(e => e.k === 'lat').every(e => e.sign === 'corr' || e.sign === 'contra'),
  'every lateral edge is signed');

/* family axes */
check(m.families.every(f => Math.abs(Math.hypot(...f.axis) - 1) < 1e-3), 'family axes are unit vectors');
check(new Set(m.families.map(f => f.axis.join(','))).size === m.families.length, 'family axes are pairwise distinct');
check(m.families.reduce((a, f) => a + f.members, 0) >= s.famAuthored + s.famInherited,
  'branch member counts cover every familied slice');

console.log('\n=== the sixteen, in ladder order ===');
m.families.forEach((f, k) => console.log(`  ${String(k).padStart(2)}  ${String(f.members).padStart(4)}  ${f.kind.padEnd(15)} ${f.title}`));

console.log(`\n${bad ? bad + ' FAILED' : 'all invariants hold'}.`);
process.exit(bad ? 1 : 0);
