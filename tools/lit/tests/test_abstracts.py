"""`fulltext.extract_abstract` + the `lit abstracts` backfill.

Offline: fed saved `.md`-shaped text, no PDF, no network. The shapes here are the ones that
actually occur in the library — a Nature letter's unlabelled lead paragraph, a Cell Press
front-matter block, a Frontiers copyright sidebar, a structured abstract — because the whole
difficulty of this extractor is publisher layout, not parsing.
"""
from pathlib import Path

import pytest

from litgraph import store
from litgraph.abstracts import backfill
from litgraph.fulltext import extract_abstract

# Long enough to clear `_ABS_MIN_BYLINE` (400 chars), which is what keeps an affiliation block
# from passing for an abstract on the unlabelled path.
ABS = ("We measured the thing and found a result. The result held across three conditions and "
       "two cell lines. We conclude that the effect is real and matters for tissue mechanics. "
       "This has consequences for how collective migration is modelled in confluent layers, "
       "and for how the jamming transition is read off cell shape in a monolayer. We further "
       "show that the effect survives the removal of the substrate, which rules out the "
       "simplest alternative explanation for it.")
BODY = ("Collective migration has been studied for decades in many systems. Here we begin by "
        "reviewing what is known. The literature is large and the terminology inconsistent.")


# ── the labelled anchor

def test_abstract_heading():
    md = f"## Title\n\nA. Author, B. Author\n\n## Abstract\n\n{ABS}\n\n## Introduction\n\n{BODY}\n"
    hit = extract_abstract(md)
    assert hit.anchor == "heading"
    assert hit.text == ABS


def test_summary_heading_is_equivalent():
    md = f"## SUMMARY\n\n{ABS}\n\n## RESULTS AND DISCUSSION\n\n{BODY}\n"
    assert extract_abstract(md).text == ABS


def test_graphical_abstract_never_anchors():
    """Cell Press prints `Graphical Abstract` / `In Brief` / `Highlights` above the real
    `SUMMARY`. Anchoring on the first heading containing the word 'abstract' would take the
    teaser instead of the abstract."""
    md = ("## Graphical Abstract\n\n## In Brief\n\nAuthor et al. show that cells do things.\n\n"
          f"## Highlights\n\n- d one\n- d two\n\n## SUMMARY\n\n{ABS}\n\n## RESULTS\n\n{BODY}\n")
    assert extract_abstract(md).text == ABS


def test_inline_label_on_the_same_line():
    assert extract_abstract(f"**Abstract.** {ABS}\n\n## Introduction\n\n{BODY}\n").text == ABS


def test_interstitial_nav_heading_is_skipped():
    """Nature Reviews prints a `## Sections` contents block between the label and the text."""
    md = f"## **Abstract**\n\n## **Sections**\n\n{ABS}\n\nIntroduction\n\n{BODY}\n"
    assert extract_abstract(md).text == ABS


def test_structured_abstract_keeps_all_its_parts():
    md = ("## Summary\n\nBackground: The question is open and has been open for some time now, "
          "and the packing geometry of an epithelium is tightly controlled during development.\n\n"
          "Results: We did the experiment and it worked out as we had hoped that it would, "
          "across the whole range of parameters we were able to reach in the simulation.\n\n"
          "Conclusions: The model accounts for the observation quantitatively and well, and "
          "its response to perturbation by laser ablation matches what we measured.\n\n"
          f"## Results\n\n{BODY}\n")
    text = extract_abstract(md).text
    assert text.startswith("Background:") and "Results:" in text and "Conclusions:" in text


def test_stops_before_the_body_when_no_heading_separates_them():
    """The markdown often loses the `## Introduction` heading. A paragraph that ended in a full
    stop still ends the abstract — otherwise the introduction is appended to every paper."""
    assert extract_abstract(f"## Abstract\n\n{ABS}\n\n{BODY}\n").text == ABS


# ── the byline anchor

def test_unlabelled_lead_paragraph_after_the_byline():
    """A Nature letter prints no 'Abstract' heading at all — the abstract is the paragraph
    between the byline and the body."""
    md = f"## LETTER\n\n## A Title\n\nG. Eisenhoffer, P. Loftus & J. Rosenblatt\n\n{ABS}\n\n{BODY}\n"
    hit = extract_abstract(md, ["Eisenhoffer", "Loftus", "Rosenblatt"])
    assert hit.anchor == "byline"
    assert hit.text == ABS


def test_byline_needs_two_families():
    """One family also matches a running header or a citation, so it may not anchor alone."""
    md = f"## A Title\n\nG. Eisenhoffer\n\n{ABS}\n\n{BODY}\n"
    assert extract_abstract(md, ["Eisenhoffer"]) is None


def test_byline_ignores_the_reference_list():
    """The authors' own names recur in the references, and the paragraph after them is a
    *reference* — which reads enough like prose to pass every other test. Windowing the search
    to the title page is the only thing that stops it."""
    md = ("## A Title\n\n" + "filler paragraph. " * 900 + "\n\n## References\n\n"
          f"Soine J., Schwarz U. Traction force microscopy. J. Cell Sci. (2015).\n\n{BODY}\n")
    assert extract_abstract(md, ["Soine", "Schwarz"]) is None


def test_byline_rejects_the_affiliation_block():
    aff = ("1 Department of Physics, Some University, Some City, Country. 2 Institute of Things, "
           "Other University, Other City. 3 Centre for Matter, Third University, Third City. "
           "Correspondence to a.author@example.org and b.author@example.org for all requests.")
    md = f"## A Title\n\nA. Author, B. Author\n\n{aff}\n\n{BODY}\n"
    assert extract_abstract(md, ["Author", "Other"]) is None


def test_byline_rejects_the_copyright_sidebar():
    """Frontiers prints its citation + copyright sidebar with the full author list in it, so the
    byline anchor lands on the licence paragraph unless the boilerplate guard rejects it."""
    lic = ("© 2022 Cai, Nguyen and Liu. This is an open-access article distributed under the "
           "terms of the Creative Commons Attribution License (CC BY). The use, distribution or "
           "reproduction in other forums is permitted, provided the original authors are "
           "credited and the original publication is cited, in accordance with practice.")
    md = f"## CITATION\n\nCai G, Nguyen A and Liu AP (2022), Compressive stress.\n\n{lic}\n"
    assert extract_abstract(md, ["Cai", "Nguyen", "Liu"]) is None


def test_column_split_abstract_is_rejoined():
    """A two-column PDF breaks the abstract mid-sentence; the halves must be rejoined or the
    opening is lost."""
    md = ("## A Title\n\nA. Author and B. Other\n\nWe measured the thing and found that a wide "
          "variety of close-packed collective systems, both inert and living, can jam—\n\n"
          "both inert and living—have the potential to jam and to unjam again. The result held "
          "across every condition we tested, in two cell lines and three substrate stiffnesses. "
          "We conclude the effect is real and important for how tissues are modelled, and that "
          "it is not an artefact of the imaging.\n\n"
          f"{BODY}\n")
    text = extract_abstract(md, ["Author", "Other"]).text
    assert text.startswith("We measured") and "both inert and living" in text
    assert "Collective migration has been studied" not in text


def test_byline_rejects_a_paragraph_that_stops_mid_sentence():
    """Some Nature layouts carry no abstract block in the text layer at all, so the paragraph
    under the byline is the *introduction*, arriving mid-column and stopping mid-sentence.
    Returning it would hand back the paper's introduction dressed as its abstract — which is
    exactly what this did to `Ruppel2026NatPhys` before the completeness test went in."""
    intro = ("Animal tissues have the remarkable capacity to undergo extensive remodelling and "
             "remain structurally coherent. At the core of this capacity is the ability of cells "
             "to exchange neighbours, a process called intercalation. This fundamental process "
             "can be decomposed into topological events called T1 transitions, where two "
             "initially contacting")
    md = f"## A Title\n\nA. Ruppel, V. Misiak & F. Fagotto\n\n{intro}\n\npassive materials like "
    assert extract_abstract(md, ["Ruppel", "Misiak", "Fagotto"]) is None


def test_labelled_anchor_wins_over_the_byline():
    md = f"## A Title\n\nA. Author, B. Other\n\n{BODY}\n\n## Abstract\n\n{ABS}\n"
    assert extract_abstract(md, ["Author", "Other"]).anchor == "heading"


# ── cleaning and damage flags

def test_reference_superscripts_and_bold_are_stripped():
    md = f"## Abstract\n\n**Cells divide[1–3] , and they also move[4, 5] . {ABS}**\n"
    text = extract_abstract(md).text
    assert "[" not in text and "*" not in text
    assert text.startswith("Cells divide, and they also move. ")


def test_flags_fused_words_and_sentences():
    md = ("## Abstract\n\nIt is unknown how cell death might "
          "relieveovercrowdingduetoproliferation.Whenwetrigger apoptosis the cells go. "
          f"{ABS}\n")
    assert extract_abstract(md).artifacts


def test_does_not_flag_ordinary_long_words():
    """A detector that fires on `mechanotransduction` fires on a fifth of this library."""
    md = ("## Abstract\n\nWe studied mechanotransduction, the microenvironment, "
          f"metalloproteinases and pathophysiological transformations. {ABS}\n")
    assert extract_abstract(md).artifacts == ()


def test_returns_none_rather_than_guessing():
    assert extract_abstract("## A Title\n\nsome short text\n") is None


# ── the backfill sweep

@pytest.fixture()
def library(tmp_path: Path):
    root = tmp_path / "data"
    (root / "curated").mkdir(parents=True)
    (root / "pdfs").mkdir()
    return root


def _paper(root: Path, key: str, body: str) -> Path:
    p = root / "curated" / f"{key}.yaml"
    p.write_text(body)
    return p


def test_backfill_fills_only_the_gaps(library):
    _paper(library, "Has2020Nature",
           'title: "A"\npdf: Has2020Nature.pdf\nabstract: "already here"\n'
           'authors:\n  - {name: "Alpha, A"}\n  - {name: "Beta, B"}\n')
    _paper(library, "Lacks2020Nature",
           'title: "B"\npdf: Lacks2020Nature.pdf\n'
           'authors:\n  - {name: "Alpha, A"}\n  - {name: "Beta, B"}\n')
    (library / "pdfs" / "Has2020Nature.md").write_text(f"## Abstract\n\n{ABS}\n")
    (library / "pdfs" / "Lacks2020Nature.md").write_text(f"## Abstract\n\n{ABS}\n")

    res = backfill(library, library / "pdfs")
    assert [k for k, _ in res.filled] == ["Lacks2020Nature"]
    assert res.already == ["Has2020Nature"]
    assert 'abstract: "already here"' in (library / "curated" / "Has2020Nature.yaml").read_text()
    assert ABS in (library / "curated" / "Lacks2020Nature.yaml").read_text()


def test_backfill_reports_what_it_could_not_anchor(library):
    _paper(library, "Opaque2020Nature",
           'title: "C"\npdf: Opaque2020Nature.pdf\nauthors:\n  - {name: "Alpha, A"}\n')
    _paper(library, "NoText2020Nature",
           'title: "D"\npdf: NoText2020Nature.pdf\nauthors:\n  - {name: "Alpha, A"}\n')
    (library / "pdfs" / "Opaque2020Nature.md").write_text("## A Title\n\ncolumns interleaved\n")

    res = backfill(library, library / "pdfs")
    assert res.filled == [] and res.unanchored == ["Opaque2020Nature"]
    assert res.no_fulltext == ["NoText2020Nature"]


def test_backfill_dry_run_writes_nothing(library):
    path = _paper(library, "Lacks2020Nature",
                  'title: "B"\npdf: Lacks2020Nature.pdf\nauthors:\n  - {name: "Alpha, A"}\n')
    (library / "pdfs" / "Lacks2020Nature.md").write_text(f"## Abstract\n\n{ABS}\n")
    before = path.read_text()
    res = backfill(library, library / "pdfs", dry_run=True)
    assert [k for k, _ in res.filled] == ["Lacks2020Nature"]
    assert path.read_text() == before


def test_write_abstract_keeps_field_order_and_comments(library):
    path = _paper(library, "X2020Nature",
                  "# a curator's comment\ntitle: \"X\"\npdf: X2020Nature.pdf\n"
                  'tags: ["jamming"]\nauthors:\n  - {name: "Alpha, A"}\n')
    assert store.write_abstract(library, "X2020Nature", "the abstract") is True
    out = path.read_text()
    assert "# a curator's comment" in out
    assert out.index("pdf:") < out.index("abstract:") < out.index("tags:") < out.index("authors:")
    # Never second-guesses an abstract already on disk.
    assert store.write_abstract(library, "X2020Nature", "different") is False
    assert "the abstract" in path.read_text()
