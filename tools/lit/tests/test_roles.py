from litgraph.model import NormAuthor
from litgraph.roles import AuthorMarkers, resolve_roles


def _na(family, given="", corr=False):
    return NormAuthor(family=family, given=given, display_name=f"{given} {family}".strip(), is_corresponding=corr)


def test_elife_case_union_and_cofirst():
    # OpenAlex flagged only Schwarz corresponding; the PDF caught Balland too.
    authors = [
        _na("Ruppel", "Artur"),
        _na("Wörthmüller", "Dennis"),
        _na("Misiak", "Vladimir"),
        _na("Schwarz", "Ulrich S", corr=True),
        _na("Balland", "Martial"),
    ]
    markers = AuthorMarkers(
        corresponding_families={"schwarz", "balland"},
        equal_contrib_families={"ruppel", "worthmuller"},
    )
    out = resolve_roles(authors, markers)
    assert out[0].name == "Ruppel, Artur" and out[0].position == "first"
    assert out[1].position == "first"  # co-first via equal-contribution
    assert out[2].position is None  # middle
    assert out[3].corresponding is True and out[3].position is None
    # Balland is last AND corresponding (union recovered the corresponding flag).
    assert out[4].position == "last" and out[4].corresponding is True


def test_no_markers_falls_back_to_order_and_openalex():
    authors = [_na("A", "x"), _na("B", "y"), _na("C", "z", corr=True)]
    out = resolve_roles(authors, None)
    assert [a.position for a in out] == ["first", None, "last"]
    assert out[2].corresponding is True
