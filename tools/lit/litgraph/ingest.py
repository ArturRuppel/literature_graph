"""Orchestrate a single PDF ingest (spec §4 Stages A–D) into a reviewable Report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import pdf as pdfmod
from . import store
from .citekey import _norm_doi, make_citekey
from .fulltext import to_markdown
from .model import Author, CuratedPaper, Stub, Work, map_type
from .roles import resolve_roles
from .sources.crossref import Crossref
from .sources.openalex import OpenAlex
from .venue import venue_token


class IngestError(Exception):
    """Unrecoverable ingest problem (no resolvable DOI, etc.)."""


@dataclass
class Report:
    pdf: str
    doi: str | None = None
    doi_source: str = ""  # "--doi" | "pdf" | "title-search"
    metadata_source: str = "openalex"  # "openalex" | "crossref" (focal metadata + refs origin)
    title_search_unverified: bool = False
    citekey: str = ""
    title: str = ""
    type: str = ""
    type_defaulted: bool = False
    year: int | None = None
    venue_display: str | None = None
    venue_token: str = ""
    authors: list[Author] = field(default_factory=list)
    n_referenced: int = 0  # ids in the focal work's reference list
    n_refs: int = 0  # references actually returned by OpenAlex
    stubs_added: list[str] = field(default_factory=list)
    stubs_deduped: list[str] = field(default_factory=list)
    stubs_pruned: list[str] = field(default_factory=list)  # stubs promoted to curated (§6.3 self-heal)
    refs_skipped: int = 0
    curated_path: str = ""
    pdf_renamed_to: str | None = None
    pdf_rename_skipped: bool = False
    fulltext_path: str | None = None
    dry_run: bool = False
    warnings: list[str] = field(default_factory=list)


def _enrich_names(work: Work, crossref_pairs: list[tuple[str, str]]) -> None:
    """Overwrite OpenAlex 'First Last' names with Crossref family/given when aligned."""
    if len(crossref_pairs) == len(work.authors) and crossref_pairs:
        for a, (fam, given) in zip(work.authors, crossref_pairs):
            a.family, a.given = fam, given


def _resolve_focal(pdf_path: str, doi_override: str | None, oa: OpenAlex, cr: Crossref, report: Report) -> Work:
    def _by_doi(doi: str, source: str) -> Work | None:
        """OpenAlex first, then Crossref (for papers OpenAlex hasn't indexed yet)."""
        work = oa.fetch_work(doi)
        if work is not None:
            report.doi_source, report.metadata_source = source, "openalex"
        else:
            work = cr.fetch_work(doi)
            if work is not None:
                report.doi_source, report.metadata_source = source, "crossref"
        if work is not None:
            # OpenAlex lowercases DOIs; keep the caller's canonical casing.
            work.doi = _prefer_casing(doi, work.doi)
        return work

    if doi_override:
        work = _by_doi(doi_override, "--doi")
        if work is None:
            raise IngestError(f"--doi {doi_override} did not resolve in OpenAlex or Crossref")
        return work
    doi = pdfmod.extract_doi(pdf_path)
    if doi:
        work = _by_doi(doi, "pdf")
        if work is not None:
            return work
    # Fallback: title search (OpenAlex only).
    title = pdfmod.extract_title(pdf_path)
    if title:
        work = oa.search_by_title(title)
        if work is not None:
            report.doi_source = "title-search"
            report.metadata_source = "openalex"
            report.title_search_unverified = True
            return work
    raise IngestError(
        "could not resolve a DOI from the PDF (no embedded DOI, title search failed). "
        "Re-run with --doi <doi>."
    )


def _resolve_ref_dois(dois: list[str], oa: OpenAlex, cr: Crossref) -> list[Work]:
    """Resolve a Crossref reference DOI list to Works: OpenAlex batch, Crossref per-DOI fallback.

    Unresolvable DOIs (e.g. DataCite dataset deposits Crossref doesn't carry) are dropped.
    """
    by_doi = {_norm_doi(w.doi): w for w in oa.fetch_works_by_doi(dois) if w.doi}
    out: list[Work] = []
    for d in dois:
        work = by_doi.get(_norm_doi(d)) or cr.fetch_work(d)
        if work is not None:
            out.append(work)
    return out


def _prefer_casing(local: str, canonical: str | None) -> str | None:
    """Keep `local`'s casing when it equals `canonical` case-insensitively."""
    if canonical and local and local.lower() == canonical.lower():
        return local
    return canonical


def _year_str(year: int | None) -> str:
    return str(year) if year is not None else ""


def ingest(
    pdf_path: str,
    *,
    root: str | Path,
    mailto: str = "",
    doi: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    openalex: OpenAlex | None = None,
    crossref: Crossref | None = None,
) -> Report:
    root = Path(root)
    oa = openalex or OpenAlex(mailto=mailto)
    cr = crossref or Crossref(mailto=mailto)
    report = Report(pdf=str(pdf_path), dry_run=dry_run)

    # A/B — focal work.
    work = _resolve_focal(pdf_path, doi, oa, cr, report)
    report.doi = work.doi
    # Crossref-sourced focal already has clean family/given; only enrich OpenAlex names.
    if report.metadata_source != "crossref":
        _enrich_names(work, cr.author_names(work.doi) if work.doi else [])

    # Author roles: union OpenAlex order/flags with PDF markers.
    families = [a.family for a in work.authors]
    page_text = pdfmod.extract_text(pdf_path, max_pages=2)
    markers = pdfmod.extract_author_markers(page_text, families)
    authors = resolve_roles(work.authors, markers)

    # Citekey allocation (against existing keys; grows as references are added).
    taken = store.load_taken(root)
    vtoken = venue_token(work.venue_display)
    citekey = make_citekey(work.authors[0].family if work.authors else "", _year_str(work.year), vtoken, taken, work.doi)
    taken[citekey] = work.doi

    rtype = map_type(work.type_raw)
    report.citekey = citekey
    report.title = work.title
    report.type = rtype
    report.type_defaulted = rtype == "original" and (work.type_raw or "").lower() not in ("article", "journal-article", "original")
    report.year = work.year
    report.venue_display = work.venue_display
    report.venue_token = vtoken
    report.authors = authors

    paper = CuratedPaper(
        citekey=citekey,
        title=work.title,
        type=rtype,
        year=work.year,
        doi=work.doi,
        url=f"https://doi.org/{work.doi}" if work.doi else None,
        pdf=f"{citekey}.pdf",
        abstract=work.abstract,
        authors=authors,
    )

    # C — references -> stubs. OpenAlex ids when the focal came from OpenAlex; otherwise the
    # Crossref reference DOI list (resolved via OpenAlex batch + Crossref fallback).
    if work.referenced_works:
        refs = oa.fetch_works(work.referenced_works)
        report.n_referenced = len(work.referenced_works)
    elif work.referenced_dois:
        refs = _resolve_ref_dois(work.referenced_dois, oa, cr)
        report.n_referenced = len(work.referenced_dois)
    else:
        refs = []
    report.n_refs = len(refs)
    stubs: list[Stub] = []
    for ref in refs:
        fam = ref.authors[0].family if ref.authors else ""
        if not fam and ref.year is None:
            report.refs_skipped += 1
            continue
        rvtoken = venue_token(ref.venue_display)
        rkey = make_citekey(fam, _year_str(ref.year), rvtoken, taken, ref.doi)
        taken[rkey] = ref.doi
        stubs.append(Stub(citekey=rkey, title=ref.title, year=ref.year, doi=ref.doi, type=map_type(ref.type_raw)))

    # D — writes / rename.
    curated_path = store.write_curated(root, paper, force=force, dry_run=dry_run)
    report.curated_path = str(curated_path)

    renamed = store.rename_pdf(Path(pdf_path), citekey, dry_run=dry_run)
    if renamed is None:
        report.pdf_rename_skipped = True
        report.warnings.append(f"{citekey}.pdf already exists beside the source — left the PDF in place")
        md_source = Path(pdf_path)
    else:
        report.pdf_renamed_to = str(renamed)
        md_source = renamed if not dry_run else Path(pdf_path)

    if dry_run:
        report.fulltext_path = str(Path(pdf_path).with_name(f"{citekey}.md"))
    else:
        markdown = to_markdown(str(md_source))
        report.fulltext_path = str(store.write_fulltext(md_source, citekey, markdown, dry_run=False))

    added, deduped = store.merge_stubs(root, stubs, dry_run=dry_run)
    report.stubs_added = added
    report.stubs_deduped = deduped
    # This paper (and any earlier-curated one) is no longer a stub: drop the stale entry so
    # the build never trips the §6.3 curated/stub collision. `extra_keys` names the focal key
    # because in a dry run its curated file isn't on disk to be swept up.
    report.stubs_pruned = store.prune_curated_stubs(root, dry_run=dry_run, extra_keys=(citekey,))
    return report
