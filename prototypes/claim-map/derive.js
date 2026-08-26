/* derive.js — graph.json to the map's model, and nothing else.
 *
 * Pure: no DOM, no I/O, no dependencies, so map-view.js and the headless
 * check in verify_headless.mjs read the same numbers. Every quantity here has
 * a counterpart in verify.py, which was run against the real library first;
 * if the two ever disagree, verify.py is right and this file is the bug.
 *
 *   buildModel(graph) -> { claims, rungs, yearExtent, topics, stats }
 *
 * Three rules govern what is computed:
 *
 * 1. **A programme aim is not evidence.** `graph.papers` carries the
 *    programme's aims alongside the literature (`type: "aim"`, `@`-prefixed
 *    key). They are dropped everywhere below: counting one would put the lab's
 *    own proposal into a claim's support meter, which is the one number that
 *    must only ever come from other people's papers.
 *
 * 2. **Altitude is authored; the topic band was not.** The y axis is the
 *    `leads_to` ladder between broad claims — an authored edge, so a claim's
 *    rung needs no tie-breaking. Banding by topic was tried and rejected: a
 *    claim has no topic of its own, so the band would be a plurality vote of
 *    its members' topics, and that vote is a near-tie for 38 of 42 claims
 *    (verify.py prints the margin). Topic survives here as a filter, which is
 *    a use that does not require picking a winner.
 *
 * 3. **The two kinds of dispute stay apart.** A paper can contradict the claim
 *    itself (`lateral[].slug`, 14 in the library) or contradict another paper
 *    that sits under the same claim (`lateral[].key`, the far commoner case).
 *    The first disputes the claim, the second is a disagreement inside it.
 *    They are counted separately and never summed.
 */

/** Linear-interpolated quantile over an ascending array. */
export function quantile(sorted, q) {
  if (!sorted.length) return null;
  if (sorted.length === 1) return sorted[0];
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export function buildModel(graph) {
  // ---- 1. the paper pool (rule 1) --------------------------------------
  const papers = {};
  for (const [key, p] of Object.entries(graph.papers)) {
    if (p.cur && p.type !== 'aim') papers[key] = p;
  }

  const claimNodes = {};
  for (const [slug, b] of Object.entries(graph.broad)) {
    if (b.kind === 'broad claim') claimNodes[slug] = b;
  }

  // ---- 2. membership: the ladder union the signed axis ------------------
  // Stance per (paper, claim): contra beats corro beats neutral. A paper that
  // both ladders into a claim and contradicts it is the intended encoding of a
  // counterexample (polarity is derived, SCHEMA §7), so the sign must win over
  // the mere presence of the ladder edge.
  const members = {};
  for (const slug of Object.keys(claimNodes)) members[slug] = new Map();
  for (const [key, p] of Object.entries(papers)) {
    for (const c of p.cons || []) {
      if (members[c.slug] && !members[c.slug].has(key)) members[c.slug].set(key, 'neutral');
    }
    for (const l of p.lateral || []) {
      if (!l.slug || !members[l.slug]) continue;
      const sign = l.sign === 'contra' ? 'contra' : 'corro';
      if (members[l.slug].get(key) !== 'contra') members[l.slug].set(key, sign);
    }
  }

  // ---- 3. dispute inside a claim (rule 3) -------------------------------
  // Deduped on an unordered pair key: one paper often contradicts several
  // slices of the same other paper, and a disagreement between two papers is
  // one disagreement however many slices carry it, in either direction.
  const internalSet = {};
  for (const slug of Object.keys(claimNodes)) internalSet[slug] = new Map();
  for (const [key, p] of Object.entries(papers)) {
    for (const l of p.lateral || []) {
      // a paper's lateral onto one of its own slices is an internal argument,
      // not a dispute between papers, so it never counts here
      if (!l.key || l.key === key || l.sign !== 'contra' || !papers[l.key]) continue;
      const pair = [key, l.key].sort();
      for (const [slug, m] of Object.entries(members)) {
        if (m.has(key) && m.has(l.key)) internalSet[slug].set(pair.join('\u0000'), pair);
      }
    }
  }
  const internal = Object.fromEntries(
    Object.entries(internalSet).map(([slug, m]) => [slug, [...m.values()]]));

  // ---- 4. altitude (rule 2) --------------------------------------------
  // `leads_to` means "generalizes into", so a claim with no leads_to is an
  // apex and sits at 0. Longest path rather than shortest: a claim that
  // generalizes two ways belongs on the rung its deepest reading puts it on,
  // which is what keeps every drawn ladder edge pointing upward.
  const altMemo = new Map();
  const altitude = (slug, seen = new Set()) => {
    if (altMemo.has(slug)) return altMemo.get(slug);
    const up = (claimNodes[slug].leads_to || []).filter((t) => claimNodes[t]);
    let v = 0;
    if (up.length && !seen.has(slug)) {
      const next = new Set(seen).add(slug);
      v = 1 + Math.max(...up.map((t) => altitude(t, next)));
    }
    if (!seen.size) altMemo.set(slug, v);
    return v;
  };

  // ---- 5. topic membership, for the filter ------------------------------
  const paperTopics = {};
  for (const [t, tv] of Object.entries(graph.topics || {})) {
    for (const pk of tv.papers || []) (paperTopics[pk] ||= new Set()).add(t);
  }

  // ---- 6. assemble ------------------------------------------------------
  const claims = Object.entries(claimNodes).map(([slug, node]) => {
    const m = members[slug];
    const memberList = [...m.entries()]
      .map(([key, stance]) => ({
        key, stance, year: papers[key].year ?? null,
        title: papers[key].title || key,
        head: (papers[key].head || [])[0] || null,
      }))
      .sort((a, b) => (a.year ?? 0) - (b.year ?? 0));
    const years = memberList.map((x) => x.year).filter((y) => y != null).sort((a, b) => a - b);

    const topicVotes = {};
    for (const { key } of memberList) {
      for (const t of paperTopics[key] || []) topicVotes[t] = (topicVotes[t] || 0) + 1;
    }

    const contra = memberList.filter((x) => x.stance === 'contra').length;
    return {
      slug,
      title: node.title || slug,
      text: node.text || '',
      meter: node.meter || { s: 0, c: 0 },
      leads_to: (node.leads_to || []).filter((t) => claimNodes[t]),
      alt: altitude(slug),
      members: memberList,
      n: memberList.length,
      contra,
      internal: internal[slug],
      topics: Object.entries(topicVotes).sort((a, b) => b[1] - a[1]),
      // x and the whiskers. `med` is the position; the bars are the spread the
      // position is a summary of, drawn so the summary cannot be read as a
      // point measurement.
      years,
      min: years.length ? years[0] : null,
      p25: quantile(years, 0.25),
      med: quantile(years, 0.5),
      p75: quantile(years, 0.75),
      max: years.length ? years[years.length - 1] : null,
    };
  });

  const rungs = [...new Set(claims.map((c) => c.alt))].sort((a, b) => a - b);
  const allYears = claims.flatMap((c) => c.years);

  return {
    claims,
    rungs,
    yearExtent: [Math.min(...allYears), Math.max(...allYears)],
    medExtent: [
      Math.min(...claims.map((c) => c.med)),
      Math.max(...claims.map((c) => c.med)),
    ],
    topics: Object.fromEntries(
      Object.entries(graph.topics || {}).map(([k, v]) => [k, v.title || k]),
    ),
    paperTopics,
    stats: {
      papers: Object.keys(papers).length,
      claims: claims.length,
      attachments: claims.reduce((a, c) => a + c.n, 0),
      ladderEdges: claims.reduce((a, c) => a + c.leads_to.length, 0),
      disputed: claims.filter((c) => c.contra || c.internal.length).length,
      aimsExcluded: Object.entries(graph.papers)
        .filter(([, p]) => p.type === 'aim').map(([k]) => k),
    },
  };
}
