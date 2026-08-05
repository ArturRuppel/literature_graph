/* derive-model.js — the claim-sphere coordinate rules, applied to dist/graph.json.
 *
 *   deriveModel(graph) -> { stats, families, nodes, edges }
 *
 * `graph` is a parsed dist/graph.json. Pure: no I/O, no dependencies, no globals.
 * Every coordinate below comes from an authored field. Nothing is inferred, no
 * similarity is computed, and no paper-level majority vote is used — a slice with
 * no authored coordinate is marked halo:true instead of being given one
 * (docs/2026-08-05-additive-graph-views.md §3.1).
 *
 * The five rules the renderer depends on:
 *   1. radius is generality, inverted — distance-to-floor (slices) / ladder tier
 *      (broad), mapped so the top-level entries sit at r≈0.13 and floors at r=1;
 *   2. direction is family — the top-level ancestor of the broad node a slice
 *      `cons` into, Fibonacci-distributed over the sphere (2 DOF, never wedges);
 *   3. inheritance is authored only — through the local gen/up ladder, never a
 *      paper-level vote;
 *   4. no coordinate ⇒ the haze — halo:true, a radius in 1.10–2.05 and a
 *      direction that is explicitly meaningless;
 *   5. within a shell, packing is arbitrary — a deterministic sunflower inside
 *      the family cone. Any deterministic packing is a valid substitute.
 */
export function deriveModel(graph) {
  const P = graph.papers, B = graph.broad;
  const sk = (key, id) => key + '#' + id;

  /* ── nodes ─────────────────────────────────────────────────────────────── */
  const nodes = [], idx = new Map();
  for (const [key, p] of Object.entries(P)) {
    for (const s of (p.slices || [])) {
      idx.set(sk(key, s.id), nodes.length);
      nodes.push({
        t: 's', k: sk(key, s.id), sid: s.id, paper: key, year: p.year, pass: p.pass,
        ptitle: p.title, a1: p.authors && p.authors[0] ? String(p.authors[0][0]).split(',')[0] : '',
        kind: s.kind, text: s.text, quote: s.quote || null, color: s.color,
        floor: !!s.is_floor, grounded: !!s.grounded, borrowed: !!s.borrowed, answered: !!s.answered
      });
    }
  }
  for (const [slug, b] of Object.entries(B)) {
    idx.set('@' + slug, nodes.length);
    nodes.push({ t: 'b', k: '@' + slug, slug, kind: b.kind, title: b.title, text: b.text, meter: b.meter });
  }

  /* ── edges — all authored; direction is always toward the more general ──── */
  const edges = [];
  const E = (a, b, k, extra) => { if (a == null || b == null || a === b) return; edges.push(Object.assign({ a, b, k }, extra || {})); };
  for (const [key, p] of Object.entries(P)) {
    for (const s of (p.slices || [])) {
      const me = idx.get(sk(key, s.id));
      for (const u of (s.up || [])) E(idx.get(sk(key, u)), me, 'up');       // support → claim
      for (const g of (s.gen || [])) E(me, idx.get(sk(key, g)), 'gen');
    }
    for (const c of (p.cons || [])) E(idx.get(sk(key, c.via)), idx.get('@' + c.slug), 'cons');
    for (const g of (p.grounds || [])) if (g.tid) E(idx.get(sk(g.key, g.tid)), idx.get(sk(key, g.via)), 'cite');
    for (const l of (p.lateral || [])) {
      const other = l.tid ? idx.get(sk(l.key, l.tid)) : (l.slug ? idx.get('@' + l.slug) : null);
      E(idx.get(sk(key, l.via)), other, 'lat', { sign: l.sign });
    }
  }
  for (const [slug, b] of Object.entries(B)) for (const t of (b.leads_to || [])) E(idx.get('@' + slug), idx.get('@' + t), 'ladder');

  /* ── rule 1a · distance to floor (slices) ──────────────────────────────── */
  const upA = nodes.map(() => []), dnA = nodes.map(() => []);
  for (const e of edges) {
    if (e.k === 'up' || e.k === 'gen' || e.k === 'cite' || e.k === 'cons' || e.k === 'ladder') {
      upA[e.a].push(e.b); dnA[e.b].push(e.a);
    }
  }
  const dist = nodes.map(() => null);
  let frontier = [];
  nodes.forEach((n, i) => { if (n.floor) { dist[i] = 0; frontier.push(i); } });
  for (let lvl = 1; frontier.length; lvl++) {
    const next = [];
    for (const i of frontier) for (const j of upA[i]) if (dist[j] == null && nodes[j].t === 's') { dist[j] = lvl; next.push(j); }
    frontier = next;
  }
  const maxSlice = Math.max(...dist.filter(v => v != null));

  /* ── rule 1b · ladder tier (broad nodes) ───────────────────────────────── */
  const tops = Object.entries(B).filter(([, b]) => !(b.leads_to || []).length).map(([s]) => s);
  const tier = {}; tops.forEach(s => { tier[s] = 0; });
  let ring = tops.slice();
  for (let t = 1; ring.length; t++) {
    const next = [];
    for (const [slug, b] of Object.entries(B)) {
      if (tier[slug] == null && (b.leads_to || []).some(x => ring.includes(x))) { tier[slug] = t; next.push(slug); }
    }
    ring = next;
  }
  const maxTier = Math.max(...Object.values(tier));

  /* ── rule 2 · family = top-level ancestor, Fibonacci-distributed ───────── */
  const ancestors = slug => {
    const out = new Set();
    const walk = (x, depth) => {
      const l = B[x].leads_to || [];
      if (!l.length || depth > 8) { out.add(x); return; }
      l.forEach(y => walk(y, depth + 1));
    };
    walk(slug, 0);
    return [...out];
  };
  const famIdx = {}; tops.forEach((s, i) => { famIdx[s] = i; });
  const fam = nodes.map(() => null), famSrc = nodes.map(() => null);
  nodes.forEach((n, i) => { if (n.t === 'b') { fam[i] = ancestors(n.slug).map(s => famIdx[s]); famSrc[i] = 'authored'; } });
  for (const e of edges) {
    if (e.k !== 'cons' || !fam[e.b]) continue;
    fam[e.a] = [...new Set([...(fam[e.a] || []), ...fam[e.b]])];
    famSrc[e.a] = 'authored';
  }
  /* rule 3 · inherit only through the local gen/up ladder — never a paper vote */
  for (let pass = 0; pass < 6; pass++) {
    nodes.forEach((n, i) => {
      if (n.t !== 's' || fam[i]) return;
      const got = [...new Set([...upA[i], ...dnA[i]].flatMap(j => fam[j] || []))];
      if (got.length) { fam[i] = got.slice(0, 2); famSrc[i] = 'inherited'; }
    });
  }

  /* ── geometry ──────────────────────────────────────────────────────────── */
  const GA = Math.PI * (3 - Math.sqrt(5));
  const axes = tops.map((_, i) => {
    const y = 1 - (i + 0.5) / tops.length * 2, rr = Math.sqrt(Math.max(0, 1 - y * y)), th = GA * i;
    return [Math.cos(th) * rr, y, Math.sin(th) * rr];
  });
  const norm = v => { const m = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / m, v[1] / m, v[2] / m]; };
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const RMIN = 0.13, gmax = (maxSlice + 1) + maxTier;

  /* rule 5 · within-shell packing: deterministic sunflower inside the family cone.
     Meaningless by construction — any deterministic packing is a valid substitute. */
  const shellCount = {}, shellSeen = {}, shellKey = [];
  nodes.forEach((n, i) => {
    const k = (n.t === 'b' ? 'b' + tier[n.slug] : 's' + dist[i]) + '|' + (fam[i] ? fam[i].join(',') : 'halo');
    shellKey[i] = k; shellCount[k] = (shellCount[k] || 0) + 1;
  });
  let haloTotal = 0;
  nodes.forEach((n, i) => { if (n.t === 's' && (dist[i] == null || !fam[i])) haloTotal++; });
  let haloSeen = 0;

  nodes.forEach((n, i) => {
    const halo = n.t === 's' && (dist[i] == null || !fam[i]);   // rule 4
    n.lvl = n.t === 'b' ? tier[n.slug] : dist[i];
    n.fam = fam[i]; n.famSrc = famSrc[i]; n.halo = halo;
    let dir, R;
    if (halo) {
      const y = 1 - (haloSeen + 0.5) / haloTotal * 2, rr = Math.sqrt(Math.max(0, 1 - y * y)), th = GA * haloSeen;
      haloSeen++;
      dir = [Math.cos(th) * rr, y, Math.sin(th) * rr];
      R = 1.22 + (Math.sin(i * 127.1) * 0.5 + 0.5) * 0.42;      // radius is explicitly arbitrary
    } else {
      const g = n.t === 'b' ? (maxSlice + 1) + (maxTier - tier[n.slug]) : dist[i];
      R = RMIN + (1 - g / gmax) * (1 - RMIN);                   // rule 1: apex inside, floors out
      const ax = norm(fam[i].reduce((acc, k) => [acc[0] + axes[k][0], acc[1] + axes[k][1], acc[2] + axes[k][2]], [0, 0, 0]));
      const cnt = shellCount[shellKey[i]];
      const j = shellSeen[shellKey[i]] = (shellSeen[shellKey[i]] || 0);
      shellSeen[shellKey[i]] = j + 1;
      const spread = cnt > 1 ? 0.46 : 0;
      const u = Math.sqrt((j + 0.35) / Math.max(cnt, 1)) * spread, th = GA * j * 7 + i * 0.7;
      const e1 = norm(cross(ax, Math.abs(ax[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0]));
      const e2 = norm(cross(ax, e1));
      dir = norm(ax.map((v, k) => v * Math.cos(u) + (e1[k] * Math.cos(th) + e2[k] * Math.sin(th)) * Math.sin(u)));
    }
    n.r = +R.toFixed(4);
    n.x = +(dir[0] * R).toFixed(4); n.y = +(dir[1] * R).toFixed(4); n.z = +(dir[2] * R).toFixed(4);
  });

  const stats = {
    slices: nodes.filter(n => n.t === 's').length,
    broad: nodes.filter(n => n.t === 'b').length,
    papers: Object.keys(P).length, stubs: Object.keys(graph.stubs || {}).length,
    floors: nodes.filter(n => n.floor).length,
    ranked: nodes.filter(n => n.t === 's' && n.lvl != null).length,
    unfloored: nodes.filter(n => n.t === 's' && n.lvl == null).length,
    famAuthored: nodes.filter(n => n.t === 's' && n.famSrc === 'authored').length,
    famInherited: nodes.filter(n => n.t === 's' && n.famSrc === 'inherited').length,
    halo: nodes.filter(n => n.halo).length,
    families: tops.length, maxSlice, maxTier,
    edges: edges.reduce((a, e) => (a[e.k] = (a[e.k] || 0) + 1, a), {})
  };
  const families = tops.map((slug, i) => ({
    slug, title: B[slug].title, kind: B[slug].kind,
    axis: axes[i].map(v => +v.toFixed(4)),
    members: nodes.filter(n => n.fam && n.fam.includes(i)).length
  }));

  return { stats, families, nodes, edges };
}
