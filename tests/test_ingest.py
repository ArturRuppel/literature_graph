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


def test_idempotent_dedup_on_reingest(workspace):
    root, pdf = workspace
    ingest(str(pdf), root=root, openalex=_openalex(), crossref=_crossref())
    # Re-ingest the renamed PDF: stubs already present -> all deduped, none added.
    pdf2 = pdf.parent / "Ruppel2023eLife.pdf"
    r2 = ingest(str(pdf2), root=root, force=True, openalex=_openalex(), crossref=_crossref())
    assert r2.stubs_added == [] and len(r2.stubs_deduped) == 3
