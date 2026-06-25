from litgraph.citekey import family_token, fold_ascii, make_citekey


def test_fold_ascii():
    assert fold_ascii("Wörthmüller") == "Worthmuller"
    assert fold_ascii("Méry") == "Mery"
    assert fold_ascii("Saïas") == "Saias"


def test_family_token_camelcase():
    assert family_token("Ruppel") == "Ruppel"
    assert family_token("van der Berg") == "VanDerBerg"
    assert family_token("O'Brien") == "OBrien"
    assert family_token("Méry") == "Mery"


def test_make_citekey_basic():
    assert make_citekey("Ruppel", 2023, "eLife", {}, doi="10.7554/eLife.83588") == "Ruppel2023eLife"


def test_make_citekey_same_doi_is_idempotent():
    taken = {"Ruppel2023eLife": "10.7554/elife.83588"}
    # Re-ingesting the same DOI reuses the key (case/URL-insensitive).
    assert make_citekey("Ruppel", 2023, "eLife", taken, doi="https://doi.org/10.7554/eLife.83588") == "Ruppel2023eLife"


def test_make_citekey_collision_different_doi_suffixes():
    taken = {"Smith2020J": "10.1/aaa"}
    assert make_citekey("Smith", 2020, "J", taken, doi="10.2/bbb") == "Smith2020Ja"
    taken["Smith2020Ja"] = "10.2/bbb"
    assert make_citekey("Smith", 2020, "J", taken, doi="10.3/ccc") == "Smith2020Jb"
