from litgraph.model import Author, CuratedPaper, Stub, map_type


def test_map_type():
    assert map_type("article") == "original"
    assert map_type("journal-article") == "original"
    assert map_type("review") == "review"
    assert map_type(None) == "original"


def test_stub_mapping_omits_empties():
    s = Stub(citekey="Bench2016Tools", title="T", year=2016, doi="10.1/x", type="original")
    assert s.to_mapping() == {"title": "T", "year": 2016, "doi": "10.1/x", "type": "original"}
    s2 = Stub(citekey="X2020", title="T")
    assert s2.to_mapping() == {"title": "T"}


def test_stub_mapping_carries_authors_and_journal():
    s = Stub(citekey="Bench2016Tools", title="T", year=2016, doi="10.1/x", type="original",
             authors=["Mei Chen", "Ada Okafor"], journal="Systems Biology")
    m = s.to_mapping()
    assert m["authors"] == ["Mei Chen", "Ada Okafor"]
    assert m["journal"] == "Systems Biology"
    # authors/journal read before year — the tooltip's title · authors · journal · year order
    assert list(m) == ["title", "authors", "journal", "year", "doi", "type"]


def test_curated_yaml_render():
    p = CuratedPaper(
        citekey="Chen2021Sys",
        title='Batching "improves" throughput',
        type="original",
        year=2021,
        doi="10.0000/synth.chen2021",
        url="https://doi.org/10.0000/synth.chen2021",
        pdf="Chen2021Sys.pdf",
        authors=[
            Author("Chen, Mei", position="first"),
            Author("Okafor, Ada"),
            Author("Vidal, Ramon", position="last", corresponding=True),
        ],
    )
    text = p.to_yaml()
    assert 'title: "Batching \\"improves\\" throughput"' in text
    assert "type: original" in text
    assert '  - {name: "Chen, Mei", position: first}' in text
    assert '  - {name: "Okafor, Ada"}' in text
    assert '  - {name: "Vidal, Ramon", position: last, corresponding: true}' in text
    # affirmations/questions are not emitted by ingest
    assert "affirmations:" not in text.split("# affirmations")[0]
    assert "tags:" not in text        # no tags by default → no key emitted


def test_curated_yaml_renders_tags():
    p = CuratedPaper(
        citekey="Chen2021Sys", title="T", type="original", year=2021,
        doi=None, url=None, pdf=None,
        authors=[Author("Chen, Mei", position="first")],
        tags=["batching", "queueing model"],
    )
    text = p.to_yaml()
    # flow list, quoted per tag; emitted before authors (SCHEMA §4 field order)
    assert 'tags: ["batching", "queueing model"]' in text
    assert text.index("tags:") < text.index("authors:")
