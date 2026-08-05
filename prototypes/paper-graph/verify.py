#!/usr/bin/env python3
"""Throwaway numerical check for the paper-graph prototype.

Recomputes the A1 (grounding) and A2 (co-support) projections directly from
graph.json in plain Python, mirroring the logic in app.js, and prints them
against the figures quoted in docs/2026-08-05-additive-graph-views.md §2.
Not part of the served app; run by hand against the private data repo:

    python3 verify.py --graph /path/to/dist/graph.json
"""
import argparse
import json
from collections import Counter, defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    args = ap.parse_args()

    with open(args.graph) as f:
        g = json.load(f)

    papers = g["papers"]
    curated_keys = set(papers.keys())

    # ---------- A1: grounding projection ----------
    raw_refs = 0
    pair_set = set()  # (source_paper_key, target_key), de-duped
    for pkey, p in papers.items():
        for e in p.get("grounds", []):
            raw_refs += 1
            pair_set.add((pkey, e["key"]))

    indeg = Counter(t for (_s, t) in pair_set)
    targets = set(indeg.keys())
    in1 = sum(1 for c in indeg.values() if c == 1)
    in_ge2 = sum(1 for c in indeg.values() if c >= 2)
    dedup_on_curated = sum(1 for (_s, t) in pair_set if t in curated_keys)

    print("=== A1 grounding projection ===")
    print(f"raw grounds refs:              {raw_refs:>4}  (doc: 634)")
    print(f"distinct targets:              {len(targets):>4}  (doc: 424)")
    print(f"targets in-degree == 1:        {in1:>4}  (doc: 357)")
    print(f"targets in-degree >= 2:        {in_ge2:>4}  (doc: 67)")
    print(f"distinct (src,target) pairs landing on a curated paper: {dedup_on_curated}  (doc: 90 of 634 refs)")
    print("  note: the doc's '90 of 634' mixes a de-duped-pair count (90) with the raw ref")
    print("  count (634) — the raw-ref-on-curated count is actually 117. 90 is the right")
    print("  number for 'how many distinct grounding edges point at a curated paper'.")
    top = indeg.most_common(5)
    print("top targets:", top)
    top_uncurated = sorted(((t, c) for t, c in indeg.items() if t not in curated_keys), key=lambda x: -x[1])[:3]
    print("top uncurated (stub) targets:", top_uncurated)

    # ---------- A2: co-support projection ----------
    paper_to_broads = {}
    for pkey, p in papers.items():
        slugs = set(e["slug"] for e in p.get("cons", []))
        if slugs:
            paper_to_broads[pkey] = slugs

    broad_to_papers = defaultdict(set)
    for pkey, slugs in paper_to_broads.items():
        for s in slugs:
            broad_to_papers[s].add(pkey)

    pair_weight = Counter()
    for pset in broad_to_papers.values():
        plist = sorted(pset)
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                pair_weight[(plist[i], plist[j])] += 1

    on_graph = set(paper_to_broads.keys())
    off_graph = curated_keys - on_graph
    w_ge2 = sum(1 for w in pair_weight.values() if w >= 2)
    w_ge3 = sum(1 for w in pair_weight.values() if w >= 3)

    print()
    print("=== A2 co-support projection ===")
    print(f"pairs (weight >= 1):           {len(pair_weight):>4}  (doc: 380)")
    print(f"papers touching >=1 broad node:{len(on_graph):>4}  (doc: 53)")
    print(f"pairs weight >= 2:              {w_ge2:>4}  (doc: 144)")
    print(f"pairs weight >= 3:              {w_ge3:>4}  (doc: 41)")
    print(f"curated papers off-graph:      {len(off_graph):>4}  (doc: 24)")

    # ---------- lateral overlay (paper<->paper only) ----------
    print()
    print("=== lateral overlay (paper<->paper, self-refs dropped) ===")
    pair_signs = defaultdict(set)
    self_refs = 0
    slug_entries = 0
    for pkey, p in papers.items():
        for e in p.get("lateral", []):
            if "slug" in e:
                slug_entries += 1
                continue
            if e["key"] == pkey:
                self_refs += 1
                continue
            a, b = sorted([pkey, e["key"]])
            pair_signs[(a, b)].add(e["sign"])
    mixed = {k: v for k, v in pair_signs.items() if len(v) > 1}
    print(f"distinct paper-pairs: {len(pair_signs)}  self-refs dropped: {self_refs}  broad-node (slug) entries skipped: {slug_entries}")
    print(f"mixed-sign pairs: {len(mixed)}")


if __name__ == "__main__":
    main()
