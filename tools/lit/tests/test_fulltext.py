"""`fulltext.extract_keywords` — author-keyword scrape for the Pass-1 tag proposal, and the
`lit tag --suggest` CLI surface. Offline: fed saved `.md`-shaped text, no PDF, no network."""
import pymupdf

from litgraph import cli, fulltext
from litgraph.fulltext import _normalize, extract_keywords


def test_inline_colon_comma_separated():
    md = "Abstract\n\nKeywords: Glioblastoma, Glial cells, Tumor microenvironment\n\n## Background\n"
    assert extract_keywords(md) == ["Glioblastoma", "Glial cells", "Tumor microenvironment"]


def test_semicolon_separated():
    md = "Keywords: cell mechanics; force transmission; optogenetics\n"
    assert extract_keywords(md) == ["cell mechanics", "force transmission", "optogenetics"]


def test_key_words_two_word_label():
    md = "Key words: A, B\n"
    assert extract_keywords(md) == ["A", "B"]


def test_markdown_header_list_on_next_line():
    # pymupdf4llm sometimes emits the label as a header with the list beneath it, also headered.
    md = "## KEYWORDS\n\n## breast cancer, mechanotransduction, YAP, ERK\n\n## Introduction\n"
    assert extract_keywords(md) == ["breast cancer", "mechanotransduction", "YAP", "ERK"]


def test_dedupes_case_insensitively_and_trims_trailing_period():
    md = "Keywords: mechanics, Mechanics, invasion.\n"
    assert extract_keywords(md) == ["mechanics", "invasion"]


def test_bold_label_semicolon_separated():
    # pymupdf4llm renders many journals' label in bold: `**Keywords:** a; b; c`.
    md = "**Keywords:** glioblastoma; collective migration; jamming\n"
    assert extract_keywords(md) == ["glioblastoma", "collective migration", "jamming"]


def test_bold_label_middot_separated():
    # Springer/Cell-family papers separate on a middle-dot bullet, label often bold and colon-less.
    md = "**Keywords** Glioblastoma · Invasion · Cancer stem cells\n"
    assert extract_keywords(md) == ["Glioblastoma", "Invasion", "Cancer stem cells"]


def test_bold_header_list_on_next_line():
    md = "## **Keywords**\n\nactin filaments, myosin II motor, E-cadherin\n\n## Abstract\n"
    assert extract_keywords(md) == ["actin filaments", "myosin II motor", "E-cadherin"]


def test_inline_all_caps_label_at_end_of_runon_abstract():
    # A run-on abstract that trails its list mid-line — caught only by the all-caps fallback.
    md = "ABSTRACT: Glioblastoma is aggressive. KEYWORDS: tumor model, hydrogels, glioblastoma\n"
    assert extract_keywords(md) == ["tumor model", "hydrogels", "glioblastoma"]


def test_absent_returns_empty():
    assert extract_keywords("Abstract\n\nWe measured forces. The keywords were chosen.\n") == []


def _paper_with_md(root, key, md_text, tags_line=""):
    (root / "curated").mkdir(parents=True, exist_ok=True)
    (root / "curated" / f"{key}.yaml").write_text(f'title: "T"\ntype: original\n{tags_line}')
    (root / "pdfs").mkdir(parents=True, exist_ok=True)
    (root / "pdfs" / f"{key}.md").write_text(md_text)


def test_cli_suggest_prints_candidates_and_ready_command(tmp_path, capsys):
    _paper_with_md(tmp_path, "Chen2021Sys", "Keywords: cell mechanics, YAP signaling\n")
    rc = cli.main(["tag", "Chen2021Sys", "--suggest", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cell mechanics · YAP signaling" in out
    # kebab-cased, ready to paste
    assert "lit tag Chen2021Sys cell-mechanics yap-signaling" in out


def test_cli_suggest_writes_nothing(tmp_path):
    _paper_with_md(tmp_path, "Chen2021Sys", "Keywords: a, b\n")
    before = (tmp_path / "curated" / "Chen2021Sys.yaml").read_text()
    cli.main(["tag", "Chen2021Sys", "--suggest", "--root", str(tmp_path)])
    assert (tmp_path / "curated" / "Chen2021Sys.yaml").read_text() == before


def test_cli_suggest_no_keyword_line(tmp_path, capsys):
    _paper_with_md(tmp_path, "Chen2021Sys", "Abstract only, no keyword line.\n")
    rc = cli.main(["tag", "Chen2021Sys", "--suggest", "--root", str(tmp_path)])
    assert rc == 0
    assert "no author-keyword line found" in capsys.readouterr().out


def test_cli_suggest_missing_fulltext_errors(tmp_path, capsys):
    (tmp_path / "curated").mkdir(parents=True)
    (tmp_path / "curated" / "Chen2021Sys.yaml").write_text('title: "T"\ntype: original\n')
    rc = cli.main(["tag", "Chen2021Sys", "--suggest", "--root", str(tmp_path)])
    assert rc == 1
    assert "no full text to scan" in capsys.readouterr().err


from litgraph.fulltext import extract_reference_dois


def test_reference_dois_read_off_the_printed_list():
    # Shaped like a real pymupdf4llm extraction: "- " bullets, DOIs sprayed with spaces and
    # newlines by the PDF text layer, page furniture interleaved.
    md = (
        "## INTRODUCTION\n\nSee the references for detail.\n\n"
        "## REFERENCES\n\n"
        "- Aiello NM, Maddipati R. 2018. EMT subtype influences plasticity. Dev Cell 45:\n"
        "681-695. doi:10.1016/j .devcel.2018.05.027\n\n"
        "- Angelini TE, Hannezo E. 2011. Glass-like dynamics. Proc Natl Acad Sci 108:\n"
        "4714-4719. doi:10\n.1073/pnas.1010059108\n\n"
        "Cite this article as Cold Spring Harb Perspect Biol 2026;18:a041794\n\n"
        "- Friedl P, Mayor R. 2017. Tuning collective cell migration. Cold Spring Harb\n"
        "Perspect Biol 9: a029199. doi: 10.1101/cshperspect.a029199\n\n"
        "- Friedl P, Noble PB. 1995. Migration of coordinated cell clusters. Cancer Res 55:\n"
        "4557-4560.\n"
    )
    assert extract_reference_dois(md) == [
        "10.1016/j.devcel.2018.05.027",
        "10.1073/pnas.1010059108",
        "10.1101/cshperspect.a029199",
    ]


def test_reference_dois_dedupe_and_trim_trailing_punctuation():
    md = ("## References\n\n"
          "- A. 2020. Title. J 1: 1. doi:10.1000/abc.\n\n"
          "- B. 2021. Title. J 2: 2. doi:10.1000/ABC\n\n"
          "- C. 2022. Title. J 3: 3. doi:10.1000/xyz)\n")
    assert extract_reference_dois(md) == ["10.1000/abc", "10.1000/xyz"]


def test_reference_dois_absent_when_no_section_or_no_dois():
    assert extract_reference_dois("## Results\n\nWe measured doi-free things.\n") == []
    assert extract_reference_dois("## References\n\n- Friedl P. 1995. No DOI here.\n") == []


def test_reference_dois_take_the_last_heading():
    # "References" as a prose line early on must not shadow the real section.
    md = ("References\n\nare discussed below.\n\n"
          "- Nothing. doi:10.9999/decoy\n\n"
          "## REFERENCES\n\n- Real A. 2020. T. J 1: 1. doi:10.1000/real\n")
    assert extract_reference_dois(md) == ["10.1000/real"]


def test_reference_dois_do_not_swallow_prose_after_the_doi():
    # The journal footer that broke the first real run: the DOI is followed by prose on the
    # same line, and naive whitespace-stripping produced ".../a041794originallypublished...".
    md = ("## REFERENCES\n\n"
          "- A. 2020. T. J 1: 1. doi:10.1000/aaa\n\n"
          "_Cold Spring Harb Perspect Biol_ 2026; doi: 10.1101/cshperspect.a041794 "
          "originally published online November 24, 2025\n")
    assert extract_reference_dois(md) == ["10.1000/aaa", "10.1101/cshperspect.a041794"]


def test_reference_dois_rejoin_breaks_but_stop_at_a_word_boundary():
    from litgraph.fulltext import _stitch_doi
    assert _stitch_doi("10.1016/j .devcel.2018.05.027") == "10.1016/j.devcel.2018.05.027"
    assert _stitch_doi("10\n.1073/pnas.1010059108") == "10.1073/pnas.1010059108"
    assert _stitch_doi("10.1038/s41580-\n023-00688-7") == "10.1038/s41580-023-00688-7"
    assert _stitch_doi("10.1101/x.a041794 originally published online") == "10.1101/x.a041794"
    assert _stitch_doi("not a doi at all") is None
    assert _stitch_doi("") is None


# --- legacy publisher-font encoding (pre-2005 PDFs) ---------------------------------------

def test_legacy_glyph_repair_maps_the_slots_and_reports_what_it_cannot():
    from litgraph.fulltext import repair_legacy_glyphs
    # Real Trappe2001Nature text: "fi"/"fl" sit at 0xAE/0xAF, "=" at 0x88, an en dash at 0xB1.
    raw = "the plateau modulus at fc \x88 0:053 is ®xed and re¯ects f 139±141 at 1:5 3 10"
    out, residual = repair_legacy_glyphs(raw)
    assert "fixed" in out and "reflects" in out
    assert "= 0" in out and "139–141" in out
    # The two collisions with legitimate characters are left alone, and reported instead.
    assert "0:053" in out and " 3 " in out
    assert residual and any(":" in s for s in residual)


def test_legacy_glyph_repair_is_a_no_op_on_normally_encoded_text():
    from litgraph.fulltext import repair_legacy_glyphs
    # A real ® follows a name and is followed by space/punctuation; a real ± precedes a digit.
    clean = "Matrigel® was used; strain was 5.2 ± 0.3% at a 1:1 ratio, 3 replicates."
    assert repair_legacy_glyphs(clean) == (clean, ())


def test_both_folds_agree_across_the_legacy_repair():
    """The `.md` is repaired at ingest but the PDF still holds the raw slots, so a quote must
    fold identically from either side — otherwise every quote_loc on such a paper fails to place."""
    from litgraph.pdfview import fold
    from litgraph.quotes import _fold
    assert fold("®xed") == fold("fixed")
    assert fold("re¯ects") == fold("reflects")
    assert _fold("the ®eld") == _fold("the field")


# --- normalization order: hyphenation joins across a padded line break -----------------------
# `_normalize` used to join hyphens before stripping trailing whitespace, so a line ending
# "adhe- \n" slipped past the join. Publisher PDFs never pad there; the text layers of archive
# scans always do (Townes1955JExpZol: 383 hyphenated breaks, 383 of them padded).


def test_hyphenation_joins_across_a_space_padded_line_break():
    assert _normalize("selective adhe- \nsion of cells") == "selective adhesion of cells\n"


def test_hyphenation_still_joins_the_unpadded_publisher_case():
    assert _normalize("mechano-\nstructural") == "mechanostructural\n"


def test_a_dash_ending_a_line_is_not_a_hyphenation():
    # " -\n" has no word character before the dash, so there is nothing to rejoin.
    assert _normalize("a clause -\nand its continuation") == "a clause -\nand its continuation\n"


# --- recovering the text layer pymupdf4llm drops on archive scans ----------------------------


def _text_pdf(path, sentence, lines=40):
    """A one-page PDF carrying a real text layer big enough to clear `_DOC_TEXT_MIN`."""
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    for i in range(lines):
        page.insert_text((20, 20 + 18 * i), sentence, fontsize=9)
    doc.save(path)
    return str(path)


def test_recover_splices_the_text_layer_where_the_layout_pass_dropped_the_page(tmp_path, monkeypatch):
    sentence = "The digitizer stored this page as real text under the scan image."
    pdf = _text_pdf(tmp_path / "scan.pdf", sentence)
    # what pymupdf4llm does to a page it classifies as a picture: markers, no prose
    dropped = "**==> picture [1950 x 2924] intentionally omitted <==**\n\n##\n"
    monkeypatch.setattr(
        fulltext.pymupdf4llm, "to_markdown",
        lambda *a, **k: [{"text": dropped}] if k.get("page_chunks") else dropped,
    )
    out = fulltext._recover_dropped_pages(pdf, dropped)
    assert "digitizer stored this page" in out
    assert "intentionally omitted" not in out


def test_recover_leaves_a_healthy_extraction_untouched(tmp_path, monkeypatch):
    sentence = "A publisher PDF whose text the layout pass extracted perfectly well."
    pdf = _text_pdf(tmp_path / "clean.pdf", sentence)
    healthy = (sentence + "\n") * 40
    # if the gate ever lets a healthy paper through, the chunked call would raise and fail here
    monkeypatch.setattr(
        fulltext.pymupdf4llm, "to_markdown",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("healthy paper entered the splice path")),
    )
    assert fulltext._recover_dropped_pages(pdf, healthy) == healthy


def test_recover_skips_a_pdf_with_no_text_layer_at_all(tmp_path, monkeypatch):
    doc = pymupdf.open()
    doc.new_page(width=300, height=400)  # blank: no text to recover
    pdf = str(tmp_path / "blank.pdf")
    doc.save(pdf)
    monkeypatch.setattr(
        fulltext.pymupdf4llm, "to_markdown",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("entered the splice path")),
    )
    assert fulltext._recover_dropped_pages(pdf, "") == ""
