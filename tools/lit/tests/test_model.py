from litgraph.model import Author, CuratedPaper, Stub, map_type


def test_map_type():
    assert map_type("article") == "original"
    assert map_type("journal-article") == "original"
    assert map_type("review") == "review"
    assert map_type(None) == "original"


def test_stub_mapping_omits_empties():
    s = Stub(citekey="Saha2016BiophysJ", title="T", year=2016, doi="10.1/x", type="original")
    assert s.to_mapping() == {"title": "T", "year": 2016, "doi": "10.1/x", "type": "original"}
    s2 = Stub(citekey="X2020", title="T")
    assert s2.to_mapping() == {"title": "T"}


def test_curated_yaml_render():
    p = CuratedPaper(
        citekey="Ruppel2023eLife",
        title='Force "propagation" between cells',
        type="original",
        year=2023,
        doi="10.7554/eLife.83588",
        url="https://doi.org/10.7554/eLife.83588",
        pdf="Ruppel2023eLife.pdf",
        authors=[
            Author("Ruppel, Artur", position="first"),
            Author("Misiak, Vladimir"),
            Author("Balland, Martial", position="last", corresponding=True),
        ],
    )
    text = p.to_yaml()
    assert 'title: "Force \\"propagation\\" between cells"' in text
    assert "type: original" in text
    assert '  - {name: "Ruppel, Artur", position: first}' in text
    assert '  - {name: "Misiak, Vladimir"}' in text
    assert '  - {name: "Balland, Martial", position: last, corresponding: true}' in text
    # affirmations/questions are not emitted by ingest
    assert "affirmations:" not in text.split("# affirmations")[0]
