/* Claim sphere — model.js. Pure data/graph logic, NO three.js and NO DOM.
 *
 * §3.1 of docs/2026-08-05-additive-graph-views.md is the spec. This module
 * turns dist/graph.json into a fully-positioned node/edge model: every slice
 * and broad node gets a direction (family, on the unit sphere), a radius
 * (generality) or null, and everything downstream (scene.js, the browser
 * app, the headless verifier) consumes this same object. Kept dependency-
 * free on purpose so it can be `import`ed unmodified from Node for the
 * headless scene-graph check — no fetch, no window, no document.
 *
 * ============================================================================
 * RULE 1 — never fabricate a coordinate (§3.1, "the coordinates are sparse").
 * A slice/broad node gets a *direction* only from an authored `cons` edge
 * (direct) or by walking its local, same-paper `gen`/`up` ladder to a slice
 * that has one (inherited). No paper-level majority vote — that was measured
 * and explicitly rejected in the design doc. A node gets a *radius* only
 * from the same distance-to-floor BFS the flat claim-graph prototype
 * already uses and has verified against graph.json's own `grounded` field.
 * Missing EITHER piece routes the node to the halo — never a sector it was
 * never assigned to, never a radius it never earned.
 *
 * RULE 2 — colour is read, not derived. `color` / `grounded` / `borrowed` /
 * `is_floor` / `answered` come straight off graph.json. Nothing here
 * recomputes "is this grounded".
 *
 * RULE 3 — LOD merges along the authored ladder only (see buildLadder()).
 * ============================================================================
 */

// ---------------------------------------------------------------------------
// small math helpers — plain {x,y,z} objects, no three.js dependency here.
// ---------------------------------------------------------------------------
function vAdd(a, b) { return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z }; }
function vScale(a, s) { return { x: a.x * s, y: a.y * s, z: a.z * s }; }
function vLen(a) { return Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z); }
function vNorm(a) {
  const l = vLen(a);
  if (l < 1e-9) return { x: 0, y: 1, z: 0 }; // degenerate average — arbitrary but stable
  return { x: a.x / l, y: a.y / l, z: a.z / l };
}
function vAvgNorm(vs) {
  let s = { x: 0, y: 0, z: 0 };
  for (const v of vs) s = vAdd(s, v);
  return vNorm(s);
}

// Deterministic pseudo-random in [0,1) from a string key — used only for
// halo jitter and within-shell packing, both explicitly meaningless by
// construction (§3.1). Never used to decide membership, only to spread
// points apart visually.
function hash01(str) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
}

// Fibonacci sphere — n points evenly distributed over the unit sphere.
// Used for the 16 top-level family directions (§3.1: "Fibonacci-distributed
// over the sphere, not wedges: family is a solid angle, 2 DOF").
export function fibonacciSphere(n) {
  const pts = [];
  const gAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = gAngle * i;
    pts.push({ x: Math.cos(theta) * r, y, z: Math.sin(theta) * r });
  }
  return pts;
}

const SEP = '::';
const sliceKey = (paper, id) => paper + SEP + id;
const broadKey = (slug) => 'b' + SEP + slug;

// ---------------------------------------------------------------------------
// 1. FAMILY DIRECTIONS — the 45 broad nodes, resolved off `broad.leads_to`.
// ---------------------------------------------------------------------------
// A broad node with empty leads_to is one of the 16 top-level families
// (Fibonacci-distributed, in alphabetical-slug order for a stable, arbitrary
// — and declared-arbitrary — assignment). Every other broad node's direction
// is the normalized average of its direct leads_to parents' directions,
// resolved recursively. This is exactly the rule §3.1 states for the one
// broad node with two top-level ancestors ("the normalized midpoint of its
// parents' directions") — applied uniformly, so that case falls out for
// free instead of needing a special branch.
function resolveBroadDirections(broadRaw) {
  const slugs = Object.keys(broadRaw);
  const topLevel = slugs.filter((s) => !(broadRaw[s].leads_to || []).length).sort();
  const famDirs = fibonacciSphere(topLevel.length);
  const familyDirection = new Map(topLevel.map((s, i) => [s, famDirs[i]]));
  const families = topLevel.map((slug, i) => ({
    slug, title: broadRaw[slug].title, kind: broadRaw[slug].kind, direction: famDirs[i],
  }));

  const direction = new Map();     // slug -> {x,y,z}
  const topAncestors = new Map();  // slug -> Set(topLevelSlug)
  const nearestTop = new Map();    // slug -> single topLevelSlug (LOD tie-break, see below)

  function resolve(slug, visiting) {
    if (direction.has(slug)) return;
    if (familyDirection.has(slug)) {
      direction.set(slug, familyDirection.get(slug));
      topAncestors.set(slug, new Set([slug]));
      nearestTop.set(slug, slug);
      return;
    }
    if (visiting.has(slug)) return; // cycle guard; leads-to is acyclic per SCHEMA §6.5
    visiting.add(slug);
    const parents = (broadRaw[slug]?.leads_to || []).filter((t) => broadRaw[t]);
    for (const p of parents) resolve(p, visiting);
    const dirs = parents.map((p) => direction.get(p)).filter(Boolean);
    if (dirs.length) {
      direction.set(slug, vAvgNorm(dirs));
      const anc = new Set();
      let minDist = Infinity, nearest = null;
      for (const p of parents) {
        for (const a of (topAncestors.get(p) || [])) anc.add(a);
      }
      // deterministic single-bucket LOD tie-break for the (rare) multi-parent
      // case: lexicographically smallest ancestor slug. Cosmetic only — the
      // node's real *rendered position* still uses the full averaged
      // direction above; this is only which single dot it collapses to at
      // the coarsest zoom level.
      nearest = [...anc].sort()[0];
      topAncestors.set(slug, anc);
      nearestTop.set(slug, nearest);
    }
    visiting.delete(slug);
  }
  for (const slug of slugs) resolve(slug, new Set());

  return { families, direction, topAncestors, nearestTop, topLevelSet: new Set(topLevel) };
}

// ---------------------------------------------------------------------------
// 2. SLICE FAMILY — direct via `cons`, then inherited via the local
//    same-paper `gen`/`up` ladder (RULE 1).
// ---------------------------------------------------------------------------
// Direction propagates *forward* along the authored ground->derived edges
// (the same orientation CONCEPT §4 gives leads-to): a slice grounded in a
// family-classified floor/claim is, by construction, built on that family —
// this is the same axis the sphere's radius already walks (floor -> apex),
// so inheritance flows the same direction. A slice with two DIRECT `cons`
// entries (13 in the current library) gets the normalized midpoint of both,
// same treatment as the one multi-parent broad node above.
function resolveSliceFamilies(papers, broadDir) {
  const direct = new Map();      // key -> Set(slug)   (before averaging)
  const direction = new Map();   // key -> {x,y,z}
  const source = new Map();      // key -> 'direct' | 'inherited'
  const broadFor = new Map();    // key -> slug (nearest, for LOD level-2 merge)

  for (const [pkey, paper] of Object.entries(papers)) {
    const idsInPaper = new Set(paper.slices.map((s) => s.id));
    for (const c of (paper.cons || [])) {
      if (!idsInPaper.has(c.via) || !broadDir.direction.has(c.slug)) continue;
      const key = sliceKey(pkey, c.via);
      if (!direct.has(key)) direct.set(key, new Set());
      direct.get(key).add(c.slug);
    }
  }
  for (const [key, slugs] of direct) {
    const dirs = [...slugs].map((s) => broadDir.direction.get(s));
    direction.set(key, vAvgNorm(dirs));
    source.set(key, 'direct');
    broadFor.set(key, [...slugs].sort()[0]);
  }

  // Inheritance: forward BFS from each directly-anchored slice, walking the
  // paper-local ground->derived graph built from `up` (u -> s) and `gen`
  // (s -> g). First assignment wins — anchors are processed in a fixed,
  // deterministic (sorted) order, so re-runs are stable. This is a
  // deliberate simplification versus the broad-ladder's midpoint handling:
  // the design doc singles out exactly one broad node as needing a blended
  // direction; it gives no such instruction for inherited slices, so no
  // blending is invented here — just a stable, documented tie-break.
  for (const [pkey, paper] of Object.entries(papers)) {
    const idsInPaper = new Set(paper.slices.map((s) => s.id));
    const succ = new Map();
    const add = (a, b) => { if (!succ.has(a)) succ.set(a, []); succ.get(a).push(b); };
    for (const s of paper.slices) {
      for (const u of (s.up || [])) if (idsInPaper.has(u)) add(u, s.id);
      for (const g of (s.gen || [])) if (idsInPaper.has(g)) add(s.id, g);
    }
    const anchors = [...idsInPaper].filter((id) => direct.has(sliceKey(pkey, id))).sort();
    for (const a of anchors) {
      const aKey = sliceKey(pkey, a);
      const stack = [a];
      const seen = new Set([a]);
      while (stack.length) {
        const u = stack.pop();
        for (const v of (succ.get(u) || [])) {
          if (seen.has(v)) continue;
          seen.add(v);
          stack.push(v);
          const vKey = sliceKey(pkey, v);
          if (!direction.has(vKey)) {
            direction.set(vKey, direction.get(aKey));
            source.set(vKey, 'inherited');
            broadFor.set(vKey, broadFor.get(aKey));
          }
        }
      }
    }
  }

  return { direction, source, broadFor, directCount: direct.size };
}

// ---------------------------------------------------------------------------
// 3. RADIUS — distance-to-floor, ONE unified multi-source BFS across slices
//    AND broad nodes together (up/gen/cons/ladder/cite edges). This is the
//    exact ranking the flat claim-graph prototype already built and
//    verified against graph.json's own `grounded` field (see its verify.py);
//    reused here rather than re-invented, because it already gives broad
//    nodes a radius on the SAME scale as slices for free — the "ladder
//    tier" §3.1 mentions for broad nodes falls out of it directly instead
//    of needing a second, incompatible metric.
// ---------------------------------------------------------------------------
function computeRank(papers, broadRaw) {
  const floors = new Set();
  const adj = new Map();
  const add = (a, b) => { if (!adj.has(a)) adj.set(a, []); adj.get(a).push(b); };
  const allSliceKeys = [];
  const allBroadKeys = Object.keys(broadRaw).map(broadKey);

  for (const [pkey, paper] of Object.entries(papers)) {
    const idsInPaper = new Set(paper.slices.map((s) => s.id));
    for (const s of paper.slices) {
      const key = sliceKey(pkey, s.id);
      allSliceKeys.push(key);
      if (s.is_floor) floors.add(key);
    }
    for (const s of paper.slices) {
      const key = sliceKey(pkey, s.id);
      for (const u of (s.up || [])) if (idsInPaper.has(u)) add(sliceKey(pkey, u), key);
      for (const g of (s.gen || [])) if (idsInPaper.has(g)) add(key, sliceKey(pkey, g));
    }
    for (const c of (paper.cons || [])) {
      if (idsInPaper.has(c.via) && broadRaw[c.slug]) add(sliceKey(pkey, c.via), broadKey(c.slug));
    }
    for (const g of (paper.grounds || [])) {
      if (g.tid && idsInPaper.has(g.via) && papers[g.key]) {
        const srcIds = new Set(papers[g.key].slices.map((s) => s.id));
        if (srcIds.has(g.tid)) add(sliceKey(g.key, g.tid), sliceKey(pkey, g.via));
      }
    }
  }
  for (const [slug, b] of Object.entries(broadRaw)) {
    for (const t of (b.leads_to || [])) if (broadRaw[t]) add(broadKey(slug), broadKey(t));
  }

  const rank = new Map();
  const q = [];
  for (const f of floors) { rank.set(f, 0); q.push(f); }
  let head = 0;
  while (head < q.length) {
    const u = q[head++];
    for (const v of (adj.get(u) || [])) {
      if (!rank.has(v)) { rank.set(v, rank.get(u) + 1); q.push(v); }
    }
  }
  const maxRank = Math.max(0, ...[...rank.values()]);
  return { rank, maxRank, allSliceKeys, allBroadKeys, floors };
}

// ---------------------------------------------------------------------------
// 4. EDGES — same authored set the flat claim-graph draws (§3 of the doc):
//    up, gen, cons, ladder, cite (sharpened grounds), lateral.
// ---------------------------------------------------------------------------
function buildEdges(papers, broadRaw) {
  const edges = { up: [], gen: [], cons: [], ladder: [], cite: [], lateral: [] };
  for (const [pkey, paper] of Object.entries(papers)) {
    const idsInPaper = new Set(paper.slices.map((s) => s.id));
    for (const s of paper.slices) {
      const key = sliceKey(pkey, s.id);
      for (const u of (s.up || [])) if (idsInPaper.has(u)) edges.up.push({ from: sliceKey(pkey, u), to: key });
      for (const g of (s.gen || [])) if (idsInPaper.has(g)) edges.gen.push({ from: key, to: sliceKey(pkey, g) });
    }
    for (const c of (paper.cons || [])) {
      if (idsInPaper.has(c.via) && broadRaw[c.slug]) edges.cons.push({ from: sliceKey(pkey, c.via), to: broadKey(c.slug) });
    }
    for (const g of (paper.grounds || [])) {
      if (g.tid && idsInPaper.has(g.via) && papers[g.key]) {
        const srcIds = new Set(papers[g.key].slices.map((s) => s.id));
        if (srcIds.has(g.tid)) edges.cite.push({ from: sliceKey(g.key, g.tid), to: sliceKey(pkey, g.via) });
      }
    }
    for (const l of (paper.lateral || [])) {
      if (!idsInPaper.has(l.via)) continue;
      const from = sliceKey(pkey, l.via);
      if (l.tid && papers[l.key]) {
        const srcIds = new Set(papers[l.key].slices.map((s) => s.id));
        if (srcIds.has(l.tid)) edges.lateral.push({ a: from, b: sliceKey(l.key, l.tid), sign: l.sign });
      } else if (l.slug && broadRaw[l.slug]) {
        edges.lateral.push({ a: from, b: broadKey(l.slug), sign: l.sign });
      }
    }
  }
  for (const [slug, b] of Object.entries(broadRaw)) {
    for (const t of (b.leads_to || [])) if (broadRaw[t]) edges.ladder.push({ from: broadKey(slug), to: broadKey(t) });
  }
  return edges;
}

// ---------------------------------------------------------------------------
// 5. POSITION — direction * radius(rank), or halo placement.
// ---------------------------------------------------------------------------
export const GEOM = {
  OUTER_R: 12,     // floors (rank 0) sit here — the shell's outer surface
  INNER_R: 1.6,    // apex region — nonzero so the top-tier families/roots don't collide at a point
  HALO_MIN: 13.8,  // just outside OUTER_R
  HALO_MAX: 23,    // diffuse outward — deliberately wide, see report: the halo outnumbers the ball
};

function radiusForRank(rank, maxRank) {
  if (maxRank <= 0) return GEOM.OUTER_R;
  const t = rank / maxRank;
  return GEOM.OUTER_R - (GEOM.OUTER_R - GEOM.INNER_R) * t;
}

// Within-shell / within-halo placement: NOT a physics simulation. A
// deterministic sunflower-spiral offset on the tangent plane at the node's
// direction, scaled by its rank within a (direction-bucket, radius) cohort.
// §3.1 is explicit that this placement is "force-packed to avoid overlap"
// and "meaningless by construction" — this produces the same qualitative
// effect (no exact overlaps, roughly even packing) without pretending to
// be a real force layout. The UI must label it as meaningless; see index.html.
function packOffset(direction, indexInCohort, cohortSize, jitterScale) {
  if (cohortSize <= 1) return { x: 0, y: 0, z: 0 };
  // any vector not parallel to direction, to build a tangent frame
  const ref = Math.abs(direction.y) < 0.99 ? { x: 0, y: 1, z: 0 } : { x: 1, y: 0, z: 0 };
  const tx = vNorm({
    x: direction.y * ref.z - direction.z * ref.y,
    y: direction.z * ref.x - direction.x * ref.z,
    z: direction.x * ref.y - direction.y * ref.x,
  });
  const ty = {
    x: direction.y * tx.z - direction.z * tx.y,
    y: direction.z * tx.x - direction.x * tx.z,
    z: direction.x * tx.y - direction.y * tx.x,
  };
  const golden = Math.PI * (3 - Math.sqrt(5));
  const rr = Math.sqrt((indexInCohort + 0.5) / cohortSize) * jitterScale;
  const th = golden * indexInCohort;
  const ox = Math.cos(th) * rr, oy = Math.sin(th) * rr;
  return { x: tx.x * ox + ty.x * oy, y: tx.y * ox + ty.y * oy, z: tx.z * ox + ty.z * oy };
}

// ---------------------------------------------------------------------------
// MAIN — buildModel(raw graph.json) -> the fully positioned model.
// ---------------------------------------------------------------------------
export function buildModel(raw) {
  const papers = raw.papers || {};
  const broadRaw = raw.broad || {};

  const broadDir = resolveBroadDirections(broadRaw);
  const sliceFam = resolveSliceFamilies(papers, broadDir);
  const rankInfo = computeRank(papers, broadRaw);
  const edges = buildEdges(papers, broadRaw);

  // ---- broad nodes -------------------------------------------------------
  const broad = new Map();
  const cohorts = new Map(); // "dirHash|rank" -> keys[], for packing
  for (const [slug, b] of Object.entries(broadRaw)) {
    const key = broadKey(slug);
    const direction = broadDir.direction.get(slug) || null;
    const rank = rankInfo.rank.has(key) ? rankInfo.rank.get(key) : null;
    const inHalo = direction === null || rank === null;
    broad.set(key, {
      key, kind: 'broad', slug, broadKind: b.kind, title: b.title, text: b.text, meter: b.meter,
      isTopLevel: broadDir.topLevelSet.has(slug),
      direction, rank, inHalo,
      nearestTopSlug: broadDir.nearestTop.get(slug) || null,
    });
    if (!inHalo) {
      const ck = `${Math.round(direction.x * 40)}_${Math.round(direction.y * 40)}_${Math.round(direction.z * 40)}|${rank}`;
      if (!cohorts.has(ck)) cohorts.set(ck, []);
      cohorts.get(ck).push(key);
    }
  }

  // ---- slices --------------------------------------------------------------
  const slices = new Map();
  for (const [pkey, paper] of Object.entries(papers)) {
    for (const s of paper.slices) {
      const key = sliceKey(pkey, s.id);
      const direction = sliceFam.direction.get(key) || null;
      const rank = rankInfo.rank.has(key) ? rankInfo.rank.get(key) : null;
      const inHalo = direction === null || rank === null;
      slices.set(key, {
        key, kind: 'slice', paper: pkey, paperTitle: paper.title, paperYear: paper.year, paperType: paper.type,
        id: s.id, sliceKind: s.kind, text: s.text, quote: s.quote, color: s.color,
        is_floor: s.is_floor, grounded: s.grounded, borrowed: s.borrowed, answered: s.answered,
        answers: s.answers || [],
        direction, rank, inHalo,
        familySource: sliceFam.source.get(key) || null,
        broadSlug: sliceFam.broadFor.get(key) || null,
      });
      if (!inHalo) {
        const ck = `${Math.round(direction.x * 40)}_${Math.round(direction.y * 40)}_${Math.round(direction.z * 40)}|${rank}`;
        if (!cohorts.has(ck)) cohorts.set(ck, []);
        cohorts.get(ck).push(key);
      }
    }
  }

  // ---- positions: shell (packed) + halo (jittered outward) ---------------
  const position = new Map();
  for (const [, keys] of cohorts) {
    keys.sort(); // deterministic order within a cohort
    keys.forEach((key, i) => {
      const node = slices.has(key) ? slices.get(key) : broad.get(key);
      const baseR = radiusForRank(node.rank, rankInfo.maxRank);
      const off = packOffset(node.direction, i, keys.length, Math.min(1.6, 0.35 + 0.06 * Math.sqrt(keys.length)));
      const base = vScale(node.direction, baseR);
      position.set(key, vAdd(base, off));
    });
  }
  const allNodes = new Map([...slices, ...broad]);
  for (const [key, node] of allNodes) {
    if (position.has(key)) continue;
    // halo placement: angularly correct if direction is known, otherwise a
    // deterministic pseudo-random direction — never meant to carry
    // meaning, purely so the halo reads as a diffuse cloud rather than a
    // single point. Radius is likewise jittered within [HALO_MIN,HALO_MAX].
    const dir = node.direction || (() => {
      const u = hash01(key + '|u') * 2 - 1;
      const t = hash01(key + '|t') * Math.PI * 2;
      const r = Math.sqrt(Math.max(0, 1 - u * u));
      return { x: r * Math.cos(t), y: u, z: r * Math.sin(t) };
    })();
    const rr = GEOM.HALO_MIN + hash01(key + '|r') * (GEOM.HALO_MAX - GEOM.HALO_MIN);
    // small tangential jitter too, so nodes sharing a direction don't ray out along one line
    const jt = hash01(key + '|jt') * Math.PI * 2;
    const jr = hash01(key + '|jr') * 1.2;
    const off = packOffset(dir, jt, Math.PI * 2, jr); // reuse packOffset's tangent-frame math loosely
    position.set(key, vAdd(vScale(dir, rr), off));
  }

  return {
    slices, broad, edges, position,
    families: broadDir.families,
    maxRank: rankInfo.maxRank,
    floors: rankInfo.floors,
    stats: {
      nSlices: slices.size,
      nBroad: broad.size,
      nTopLevelFamilies: broadDir.families.length,
      nDirectFamily: sliceFam.directCount,
      nWithFamily: [...slices.values()].filter((s) => s.direction !== null).length,
      nRankedSlices: [...slices.values()].filter((s) => s.rank !== null).length,
      nHaloSlices: [...slices.values()].filter((s) => s.inHalo).length,
      nHaloBroad: [...broad.values()].filter((b) => b.inHalo).length,
      nMultiTopBroad: [...broadDir.topAncestors.values()].filter((s) => s.size > 1).length,
    },
  };
}

export { sliceKey, broadKey };
