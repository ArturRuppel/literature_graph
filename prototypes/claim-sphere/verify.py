#!/usr/bin/env python3
"""Throwaway verification script — NOT part of the shipped prototype.

Independent, from-scratch numeric check of the claim-sphere data model
against dist/graph.json, BEFORE trusting model.js's own numbers:

  - the 16 top-level families (broad nodes with empty leads_to)
  - slices with an authored family direction: direct via `cons`, then via
    forward propagation along the local paper `gen`/`up` ladder (RULE 1 —
    see model.js's own comment for why this is forward-only, not undirected)
  - the one broad node with two distinct top-level ancestors
  - the unified distance-to-floor BFS (slices AND broad nodes together,
    walking up/gen/cons/ladder/cite) — reused verbatim from
    prototypes/claim-graph/verify.py, already cross-checked there against
    graph.json's own `grounded` field
  - shell population per radius (rank) band, and broad-node count per family

This is a Python re-derivation, independent of model.js, so a match between
the two is a real cross-check and not just "the same bug twice".

Usage: python3 verify.py --graph /path/to/graph.json
"""
import argparse
import json
from collections import Counter, deque


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    args = ap.parse_args()

    with open(args.graph) as f:
        d = json.load(f)

    papers = d["papers"]
    broad = d["broad"]

    # ---- 1. top-level families ---------------------------------------------
    top_level = sorted(s for s, b in broad.items() if not b.get("leads_to"))
    print("=== top-level families (broad.leads_to empty) ===")
    print(f"count: {len(top_level)}  (expected 16)")
    for s in top_level:
        print(f"  {s}  ({broad[s]['kind']})")

    # ---- 2. broad node(s) with 2+ distinct top-level ancestors --------------
    def top_ancestors(slug, seen=None):
        if seen is None:
            seen = set()
        if slug in seen:
            return set()
        seen.add(slug)
        lt = broad[slug].get("leads_to", [])
        if not lt:
            return {slug}
        out = set()
        for t in lt:
            if t in broad:
                out |= top_ancestors(t, seen)
        return out

    multi = [(s, top_ancestors(s)) for s in broad if len(top_ancestors(s)) > 1]
    print(f"\n=== broad nodes with >1 top-level ancestor ===")
    print(f"count: {len(multi)}  (expected 1)")
    for s, ta in multi:
        print(f"  {s} -> {sorted(ta)}")

    # ---- 3. slice family coverage: direct (cons) then inherited (gen/up) ---
    family_direct = {}
    for pkey, paper in papers.items():
        slice_ids = {s["id"] for s in paper["slices"]}
        for c in paper.get("cons", []):
            if c["via"] in slice_ids:
                family_direct.setdefault((pkey, c["via"]), set()).add(c["slug"])
    n_direct = len(family_direct)

    has_family = set(family_direct.keys())
    for pkey, paper in papers.items():
        slice_ids = {s["id"] for s in paper["slices"]}
        succ = {}
        for s in paper["slices"]:
            sid = s["id"]
            for u in s.get("up", []):
                if u in slice_ids:
                    succ.setdefault(u, []).append(sid)
            for g in s.get("gen", []):
                if g in slice_ids:
                    succ.setdefault(sid, []).append(g)
        anchors = sorted(sid for sid in slice_ids if (pkey, sid) in family_direct)
        for a in anchors:
            stack, seen = [a], {a}
            while stack:
                u = stack.pop()
                for v in succ.get(u, []):
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
                        has_family.add((pkey, v))
    n_with_family = len(has_family)
    n_total_slices = sum(len(p["slices"]) for p in papers.values())

    print(f"\n=== slice family coverage (RULE 1: cons direct, then gen/up inheritance) ===")
    print(f"direct via cons:              {n_direct}")
    print(f"direct + inherited:           {n_with_family}")
    print(f"no authored family (halo):    {n_total_slices - n_with_family}")
    print(f"total slices:                 {n_total_slices}")

    # ---- 4. unified distance-to-floor BFS (slices + broad together) --------
    floors = set()
    all_slice_nodes = set()
    edges = []
    for pkey, paper in papers.items():
        slice_ids = {s["id"] for s in paper["slices"]}
        for s in paper["slices"]:
            node = ("s", pkey, s["id"])
            all_slice_nodes.add(node)
            if s["is_floor"]:
                floors.add(node)
        for s in paper["slices"]:
            node = ("s", pkey, s["id"])
            for u in s["up"]:
                if u in slice_ids:
                    edges.append((("s", pkey, u), node))
            for g in s["gen"]:
                if g in slice_ids:
                    edges.append((node, ("s", pkey, g)))
        for c in paper["cons"]:
            if c["via"] in slice_ids:
                edges.append((("s", pkey, c["via"]), ("b", c["slug"])))
        for g in paper["grounds"]:
            if g["tid"] and g["key"] in papers:
                src_ids = {s["id"] for s in papers[g["key"]]["slices"]}
                if g["tid"] in src_ids and g["via"] in slice_ids:
                    edges.append((("s", g["key"], g["tid"]), ("s", pkey, g["via"])))
    all_broad_nodes = {("b", s) for s in broad}
    for slug, b in broad.items():
        for t in b.get("leads_to", []):
            if t in broad:
                edges.append((("b", slug), ("b", t)))

    adj = {}
    for a, b_ in edges:
        adj.setdefault(a, []).append(b_)
    rank = {}
    q = deque()
    for f in floors:
        rank[f] = 0
        q.append(f)
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            if v not in rank:
                rank[v] = rank[u] + 1
                q.append(v)

    max_rank = max(rank.values()) if rank else 0
    print(f"\n=== unified distance-to-floor rank (radius basis; max rank {max_rank}) ===")
    hist = Counter(rank[n] for n in all_slice_nodes if n in rank)
    for r in sorted(hist):
        print(f"  slice shell r-rank {r}: {hist[r]} nodes")
    n_unfloored_slices = len(all_slice_nodes) - sum(hist.values())
    print(f"  slices with NO rank (radius-halo): {n_unfloored_slices} / {len(all_slice_nodes)}")

    hist_b = Counter(rank[n] for n in all_broad_nodes if n in rank)
    for r in sorted(hist_b):
        print(f"  broad shell r-rank {r}: {hist_b[r]} nodes")
    n_unfloored_broad = len(all_broad_nodes) - sum(hist_b.values())
    print(f"  broad with NO rank (radius-halo): {n_unfloored_broad} / {len(all_broad_nodes)}")

    # ---- 5. combined in-ball vs halo (direction AND rank both required) ----
    in_ball_slices = sum(
        1
        for pkey, paper in papers.items()
        for s in paper["slices"]
        if (pkey, s["id"]) in has_family and ("s", pkey, s["id"]) in rank
    )
    in_ball_broad = sum(1 for slug in broad if ("b", slug) in rank)  # all 45 have a direction
    total_nodes = n_total_slices + len(broad)
    in_ball = in_ball_slices + in_ball_broad
    print(f"\n=== combined in-ball vs halo (needs BOTH direction and rank) ===")
    print(f"in ball:  {in_ball} / {total_nodes}  ({100 * in_ball / total_nodes:.1f}%)")
    print(f"in halo:  {total_nodes - in_ball} / {total_nodes}  ({100 * (total_nodes - in_ball) / total_nodes:.1f}%)")

    # ---- 6. broad nodes per top-level family --------------------------------
    print(f"\n=== broad node count per top-level family (via nearest single top ancestor) ===")
    nearest_top = {}
    for slug in broad:
        tas = sorted(top_ancestors(slug))
        nearest_top[slug] = tas[0] if tas else None
    per_family = Counter(nearest_top.values())
    for fam in top_level:
        print(f"  {fam}: {per_family.get(fam, 0)}")

    print("\ndone.")


if __name__ == "__main__":
    main()
