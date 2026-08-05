#!/usr/bin/env python3
"""Throwaway verification script — NOT part of the shipped prototype.

Checks the claim-graph data model against dist/graph.json numerically,
before any rendering code is trusted:

  - the headline counts from the design doc (papers/slices/broad/edges)
  - builds the same authored-edge graph the page will build (up/gen/cons/
    broad.leads_to/sharpened grounds) and runs a multi-source BFS from all
    floors to get "distance to floor" ranks
  - cross-checks BFS-reachability against the per-slice `grounded` field
    graph.json already carries (they should agree exactly — a mismatch
    would mean the edge model below is wrong, not that the field is)
  - reports the rank histogram and the unfloored-node count for both
    slices and broad nodes

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

    # ---- headline counts -------------------------------------------------
    n_papers = len(papers)
    n_slices = sum(len(p["slices"]) for p in papers.values())
    n_broad = len(broad)
    n_cons = sum(len(p["cons"]) for p in papers.values())
    n_lateral = sum(len(p["lateral"]) for p in papers.values())
    n_grounds = sum(len(p["grounds"]) for p in papers.values())
    n_sharpened = sum(1 for p in papers.values() for g in p["grounds"] if g["tid"])

    print("=== headline counts ===")
    print(f"papers   {n_papers}  (doc: 77)")
    print(f"slices   {n_slices}  (doc: 822)")
    print(f"broad    {n_broad}  (doc: 45)")
    print(f"cons     {n_cons}  (doc: 297)")
    print(f"lateral  {n_lateral}  (doc: 92)")
    print(f"grounds  {n_grounds}  (doc: 634)")
    print(f"  sharpened (tid set)  {n_sharpened}")
    print(f"  wildcard  (tid null) {n_grounds - n_sharpened}")

    n_lat_sharp = sum(
        1
        for p in papers.values()
        for l in p["lateral"]
        if l.get("tid") or "slug" in l
    )
    print(f"lateral sharpened (drawable node->node) {n_lat_sharp} / {n_lateral}")

    # ---- build the authored-edge graph ------------------------------------
    # node ids: ("s", paper_key, slice_id) for slices, ("b", slug) for broad
    floors = set()
    all_slice_nodes = set()
    grounded_field = {}  # node -> bool, read straight off graph.json
    kind_field = {}

    for pkey, paper in papers.items():
        for s in paper["slices"]:
            node = ("s", pkey, s["id"])
            all_slice_nodes.add(node)
            grounded_field[node] = s["grounded"]
            kind_field[node] = s["kind"]
            if s["is_floor"]:
                floors.add(node)

    all_broad_nodes = {("b", slug) for slug in broad}

    edges = []  # (src, dst) meaning src leads_to dst, ground -> derived

    for pkey, paper in papers.items():
        slice_ids = {s["id"] for s in paper["slices"]}
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
                src_slice_ids = {s["id"] for s in papers[g["key"]]["slices"]}
                if g["tid"] in src_slice_ids and g["via"] in slice_ids:
                    edges.append((("s", g["key"], g["tid"]), ("s", pkey, g["via"])))

    for slug, b in broad.items():
        for t in b["leads_to"]:
            if t in broad:
                edges.append((("b", slug), ("b", t)))

    print(f"\ntotal directed leads_to-family edges built: {len(edges)}")

    # ---- multi-source BFS from floors -------------------------------------
    adj = {}
    for src, dst in edges:
        adj.setdefault(src, []).append(dst)

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

    all_nodes = all_slice_nodes | all_broad_nodes
    unfloored_slices = [n for n in all_slice_nodes if n not in rank]
    unfloored_broad = [n for n in all_broad_nodes if n not in rank]

    print("\n=== rank (distance-to-floor) distribution, slices ===")
    hist = Counter(rank[n] for n in all_slice_nodes if n in rank)
    for r in sorted(hist):
        print(f"  rank {r}: {hist[r]}")
    print(f"  UNFLOORED (no path from any floor): {len(unfloored_slices)}")

    print("\n=== rank distribution, broad nodes ===")
    hist_b = Counter(rank[n] for n in all_broad_nodes if n in rank)
    for r in sorted(hist_b):
        print(f"  rank {r}: {hist_b[r]}")
    print(f"  UNFLOORED broad nodes: {len(unfloored_broad)}")
    for n in unfloored_broad:
        print(f"    {n[1]}  ({broad[n[1]]['kind']}) {broad[n[1]]['title']!r}")

    # ---- cross-check against the `grounded` field --------------------------
    mismatches = []
    for n in all_slice_nodes:
        if kind_field[n] not in ("claim",):
            continue  # `grounded` is only meaningful/set for claims in practice
        reached = n in rank
        field = grounded_field[n]
        if reached != field:
            mismatches.append((n, reached, field))

    print(f"\n=== cross-check vs graph.json's own `grounded` field (claims only) ===")
    print(f"claim slices checked: {sum(1 for n in all_slice_nodes if kind_field[n] == 'claim')}")
    print(f"mismatches: {len(mismatches)}")
    for n, reached, field in mismatches[:20]:
        print(f"  {n}  bfs_reached={reached}  grounded_field={field}")

    print("\ndone.")


if __name__ == "__main__":
    main()
