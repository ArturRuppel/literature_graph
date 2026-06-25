from pathlib import Path

from litgraph.pdf import extract_author_markers, find_doi

FIXTURE = Path(__file__).parent / "fixtures" / "elife_page0.txt"


def test_find_doi_labeled():
    assert find_doi("blah DOI: https://doi.org/10.7554/eLife.83588\nmore") == "10.7554/eLife.83588"


def test_find_doi_strips_trailing_punctuation():
    assert find_doi("see 10.1016/j.bpj.2016.02.013.") == "10.1016/j.bpj.2016.02.013"


def test_find_doi_none():
    assert find_doi("no identifiers here") is None


def test_author_markers_elife():
    text = FIXTURE.read_text()
    families = [
        "Ruppel", "Wörthmüller", "Misiak", "Kelkar", "Wang", "Moreau", "Méry",
        "Révilloud", "Charras", "Cappello", "Boudou", "Schwarz", "Balland",
    ]
    m = extract_author_markers(text, families)
    # '*' authors are corresponding; OpenAlex missed Balland but the PDF catches both.
    assert m.corresponding_families == {"schwarz", "balland"}
    # '†' authors contributed equally → co-first.
    assert m.equal_contrib_families == {"ruppel", "worthmuller"}
