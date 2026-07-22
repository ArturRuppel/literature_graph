"""`fulltext.extract_keywords` — author-keyword scrape for the Pass-1 tag proposal, and the
`lit tag --suggest` CLI surface. Offline: fed saved `.md`-shaped text, no PDF, no network."""
from litgraph import cli
from litgraph.fulltext import extract_keywords


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
