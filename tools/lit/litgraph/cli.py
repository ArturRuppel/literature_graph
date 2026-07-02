"""`lit` command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .ingest import IngestError, Report, ingest
from .graph import build_graph, BuildError
from .build import emit
from .quotes import polish_graph
from .serve import serve


def _print_report(r: Report) -> None:
    tag = "DRY-RUN — nothing written" if r.dry_run else "written"
    print(f"\n=== lit ingest ({tag}) ===")
    print(f"  PDF        : {r.pdf}")
    srcnote = f"; metadata via {r.metadata_source}" if r.metadata_source == "crossref" else ""
    print(f"  DOI        : {r.doi}  (via {r.doi_source}{srcnote})")
    if r.title_search_unverified:
        print("  ⚠ DOI resolved by TITLE SEARCH — verify the match is the right paper.")
    if r.metadata_source == "crossref":
        print("  ⚠ focal not in OpenAlex — metadata + references via Crossref; "
              "DOI-less refs (books) and DataCite deposits (datasets) are not auto-resolved.")
    print(f"  citekey    : {r.citekey}")
    print(f"  title      : {r.title}")
    typenote = " (defaulted — review)" if r.type_defaulted else ""
    print(f"  type       : {r.type}{typenote}")
    print(f"  year       : {r.year}")
    print(f"  venue      : {r.venue_display!r} -> {r.venue_token!r}")
    print("  authors:")
    for a in r.authors:
        roles = []
        if a.position:
            roles.append(a.position)
        if a.corresponding:
            roles.append("corresponding")
        print(f"    - {a.name}" + (f"  [{', '.join(roles)}]" if roles else ""))
    refnote = ""
    if r.n_referenced and r.n_referenced != r.n_refs:
        refnote = f" of {r.n_referenced} referenced ({r.n_referenced - r.n_refs} not resolved)"
    print(f"  references : {r.n_refs} fetched{refnote} | {len(r.stubs_added)} new stubs | "
          f"{len(r.stubs_deduped)} deduped | {r.refs_skipped} skipped")
    print(f"  curated    : {r.curated_path}")
    if r.pdf_renamed_to:
        print(f"  pdf -> {r.pdf_renamed_to}")
    if r.pdf_rename_skipped:
        print("  pdf rename : SKIPPED (target exists)")
    print(f"  fulltext   : {r.fulltext_path}")
    for w in r.warnings:
        print(f"  ⚠ {w}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lit", description="literature_graph tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="initialize a paper node + citation stubs from a PDF")
    p_ing.add_argument("pdf", help="path to the paper PDF")
    p_ing.add_argument("--doi", help="override the focal DOI (skips PDF extraction)")
    p_ing.add_argument("--root", default=".", help="data root holding curated/ and stubs.yaml (default: .)")
    p_ing.add_argument("--dry-run", action="store_true", help="print the plan; write/rename nothing")
    p_ing.add_argument("--force", action="store_true", help="overwrite an existing curated/<citekey>.yaml")

    p_build = sub.add_parser("build", help="build the static graph viewer from a data repo")
    p_build.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_build.add_argument("--out", default=None,
                         help="output dir (default: <root>/dist)")

    p_srv = sub.add_parser("serve", help="serve the viewer over HTTP: rebuild on refresh, "
                                         "PDF hover-preview and click-to-open")
    p_srv.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_srv.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    p_srv.add_argument("--pdf-dir", default=None,
                       help="dir holding <citekey>.pdf files "
                            "(default: config.toml pdf_dir, else <root>/pdfs)")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        if not Path(args.pdf).is_file():
            print(f"error: no such PDF: {args.pdf}", file=sys.stderr)
            return 2
        cfg = load_config(args.root)
        try:
            report = ingest(
                args.pdf,
                root=cfg.root,
                mailto=cfg.mailto,
                doi=args.doi,
                dry_run=args.dry_run,
                force=args.force,
            )
        except IngestError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except FileExistsError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        _print_report(report)
        return 0

    if args.command == "build":
        cfg = load_config(args.root)
        out = Path(args.out) if args.out else cfg.root / "dist"
        pdf_dir = cfg.pdf_dir or cfg.root / "pdfs"
        try:
            graph = build_graph(cfg.root)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        for w in polish_graph(graph, pdf_dir):
            print(f"quote-flag: {w}", file=sys.stderr)
        emit(graph, out)
        print(f"built {len(graph.papers)} papers -> {out}/index.html")
        return 0

    if args.command == "serve":
        cfg = load_config(args.root)
        pdf_dir = Path(args.pdf_dir) if args.pdf_dir else (cfg.pdf_dir or cfg.root / "pdfs")
        try:
            build_graph(cfg.root)   # fail fast on a broken repo; later edits 500 per request
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        try:
            serve(cfg.root, pdf_dir, port=args.port)
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
