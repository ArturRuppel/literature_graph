import json
import re
from pathlib import Path

import fitz
import pytest

from litgraph.ingest import ingest
from litgraph.sources.crossref import Crossref
from litgraph.sources.openalex import OpenAlex

FIX = Path(__file__).parent / "fixtures"


def _make_pdf(path: Path) -> None:
    """A real PDF whose page text is the eLife page-1 fixture (DOI + byline markers)."""
    text = (FIX / "elife_page0.txt").read_text()
    doc = fitz.open()
    page = doc.new_page(width=1200, height=3000)
    page.insert_text((36, 60), text, fontsize=8)
    doc.save(str(path))
    doc.close()


def _openalex() -> OpenAlex:
    focal = json.loads((FIX / "oa_focal.json").read_text())
    batch = json.loads((FIX / "oa_refs_batch.json").read_text())

    def get_json(url: str) -> dict:
        if "/works/https://doi.org/" in url:
            return focal
        if "filter=openalex_id" in url:
            return batch
        return {"results": []}

    return OpenAlex(mailto="t@e", get_json=get_json)


def _crossref() -> Crossref:
    cr = json.loads((FIX / "cr_focal.json").read_text())
    return Crossref(mailto="t@e", get_json=lambda url: cr)


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    pdf = pdf_dir / "Ruppel_et_al_2023_Force_propagation_eLife.pdf"
    _make_pdf(pdf)
    # The synthetic PDF's base font omits the † / ‡ marker glyphs; feed the real page
    # text to the marker step (genuine fitz extraction is covered by test_pdf).
    page_text = (FIX / "elife_page0.txt").read_text()
    monkeypatch.setattr("litgraph.pdf.extract_text", lambda path, max_pages=None: page_text)
    return root, pdf


def test_ingest_writes_node_stubs_and_fulltext(workspace):
    root, pdf = workspace
    r = ingest(str(pdf), root=root, openalex=_openalex(), crossref=_crossref())

    # Identifier convention <Family><Year><Venue>.
    assert r.citekey == "Ruppel2023eLife"
    assert r.doi == "10.7554/eLife.83588"
    assert r.type == "original" and r.year == 2023
    assert r.venue_token == "eLife"

    # Author roles: co-first via †, corresponding union recovered Balland.
    by_name = {a.name: a for a in r.authors}
    assert by_name["Ruppel, Artur"].position == "first"
    assert by_name["Wörthmüller, Dennis"].position == "first"
    assert by_name["Schwarz, Ulrich S"].corresponding is True
    assert by_name["Balland, Martial"].position == "last"
    assert by_name["Balland, Martial"].corresponding is True

    # Curated file on disk, named by citekey.
    curated = root / "curated" / "Ruppel2023eLife.yaml"
    assert curated.exists()
    body = curated.read_text()
    assert '  - {name: "Ruppel, Artur", position: first}' in body
    assert '  - {name: "Balland, Martial", position: last, corresponding: true}' in body
    assert "affirmations:" not in body.split("# affirmations")[0]

    # Three stubs, all keyed <Family><Year><Venue>.
    assert len(r.stubs_added) == 3 and r.refs_skipped == 0
    stubs = (root / "stubs.yaml").read_text()
    for key in r.stubs_added:
        assert re.match(r"^[A-Z][A-Za-z'-]*\d{4}\w*$", key), key
        assert f"{key}:" in stubs

    # Stubs carry the bib metadata OpenAlex already returned for each ref: byline authors + journal.
    from ruamel.yaml import YAML
    stub_doc = YAML(typ="safe").load(stubs)
    schwarz = next(v for v in stub_doc.values() if v["title"].startswith("Traction force microscopy"))
    assert schwarz["authors"] == ["Ulrich S. Schwarz", "Jérôme R. D. Soiné"]
    assert schwarz["journal"] == "Biochimica et Biophysica Acta (BBA) - Molecular Cell Research"

    # Abstract: de-inverted from OpenAlex, written into the curated YAML.
    assert 'abstract: "Cell-generated forces coordinate large-scale tissue behavior"' in body

    # PDF renamed + full-text markdown beside it.
    assert (pdf.parent / "Ruppel2023eLife.pdf").exists()
    assert not pdf.exists()  # moved
    assert (pdf.parent / "Ruppel2023eLife.md").exists()
    assert "Force propagation" in (pdf.parent / "Ruppel2023eLife.md").read_text()


def test_dry_run_writes_nothing(workspace):
    root, pdf = workspace
    r = ingest(str(pdf), root=root, dry_run=True, openalex=_openalex(), crossref=_crossref())
    assert r.citekey == "Ruppel2023eLife"
    assert not (root / "curated" / "Ruppel2023eLife.yaml").exists()
    assert not (root / "stubs.yaml").exists()
    assert pdf.exists()  # not renamed
    assert not (pdf.parent / "Ruppel2023eLife.pdf").exists()
    assert not (pdf.parent / "Ruppel2023eLife.md").exists()
    # but the plan still reports what it would add
    assert len(r.stubs_added) == 3


def test_promoting_a_stub_prunes_it_from_stubs_yaml(workspace):
    # The focal paper was already a stub (cited by an earlier curated paper). Ingesting it
    # promotes it to curated; its stale stub must be dropped, or the build trips §6.3.
    root, pdf = workspace
    (root / "stubs.yaml").write_text(
        "Ruppel2023eLife:\n"
        "  title: Force propagation\n"
        "  year: 2023\n"
        "  doi: 10.7554/eLife.83588\n")
    r = ingest(str(pdf), root=root, openalex=_openalex(), crossref=_crossref())
    assert r.stubs_pruned == ["Ruppel2023eLife"]
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((root / "stubs.yaml").read_text())
    assert "Ruppel2023eLife" not in doc          # promoted -> no longer a stub
    assert (root / "curated" / "Ruppel2023eLife.yaml").exists()


def test_idempotent_dedup_on_reingest(workspace):
    root, pdf = workspace
    ingest(str(pdf), root=root, openalex=_openalex(), crossref=_crossref())
    # Re-ingest the renamed PDF: stubs already present -> all deduped, none added.
    pdf2 = pdf.parent / "Ruppel2023eLife.pdf"
    r2 = ingest(str(pdf2), root=root, force=True, openalex=_openalex(), crossref=_crossref())
    assert r2.stubs_added == [] and len(r2.stubs_deduped) == 3


def _crossref_focal(doi: str, ref_dois: list[str], *, venue: str, year: int) -> Crossref:
    """Crossref that supplies focal metadata + a reference DOI list (one DOI-less)."""
    msg = {
        "message": {
            "title": ["Morphogenesis on chip"],
            "author": [{"family": "Ruppel", "given": "Artur"}, {"family": "Balland", "given": "Martial"}],
            "issued": {"date-parts": [[year]]},
            "type": "journal-article",
            "container-title": [venue],
            "DOI": doi,
            "abstract": "<jats:title>Abstract</jats:title><jats:p>Tissue folds on a chip.</jats:p>",
            "reference": [{"DOI": d} for d in ref_dois] + [{"unstructured": "A book, no DOI (1967)."}],
        }
    }
    return Crossref(mailto="t@e", get_json=lambda url: msg)


def _openalex_no_focal_doi_batch() -> OpenAlex:
    """OpenAlex that lacks every single-DOI lookup but resolves the doi-filter batch."""
    batch = json.loads((FIX / "oa_refs_batch.json").read_text())

    def get_json(url: str) -> dict:
        if "filter=doi:" in url:
            return batch
        if "/works/https://doi.org/" in url:  # focal + per-ref single lookups: absent
            return {}
        return {"results": []}

    return OpenAlex(mailto="t@e", get_json=get_json)


def test_crossref_fallback_when_openalex_lacks_focal(workspace):
    """A just-published paper absent from OpenAlex: focal + refs come from Crossref."""
    root, pdf = workspace
    focal_doi = "10.1038/s41567-026-03311-6"
    ref_dois = ["10.1016/j.bbamcr.2015.05.028", "10.1016/j.devcel.2015.03.016"]
    oa = _openalex_no_focal_doi_batch()
    cr = _crossref_focal(focal_doi, ref_dois, venue="eLife", year=2026)

    r = ingest(str(pdf), root=root, doi=focal_doi, openalex=oa, crossref=cr)

    assert r.metadata_source == "crossref"
    assert r.doi_source == "--doi"
    assert r.citekey == "Ruppel2026eLife"
    assert r.doi == focal_doi and r.year == 2026
    # Only the two DOI-bearing references resolve; the DOI-less book is not counted.
    assert r.n_referenced == 2 and r.n_refs == 2
    assert len(r.stubs_added) == 2
    curated = root / "curated" / "Ruppel2026eLife.yaml"
    assert curated.exists()
    # Crossref abstract: JATS tags stripped, leading "Abstract" heading dropped
    assert 'abstract: "Tissue folds on a chip."' in curated.read_text()


from litgraph.sources.openalex import _deinvert
from litgraph.sources.crossref import _plain_abstract


def test_openalex_deinvert_rebuilds_word_order():
    idx = {"Batching": [0], "improves": [1], "throughput": [2, 4], "and": [3]}
    assert _deinvert(idx) == "Batching improves throughput and throughput"
    assert _deinvert(None) is None
    assert _deinvert({}) is None


def test_crossref_abstract_strips_jats_and_heading():
    jats = ("<jats:title>Abstract</jats:title><jats:p>Buffers cost memory.</jats:p>"
            "<jats:p>Latency too.</jats:p>")
    assert _plain_abstract(jats) == "Buffers cost memory. Latency too."
    assert _plain_abstract("Abstract: plain text") == "plain text"
    assert _plain_abstract(None) is None
    assert _plain_abstract("   ") is None


def test_doi_unresolvable_in_both_raises(workspace):
    root, pdf = workspace

    def oa_get(url):
        return {} if "/works/" in url else {"results": []}

    oa = OpenAlex(mailto="t@e", get_json=oa_get)
    cr = Crossref(mailto="t@e", get_json=lambda url: {})  # empty message -> None
    with pytest.raises(Exception):
        ingest(str(pdf), root=root, doi="10.0000/nope", openalex=oa, crossref=cr)
