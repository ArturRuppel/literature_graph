#!/usr/bin/env python3
"""Throwaway verification script — NOT part of the shipped prototype.

Checks the claim-map data model against dist/graph.json numerically, before any
rendering code is trusted. The map places the 44 broad *claims* (not the papers)
on two axes, so every derived quantity that decides where a mark lands or how
big it is gets checked here first.

What it establishes, in order:

  - **membership** — which curated papers attach to a claim, as the union of the
    ladder (`paper.cons[].slug`) and the signed axis (`paper.lateral[]`), so a
    paper that only contradicts a claim still counts as being in the
    conversation about it. Programme aims (`type: aim`) are excluded: an aim is
    a proposal, not evidence, and counting one would put the lab's own grant
    into the support meter.
  - **x, the year spread** — min / p25 / median / p75 / max over the members'
    publication years, which is what "is this claim live or finished" is read
    off.
  - **y, the ladder altitude** — longest path along `leads_to` between broad
    claims. This is authored, so unlike the topic vote below it needs no
    tie-breaking; the check here is only that the ladder is acyclic and shallow
    enough to use as a lane index.
  - **the rejected topic band** — a claim carries no topic of its own (topics
    are keyword containers over paper `tags`, SCHEMA §9), so banding by topic
    means a plurality vote of its members' topics. This prints the margin of
    that vote, which is why the map does not use it. Kept in the script as the
    evidence for that decision.

It also cross-checks derived membership against the `meter` (s/c) graph.json
already carries. The two count different things — meter counts *slices*,
membership counts *distinct papers* — so they should not be equal, but
`meter.c > 0` must agree with the presence of a contra member.

Usage: python3 verify.py --graph /path/to/graph.json
"""
import argparse
import json
import statistics
from collections import Counter


def quantile(sorted_vals, q):
    """Linear-interpolated quantile; stdlib `quantiles` refuses n < 2."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    args = ap.parse_args()

    with open(args.graph) as f:
        d = json.load(f)

    aims = {k for k, v in d["papers"].items() if v.get("type") == "aim"}
    papers = {k: v for k, v in d["papers"].items()
              if v.get("cur") and k not in aims}
    broad = d["broad"]
    topics = d["topics"]
    claims = {k: v for k, v in broad.items() if v["kind"] == "broad claim"}

    print("=== headline counts ===")
    print(f"curated papers   {len(papers)}   (programme aims excluded: {sorted(aims)})")
    print(f"broad claims     {len(claims)}")
    print(f"papers w/ cons   {sum(1 for p in papers.values() if p.get('cons'))}")
    print(f"papers w/ head   {sum(1 for p in papers.values() if p.get('head'))}")

    # ---- membership: ladder ∪ signed -------------------------------------
    # Stance per (paper, claim): contra beats corro beats neutral, because a
    # paper that both ladders into a claim and contradicts it (the intended
    # encoding — see Bera2026's curation note) is a counterexample, not support.
    members = {s: {} for s in claims}
    for key, p in papers.items():
        for c in p.get("cons", []):
            if c["slug"] in members:
                members[c["slug"]].setdefault(key, "neutral")
        for l in p.get("lateral", []):
            if l.get("slug") in members:
                sign = "contra" if l["sign"] == "contra" else "corro"
                if members[l["slug"]].get(key) != "contra":
                    members[l["slug"]][key] = sign

    sizes = sorted((len(m) for m in members.values()), reverse=True)
    print("\n=== membership (distinct curated papers per claim) ===")
    print(f"total attachments {sum(sizes)}   max {sizes[0]}   median {statistics.median(sizes)}")
    print(f"claims with 0 members: {sum(1 for s in sizes if s == 0)}")
    print(f"claims with 1 member:  {sum(1 for s in sizes if s == 1)}  "
          "(below the >=2 minting floor, CONCEPT 10.2 — expect 0)")

    # ---- meter cross-check ----------------------------------------------
    bad = 0
    for slug, c in claims.items():
        meter = c.get("meter") or {}
        n_contra = sum(1 for st in members[slug].values() if st == "contra")
        if bool(meter.get("c")) != bool(n_contra):
            bad += 1
            print(f"  MISMATCH {slug}: meter.c={meter.get('c')} derived contra={n_contra}")
    print(f"\n=== meter cross-check ===\nclaims where meter.c and derived contra "
          f"disagree on presence: {bad}")

    # ---- second-order dispute: paper -> paper laterals inside one claim ---
    # Only 15 of the 284 signed edges name a broad slug directly; the other 269
    # point at another paper's slice. Those carry polarity about a claim too,
    # whenever both endpoints are members of it — a disagreement *inside* the
    # claim rather than *with* it. Counted separately because it is a second
    # derivation and must not be silently folded into the first.
    # Deduped on an unordered pair: one paper often contradicts several slices
    # of the same other paper, and a disagreement between two papers is one
    # disagreement however many slices carry it, in either direction.
    internal = {s: set() for s in claims}
    for key, p in papers.items():
        for l in p.get("lateral", []):
            tgt = l.get("key")
            if not tgt or tgt == key or l["sign"] != "contra":
                continue          # a paper's lateral onto its own slice is not a dispute
            for slug, m in members.items():
                if key in m and tgt in m:
                    internal[slug].add(tuple(sorted((key, tgt))))
    print("\n=== second-order dispute (paper contra paper, both in the claim) ===")
    print("signed edges naming a broad slug directly:  "
          f"{sum(1 for p in papers.values() for l in p.get('lateral', []) if l.get('slug'))}")
    print("signed edges naming another paper's slice:  "
          f"{sum(1 for p in papers.values() for l in p.get('lateral', []) if l.get('key'))}")
    print(f"claims carrying at least one internal contra pair: "
          f"{sum(1 for v in internal.values() if v)} / {len(claims)}")
    for slug in sorted(internal, key=lambda s: -len(internal[s]))[:6]:
        if internal[slug]:
            print(f"  {len(internal[slug]):2d} pairs  {slug}")

    # ---- y: the ladder altitude -----------------------------------------
    # `leads_to` means "generalizes into", so a claim with no leads_to is an
    # apex. Altitude below is distance *up* to the furthest apex, i.e. 0 = apex.
    # Longest path, not shortest: a claim that generalizes two ways should sit
    # at the rung its deepest reading puts it on, so no edge ever points down.
    def altitude(slug, seen=frozenset()):
        up = [x for x in claims[slug].get("leads_to", []) if x in claims]
        if not up or slug in seen:
            return 0
        return 1 + max(altitude(x, seen | {slug}) for x in up)

    alt = {s: altitude(s) for s in claims}
    print("\n=== y axis: ladder altitude (0 = apex, no leads_to) ===")
    print(f"rung sizes: {dict(sorted(Counter(alt.values()).items()))}")
    print(f"apex claims: {sum(1 for v in alt.values() if v == 0)}")

    # every ladder edge must point strictly upward, or the lane index is a lie
    down = [(s, t) for s in claims for t in claims[s].get("leads_to", [])
            if t in claims and alt[t] >= alt[s]]
    print(f"ladder edges that do not decrease altitude: {len(down)} (expect 0)")
    n_edges = sum(1 for s in claims for t in claims[s].get("leads_to", []) if t in claims)
    print(f"ladder edges drawn: {n_edges}")

    # ---- the rejected topic band ----------------------------------------
    roots = {k for k, v in topics.items() if not v.get("broader")}
    leaves = {k for k in topics if k not in roots}
    paper_topics = {}
    for t, tv in topics.items():
        for pk in tv.get("papers", []):
            paper_topics.setdefault(pk, set()).add(t)
    methods_sub = {k for k in leaves
                   if "methods-and-measurement" in (topics[k].get("broader") or [])}
    print("\n=== rejected: the topic band ===")
    # Both pools are printed because dropping the methods subtree is the obvious
    # rescue for a near-tie vote, and it needs to be on the record that it does
    # not rescue it.
    for label, pool in (("all leaf topics", leaves),
                        ("subject leaves, methods subtree dropped", leaves - methods_sub)):
        margins, unbanded = [], 0
        for slug in claims:
            votes = Counter()
            for pk in members[slug]:
                for t in paper_topics.get(pk, ()):
                    if t in pool:
                        votes[t] += 1
            if not votes:
                unbanded += 1
                continue
            margins.append(votes.most_common(1)[0][1] / sum(votes.values()))
        margins.sort()
        print(f"  {label} ({len(pool)} lanes) — unbanded {unbanded}; "
              f"plurality share min {margins[0]:.2f} median "
              f"{statistics.median(margins):.2f} max {margins[-1]:.2f}; "
              f"under 40%: {sum(1 for m in margins if m < 0.40)} / {len(margins)}")
    print("  <- why topic is a filter in this view, not an axis")

    # ---- the map's own table --------------------------------------------
    print("\n=== the map, as a table (sorted by weight) ===")
    print(f"{'claim':52s} {'alt':>3s} {'n':>3s} {'ctr':>3s} {'int':>3s}  "
          f"{'min':>4s} {'p25':>6s} {'med':>6s} {'p75':>6s} {'max':>4s}")
    for slug in sorted(claims, key=lambda s: -len(members[s])):
        m = members[slug]
        yrs = sorted(papers[pk]["year"] for pk in m if papers[pk].get("year"))
        n_contra = sum(1 for st in m.values() if st == "contra")
        if not yrs:
            print(f"{slug:52s} {alt[slug]:3d} {len(m):3d} {n_contra:3d} "
                  f"{len(internal[slug]):3d}   (no years)")
            continue
        print(f"{slug:52s} {alt[slug]:3d} {len(m):3d} {n_contra:3d} "
              f"{len(internal[slug]):3d}  {yrs[0]:4d} {quantile(yrs,.25):6.1f} "
              f"{quantile(yrs,.5):6.1f} {quantile(yrs,.75):6.1f} {yrs[-1]:4d}")

    med = {s: quantile(sorted(papers[pk]["year"] for pk in members[s]
                              if papers[pk].get("year")), .5) for s in claims}
    med = {k: v for k, v in med.items() if v is not None}
    print(f"\nmedian-year axis spans {min(med.values()):.1f} … {max(med.values()):.1f}")
    yrs = sorted(p["year"] for p in papers.values() if p.get("year"))
    print(f"corpus year range {yrs[0]} … {yrs[-1]} ({len(yrs)} papers with a year); "
          f"member-year range {min(min(sorted(papers[pk]['year'] for pk in members[s] if papers[pk].get('year')) or [9999]) for s in claims if members[s])} … {yrs[-1]}")


if __name__ == "__main__":
    main()
