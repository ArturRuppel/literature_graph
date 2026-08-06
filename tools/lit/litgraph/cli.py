"""`lit` command-line entry point."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .config import load_config
from .ingest import IngestError, Report, ingest
from .graph import build_graph, BuildError
from .build import emit
from .preview import build_preview_graph, emit_preview
from .quotes import polish_graph, verify_quote_locs_graph
from .serve import serve


def _slug(kw: str) -> str:
    """A keyword phrase → kebab tag, matching the repo's lowercase-hyphen tag convention."""
    s = re.sub(r"[^\w\s-]", "", kw.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-")


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
    if r.refs_from_fulltext:
        print("  ⚠ neither OpenAlex nor Crossref carries this paper's reference list — DOIs read "
              "off the printed list in the PDF. References that print no DOI are not recovered.")
    if r.stubs_pruned:
        print(f"  promoted   : {', '.join(r.stubs_pruned)} (stub -> curated, dropped from stubs.yaml)")
    if r.stubs_only:
        print(f"  curated    : {r.curated_path}  (stubs-only run — left untouched)")
        for w in r.warnings:
            print(f"  ⚠ {w}")
        print()
        return
    print(f"  abstract   : {r.abstract_source or 'NONE — see the warning below'}")
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
    p_ing.add_argument("--stubs-only", action="store_true",
                       help="backfill citation stubs for an already-ingested paper: merge stubs and "
                            "leave curated/<citekey>.yaml, the PDF and the .md untouched")

    p_build = sub.add_parser("build", help="build the static graph viewer from a data repo")
    p_build.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_build.add_argument("--out", default=None,
                         help="output dir (default: <root>/dist)")

    p_prev = sub.add_parser("preview", help="render one paper's local subgraph in isolation "
                                            "(curation: see a proposition as it'll look)")
    p_prev.add_argument("citekey", nargs="?",
                        help="focal paper citekey, or an aim as \"@<slug>\" "
                             "(default: --scratch file stem)")
    p_prev.add_argument("--scratch", default=None,
                        help="a curated-schema YAML to overlay as the focal paper (or an "
                             "aim-schema YAML with an \"@<slug>\" key) — propose before "
                             "tokenizing into curated/ or programme/aims/")
    p_prev.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_prev.add_argument("--out", default=None, help="output dir (default: <root>/dist)")
    p_prev.add_argument("--pdf-dir", default=None,
                        help="dir holding <citekey>.md for quote polishing "
                             "(default: config.toml pdf_dir, else <root>/pdfs)")

    p_loc = sub.add_parser("locate", help="resolve each curated quote's place in its PDF and "
                                          "store it as quote_loc (full-coverage highlight anchors)")
    p_loc.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_loc.add_argument("--pdf-dir", default=None,
                       help="dir holding <citekey>.pdf files "
                            "(default: config.toml pdf_dir, else <root>/pdfs)")
    p_loc.add_argument("--force", action="store_true",
                       help="re-resolve quotes that already have a quote_loc (default: keep them)")
    p_loc.add_argument("--dry-run", action="store_true", help="report what would be located; write nothing")

    p_srv = sub.add_parser("serve", help="serve the viewer over HTTP: rebuild on refresh, "
                                         "PDF hover-preview and click-to-open")
    p_srv.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_srv.add_argument("--host", default="127.0.0.1",
                       help="bind address (default: 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    p_srv.add_argument("--pdf-dir", default=None,
                       help="dir holding <citekey>.pdf files "
                            "(default: config.toml pdf_dir, else <root>/pdfs)")
    p_srv.add_argument("--read-only", action="store_true",
                       help="refuse the endpoints that write the repo or spawn an agent "
                            "(for a mirror serving a checkout it does not author)")

    p_foc = sub.add_parser("focus", help="aim a running `lit serve` PDF pane at a quote "
                                         "(curation: mark a passage in the human's view)")
    p_foc.add_argument("citekey", help="paper whose PDF to show")
    p_foc.add_argument("--quote", default="",
                       help="passage to highlight (verbatim; omit to just open the paper)")
    p_foc.add_argument("--host", default="127.0.0.1", help="lit serve host (default: 127.0.0.1)")
    p_foc.add_argument("--port", type=int, default=8000, help="lit serve port (default: 8000)")

    p_enr = sub.add_parser("enrich", help="backfill authors + journal onto existing stubs.yaml "
                                          "entries from OpenAlex (by DOI)")
    p_enr.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, config.toml)")
    p_enr.add_argument("--force", action="store_true",
                       help="re-fetch stubs that already have authors + journal (overwrite them)")
    p_enr.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")

    p_abs = sub.add_parser("abstracts", help="backfill missing abstracts onto curated papers from "
                                             "their stored full text (for the publishers that "
                                             "deposit none to OpenAlex/Crossref)")
    p_abs.add_argument("citekeys", nargs="*", help="papers to fill (omit for every curated paper)")
    p_abs.add_argument("--root", default=".", help="data root (curated/, pdfs/, config.toml)")
    p_abs.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")

    p_tag = sub.add_parser("tag", help="add / remove / list a curated paper's tags "
                                       "(free-form curator labels; searchable in the viewer)")
    p_tag.add_argument("citekey", help="curated paper to tag")
    p_tag.add_argument("tags", nargs="*", help="tag(s) to add (omit to just list the current tags)")
    p_tag.add_argument("--remove", action="store_true", help="remove the given tag(s) instead of adding")
    p_tag.add_argument("--suggest", action="store_true", help="propose tags from the paper's author-keyword "
                                                              "line (Pass 1); prints candidates, writes nothing")
    p_tag.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, config.toml)")

    p_top = sub.add_parser("topics", help="report the topic axis (SCHEMA §9): the tree with paper "
                                          "counts, or one topic's papers; --orphans finds tags no "
                                          "topic files and keywords no paper carries")
    p_top.add_argument("slug", nargs="?",
                       help="one topic — list the papers it reaches (omit for the whole tree)")
    p_top.add_argument("--orphans", action="store_true",
                       help="report unfiled tags, dead keywords and stranded papers instead")
    p_top.add_argument("--strict", action="store_true",
                       help="exit non-zero if --orphans flags anything (for CI)")
    p_top.add_argument("--root", default=".", help="data root (topics/, curated/, ...)")

    p_prog = sub.add_parser("programme", help="report the programme graph's emergent state: "
                                              "load-bearing assumptions by blast radius, tests at "
                                              "risk, aspirational capabilities, open questions, orphans")
    p_prog.add_argument("--root", default=".", help="data root (programme/, curated/, ...)")
    p_prog.add_argument("--strict", action="store_true",
                        help="exit non-zero if anything is flagged (for CI)")

    p_cur = sub.add_parser("curate", help="move a paper into (or out of) the in-progress worklist "
                                          "(`[curation] active` in config.toml)")
    p_cur.add_argument("citekey", help="curated paper to move")
    p_cur.add_argument("--done", action="store_true",
                       help="return the paper to the graph (remove from the worklist)")
    p_cur.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, config.toml)")

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
                stubs_only=args.stubs_only,
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
        for w in verify_quote_locs_graph(graph, pdf_dir):
            print(f"quote-flag: {w}", file=sys.stderr)
        emit(graph, out)
        print(f"built {len(graph.papers)} papers -> {out}/index.html")
        return 0

    if args.command == "topics":
        from .graph import load_repo
        from .topics import (TopicError, children, coverage, keyword_closure,
                             load_topics, papers_in, roots, validate_topics)
        cfg = load_config(args.root)
        papers, broad = load_repo(cfg.root)          # skips the full slice validate: topics
        topics = load_topics(cfg.root)               # are independent of the graph by design
        if not topics:
            print(f"no topics/ tree under {cfg.root}", file=sys.stderr)
            return 1
        try:
            validate_topics(topics, set(broad))
        except TopicError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        if args.orphans:
            unfiled, dead, stranded = coverage(topics, papers)
            for label, items, gloss in (
                ("unfiled tags", unfiled, "on a paper, in no topic — the topic layer is behind"),
                ("dead keywords", dead, "in a topic, on no paper — a typo or a renamed tag"),
                ("stranded papers", stranded, "curated, reached by no topic"),
            ):
                print(f"{label} ({len(items)}) — {gloss}")
                for i in items:
                    print(f"    {i}")
            return 1 if (args.strict and (unfiled or dead or stranded)) else 0

        if args.slug:
            if args.slug not in topics:
                print(f"error: no such topic: {args.slug}", file=sys.stderr)
                return 2
            hits = papers_in(topics, args.slug, papers)
            t = topics[args.slug]
            print(f"{t.title or args.slug} — {len(hits)} paper{'' if len(hits) == 1 else 's'}"
                  f"  [{', '.join(sorted(keyword_closure(topics, args.slug)))}]")
            for ck in hits:
                print(f"    {ck}  {papers[ck].title}")
            return 0

        kids = children(topics)
        seen: set[str] = set()

        def show(slug: str, depth: int) -> None:
            n = len(papers_in(topics, slug, papers))
            kw = len(keyword_closure(topics, slug))
            mark = " ↑" if len(topics[slug].broader) > 1 and slug in seen else ""
            print(f"  {'    ' * depth}{'· ' if depth else ''}{slug:<{36 - 4 * depth}}"
                  f"{n:>4} paper{' ' if n == 1 else 's'}  {kw:>3} keywords{mark}")
            seen.add(slug)
            for c in kids[slug]:
                show(c, depth + 1)

        for r in roots(topics):
            show(r, 0)
        ncur = sum(1 for p in papers.values() if p.curated)
        print(f"\n{len(topics)} topics over {ncur} curated papers "
              f"(a topic may appear under several parents; ↑ = repeat)")
        return 0

    if args.command == "preview":
        citekey = args.citekey or (Path(args.scratch).stem if args.scratch else None)
        if not citekey:
            print("error: give a citekey or --scratch <file>", file=sys.stderr)
            return 2
        cfg = load_config(args.root)
        out = Path(args.out) if args.out else cfg.root / "dist"
        pdf_dir = Path(args.pdf_dir) if args.pdf_dir else (cfg.pdf_dir or cfg.root / "pdfs")
        scratch = Path(args.scratch) if args.scratch else None
        if scratch is not None and not scratch.is_file():
            print(f"error: no such scratch file: {scratch}", file=sys.stderr)
            return 2
        try:
            graph = build_preview_graph(cfg.root, citekey, scratch)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        for w in polish_graph(graph, pdf_dir):
            if w.startswith(f"{citekey}:"):        # only the focal paper's quote flags matter here
                print(f"quote-flag: {w}", file=sys.stderr)
        html = emit_preview(graph, citekey, out)
        print(f"preview {citekey} -> {html}")
        return 0

    if args.command == "locate":
        from ruamel.yaml import YAML
        from . import store
        from .serve import locate_quote
        cfg = load_config(args.root)
        pdf_dir = Path(args.pdf_dir) if args.pdf_dir else (cfg.pdf_dir or cfg.root / "pdfs")
        reader = YAML(typ="safe")
        located = papers = missing = 0
        for f in sorted((cfg.root / "curated").glob("*.yaml")):
            key = f.stem
            pdf = pdf_dir / f"{key}.pdf"
            if not pdf.is_file():
                continue
            doc = reader.load(f.read_text()) or {}
            locs: dict[str, dict] = {}
            for group in ("claims", "questions", "methods"):
                for s in doc.get(group, []) or []:
                    q = s.get("quote")
                    if not q or (s.get("quote_loc") and not args.force):
                        continue
                    loc = locate_quote(pdf, q)
                    if loc:
                        locs[s["id"]] = loc
                    else:
                        missing += 1
                        print(f"  ⚠ {key}:{s['id']} could not be located", file=sys.stderr)
            if locs:
                papers += 1
                located += len(locs)
                if not args.dry_run:
                    store.write_quote_locs(cfg.root, key, locs)
        tag = "DRY-RUN — nothing written" if args.dry_run else "written"
        print(f"lit locate ({tag}): {located} quote_loc across {papers} papers"
              + (f"; {missing} not located" if missing else ""))
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
            serve(cfg.root, pdf_dir, host=args.host, port=args.port,
                  read_only=args.read_only)
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0

    if args.command == "focus":
        import json
        import urllib.error
        import urllib.request
        url = f"http://{args.host}:{args.port}/focus"
        data = json.dumps({"citekey": args.citekey, "quote": args.quote}).encode()
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                rec = json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            # POST /focus 404s with a JSON `null` for a missing PDF; a plain-text 404 instead
            # means the route isn't there — an older `lit serve` predating the focus channel.
            if e.read().decode(errors="replace").strip() == "null":
                print(f"error: server has no {args.citekey}.pdf to focus", file=sys.stderr)
            else:
                print("error: this lit serve has no /focus route — restart it on the current "
                      "code", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"error: no lit serve at {url} ({e.reason}) — is it running?", file=sys.stderr)
            return 1
        loc = rec.get("loc") if rec else None
        if args.quote and loc:
            print(f"focus → {rec['citekey']} p.{loc['page'] + 1} ({len(loc['rects'])} rect(s))")
        elif args.quote:
            print(f"focus → {rec['citekey']} (quote not located; opened at page top)")
        else:
            print(f"focus → {rec['citekey']}")
        return 0

    if args.command == "tag":
        from . import store
        cfg = load_config(args.root)
        if args.suggest:
            from .fulltext import extract_keywords
            pdf_dir = cfg.pdf_dir or cfg.root / "pdfs"
            md = pdf_dir / f"{args.citekey}.md"
            if not md.is_file():
                print(f"error: no full text to scan: {md}", file=sys.stderr)
                return 1
            kws = extract_keywords(md.read_text())
            if not kws:
                print(f"{args.citekey}: no author-keyword line found in the full text")
                return 0
            slugs = [_slug(k) for k in kws]
            print(f"author keywords ({len(kws)}): " + " · ".join(kws))
            print("  " + " ".join(["lit", "tag", args.citekey, *slugs]))
            return 0
        try:
            tags = store.edit_tags(cfg.root, args.citekey, args.tags, remove=args.remove)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        shown = ", ".join(tags) if tags else "(no tags)"
        if not args.tags:
            print(f"{args.citekey}: {shown}")
        else:
            verb = "removed from" if args.remove else "added to"
            print(f"tag → {', '.join(args.tags)} {verb} {args.citekey}  |  now: {shown}")
        return 0

    if args.command == "programme":
        from .programme import format_report, report as programme_report
        cfg = load_config(args.root)
        try:
            graph = build_graph(cfg.root)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if not graph.aims:
            print(f"no programme/aims/ under {cfg.root} — nothing to report")
            return 0
        rep = programme_report(graph)
        print(format_report(rep))
        return 1 if (args.strict and not rep.clean) else 0

    if args.command == "curate":
        from .config import set_active
        cfg = load_config(args.root)
        key = args.citekey
        add = not args.done
        if add and not (cfg.root / "curated" / f"{key}.yaml").is_file():
            print(f"error: not a curated paper: {key}", file=sys.stderr)
            return 1
        active = set_active(cfg.root, key, add)
        if add:
            print(f"curate → {key} moved into the in-progress zone ({len(active)} in progress)")
        else:
            print(f"curate → {key} returned to the graph ({len(active)} in progress)")
        return 0

    if args.command == "enrich":
        from . import store
        from .sources.openalex import OpenAlex
        cfg = load_config(args.root)
        oa = OpenAlex(mailto=cfg.mailto)
        try:
            res = store.enrich_stubs(cfg.root, oa, dry_run=args.dry_run, force=args.force)
        except Exception as e:  # network/parse — report, don't traceback
            print(f"error: {e}", file=sys.stderr)
            return 1
        tag = "DRY-RUN — nothing written" if args.dry_run else "written"
        print(f"lit enrich ({tag}): {len(res.enriched)} enriched, {len(res.already)} already "
              f"complete, {len(res.no_doi)} without DOI, {len(res.unmatched)} unmatched")
        for k in res.unmatched:
            print(f"  ⚠ {k}: no OpenAlex match / nothing to add", file=sys.stderr)
        return 0

    if args.command == "abstracts":
        from .abstracts import backfill
        cfg = load_config(args.root)
        res = backfill(cfg.root, cfg.pdf_dir, dry_run=args.dry_run,
                       only=tuple(args.citekeys))
        tag = "DRY-RUN — nothing written" if args.dry_run else "written"
        print(f"lit abstracts ({tag}): {len(res.filled)} filled, {len(res.already)} already "
              f"had one, {len(res.unanchored)} unanchored, {len(res.no_fulltext)} without a .md")
        for key, anchor in res.filled:
            # The anchor is the whole point of the report: a "heading" fill copied a section the
            # paper itself labelled Abstract, a "byline" fill took the unlabelled lead paragraph
            # and is the one to spot-check against the PDF.
            note = "  ← unlabelled lead paragraph, check against the PDF" if anchor == "byline" else ""
            print(f"  + {key} ({anchor}){note}")
        for key, artifacts in res.flagged:
            print(f"  ⚠ {key}: PDF text-layer damage in the abstract ({', '.join(artifacts)}) "
                  f"— fix by hand", file=sys.stderr)
        for key in res.unanchored:
            print(f"  ⚠ {key}: nothing anchored safely in the full text — add the abstract by hand",
                  file=sys.stderr)
        for key in res.no_fulltext:
            print(f"  ⚠ {key}: no <citekey>.md beside the PDF — re-ingest to write one",
                  file=sys.stderr)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
