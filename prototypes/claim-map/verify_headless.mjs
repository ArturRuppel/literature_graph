/* Throwaway cross-check — NOT part of the shipped prototype.
 *
 * derive.js is a port of verify.py's arithmetic into the browser. A port is
 * exactly the kind of thing that drifts silently, so this runs the JS against
 * the same graph.json and prints the same summary numbers for comparison by
 * eye against `python3 verify.py --graph <same file>`.
 *
 * Usage: node verify_headless.mjs /path/to/graph.json
 */
import { readFileSync } from 'node:fs';
import { buildModel } from './derive.js';

const path = process.argv[2];
if (!path) {
  console.error('usage: node verify_headless.mjs /path/to/graph.json');
  process.exit(2);
}

const m = buildModel(JSON.parse(readFileSync(path, 'utf8')));

console.log('=== headline counts ===');
console.log(`curated papers   ${m.stats.papers}   (aims excluded: ${m.stats.aimsExcluded})`);
console.log(`broad claims     ${m.stats.claims}`);
console.log(`attachments      ${m.stats.attachments}`);
console.log(`ladder edges     ${m.stats.ladderEdges}`);

const rung = {};
for (const c of m.claims) rung[c.alt] = (rung[c.alt] || 0) + 1;
console.log(`\nrung sizes: ${JSON.stringify(rung)}`);

const down = m.claims.flatMap((c) =>
  c.leads_to.filter((t) => m.claims.find((x) => x.slug === t).alt >= c.alt));
console.log(`ladder edges that do not decrease altitude: ${down.length} (expect 0)`);

console.log(`\nclaims with a direct contra: ${m.claims.filter((c) => c.contra).length}`);
console.log('claims carrying an internal contra pair: '
  + `${m.claims.filter((c) => c.internal.length).length}`);
for (const c of [...m.claims].sort((a, b) => b.internal.length - a.internal.length).slice(0, 6)) {
  if (c.internal.length) console.log(`  ${String(c.internal.length).padStart(2)} pairs  ${c.slug}`);
}

console.log(`\nmedian-year axis spans ${Math.min(...m.claims.map((c) => c.med)).toFixed(1)}`
  + ` … ${Math.max(...m.claims.map((c) => c.med)).toFixed(1)}`);
console.log(`member-year range ${m.yearExtent[0]} … ${m.yearExtent[1]}`);

console.log('\n=== the map, as a table (sorted by weight) ===');
console.log('claim'.padEnd(52) + 'alt'.padStart(4) + 'n'.padStart(4) + 'ctr'.padStart(4)
  + 'int'.padStart(4) + '  ' + 'min'.padStart(4) + 'p25'.padStart(7)
  + 'med'.padStart(7) + 'p75'.padStart(7) + 'max'.padStart(5));
for (const c of [...m.claims].sort((a, b) => b.n - a.n)) {
  console.log(c.slug.padEnd(52) + String(c.alt).padStart(4) + String(c.n).padStart(4)
    + String(c.contra).padStart(4) + String(c.internal.length).padStart(4) + '  '
    + String(c.min).padStart(4) + c.p25.toFixed(1).padStart(7)
    + c.med.toFixed(1).padStart(7) + c.p75.toFixed(1).padStart(7)
    + String(c.max).padStart(5));
}
