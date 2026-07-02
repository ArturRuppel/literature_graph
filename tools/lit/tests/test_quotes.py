# tests/test_quotes.py
"""Quote polishing: artifact stripping, sentence expansion, the two-tier polish, and the
polish_graph integration (offline — inline `.md` text, no network)."""

from pathlib import Path

from litgraph.graph import Graph, Paper, Slice
from litgraph.quotes import polish, polish_graph, strip_artifacts


# --- strip_artifacts ---------------------------------------------------------

def test_strip_numeric_bracket_cites():
    assert strip_artifacts("A jammed tissue is solid-like [1].") == "A jammed tissue is solid-like."
    assert strip_artifacts("shown before [3–5, 7] and since") == "shown before and since"


def test_strip_author_year_single_and_chain():
    assert strip_artifacts("evidence of unjamming (Spurlin et al., 2019).") == "evidence of unjamming."
    s = "termed cell unjamming (Atia et al., 2018; Garcia et al., 2015; Park et al., 2015, 2016)."
    assert strip_artifacts(s) == "termed cell unjamming."


def test_strip_markdown_emphasis_wrapped_cites():
    s = ("universal property of mammalian cells "
         "( _**Vicente- Manzanares et al., 2009**_ ).")
    assert strip_artifacts(s) == "universal property of mammalian cells."


def test_strip_figure_and_see_callouts():
    assert strip_artifacts("the shape index (Fig. 3b) determines phase") == "the shape index determines phase"
    assert strip_artifacts("as described (see Methods) below") == "as described below"


def test_keeps_content_parentheticals():
    # a name-then-year is a cite; these are not -> preserved
    for keep in ["explants (N = 16) reveals",
                 "nucleus shape (CeNuS) and low density",
                 "criteria (tumor diameter, tumor grade, lymph node status) used"]:
        assert strip_artifacts(keep) == keep


def test_mid_sentence_strip_leaves_clean_seams():
    s = "differentiation (Engler et al., 2006), fate (Chen et al., 1997), or migration."
    assert strip_artifacts(s) == "differentiation, fate, or migration."


# --- polish: expansion, tiers, fallback --------------------------------------

FULLTEXT = (
    "In gastrulation of the developing fruit fly embryo, ventral furrow formation is a "
    "signature of unjamming (Atia et al., 2018; Bi et al., 2014, 2015). "
    "The shape index, as shown in Fig. 3, determines the phase.\n"
)


def test_polish_expands_anchor_to_sentence_and_strips():
    disp, status = polish("ventral furrow formation is a signature of unjamming", FULLTEXT)
    assert status == "verbatim"
    assert disp == ("In gastrulation of the developing fruit fly embryo, ventral furrow "
                    "formation is a signature of unjamming.")


def test_polish_abbreviation_does_not_end_sentence():
    disp, status = polish("determines the phase", FULLTEXT)
    assert status == "verbatim"
    # must not break at "Fig." — the whole sentence comes back
    assert disp == "The shape index, as shown in Fig. 3, determines the phase."


def test_polish_not_found_strips_without_expanding():
    disp, status = polish("a claim not present [9] in the text", FULLTEXT)
    assert status == "not_found"
    assert disp == "a claim not present in the text"


def test_polish_empty_fulltext_is_not_found():
    disp, status = polish("anything at all", "")
    assert status == "not_found"
    assert disp == "anything at all"


def test_polish_joined_quote_polishes_each_segment():
    ft = "First sentence about coupling. A middle one. Then the disruption result here.\n"
    disp, status = polish("about coupling [...] the disruption result", ft)
    assert status == "joined"
    assert disp == "First sentence about coupling. […] Then the disruption result here."


# --- polish_graph integration ------------------------------------------------

def _graph(*slices: Slice) -> Graph:
    p = Paper(citekey="Demo2020Jour", curated=True, title="t", type="original", year=2020,
              slices=list(slices))
    return Graph(papers={"Demo2020Jour": p}, broad={}, order=["Demo2020Jour"])


def test_polish_graph_sets_display_and_flags(tmp_path: Path):
    (tmp_path / "Demo2020Jour.md").write_text(
        "We show that cells jam near the transition (Smith et al., 2019). The end.\n",
        encoding="utf-8")
    g = _graph(
        Slice(id="c1", kind="claim", text="cells jam", quote="cells jam near the transition"),
        Slice(id="c2", kind="claim", text="absent", quote="a quote not in the md at all"),
    )
    warns = polish_graph(g, tmp_path)
    c1, c2 = g.papers["Demo2020Jour"].slices
    assert c1.quote_display == "We show that cells jam near the transition."
    assert c2.quote_display == "a quote not in the md at all"           # stripped-only fallback
    assert any("c2" in w and "not found" in w for w in warns)
    assert not any("c1" in w for w in warns)


def test_polish_graph_no_md_flags_all_quotes(tmp_path: Path):
    g = _graph(Slice(id="c1", kind="claim", text="x", quote="some anchor text"))
    warns = polish_graph(g, tmp_path)   # empty dir -> no Demo2020Jour.md
    assert g.papers["Demo2020Jour"].slices[0].quote_display == "some anchor text"
    assert any("no Demo2020Jour.md" in w for w in warns)


def test_polish_graph_skips_stubs_and_quoteless(tmp_path: Path):
    p_stub = Paper(citekey="Stub2019Jour", curated=False, title="t", type="original", year=2019)
    p_stub.slices = [Slice(id="c1", kind="claim", text="x", quote="ignored")]  # stub, skip
    g = Graph(papers={"Stub2019Jour": p_stub}, broad={}, order=["Stub2019Jour"])
    assert polish_graph(g, tmp_path) == []
    assert p_stub.slices[0].quote_display is None
