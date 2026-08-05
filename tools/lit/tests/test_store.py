"""`store.write_quote_loc` — authored PDF anchor, round-tripped so the curator's file survives."""
import pytest

from litgraph import store


def _paper(root):
    (root / "curated").mkdir(parents=True)
    p = root / "curated" / "Chen2021Sys.yaml"
    p.write_text(
        "# a hand-authored curated file — comments must survive a write-back\n"
        'title: "Batching"\n'
        "type: original\n"
        "claims:\n"
        '  - {id: c1, text: "throughput rises", quote: "throughput increased monotonically"}\n'
        '  - {id: c2, text: "latency grows", quote: "median latency grew"}\n')
    return p


def test_prune_curated_stubs_drops_promoted_and_preserves_comments(tmp_path):
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Fuhs2022NatPhys.yaml").write_text('title: "Rigid tumours"\ntype: original\n')
    (tmp_path / "stubs.yaml").write_text(
        "# frontier of un-sliced containers\n"
        "Fuhs2022NatPhys:\n"
        "  title: Rigid tumours contain soft cancer cells\n"
        "  year: 2022\n"
        "Espina2021FEBJ:\n"
        "  title: Durotaxis\n"
        "  year: 2021\n")
    removed = store.prune_curated_stubs(tmp_path, dry_run=False)
    assert removed == ["Fuhs2022NatPhys"]
    from ruamel.yaml import YAML
    text = (tmp_path / "stubs.yaml").read_text()
    assert "# frontier of un-sliced containers" in text        # comment preserved
    doc = YAML(typ="safe").load(text)
    assert list(doc) == ["Espina2021FEBJ"]                      # only the still-a-stub entry remains


def test_prune_curated_stubs_dry_run_reports_focal_without_writing(tmp_path):
    (tmp_path / "curated").mkdir()  # focal file not yet on disk (dry run) -> named via extra_keys
    (tmp_path / "stubs.yaml").write_text("Fuhs2022NatPhys:\n  title: x\n  year: 2022\n")
    removed = store.prune_curated_stubs(tmp_path, dry_run=True, extra_keys=("Fuhs2022NatPhys",))
    assert removed == ["Fuhs2022NatPhys"]
    assert "Fuhs2022NatPhys" in (tmp_path / "stubs.yaml").read_text()  # nothing written


def test_write_quote_loc_round_trips_and_preserves_comments(tmp_path):
    p = _paper(tmp_path)
    store.write_quote_loc(tmp_path, "Chen2021Sys", "c2", 3, [[0.1, 0.2, 0.5, 0.23], [0.1, 0.24, 0.3, 0.27]])
    text = p.read_text()
    assert "# a hand-authored curated file" in text          # comment preserved
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load(text)
    c2 = next(s for s in doc["claims"] if s["id"] == "c2")
    assert c2["quote_loc"] == {"page": 3, "rects": [[0.1, 0.2, 0.5, 0.23], [0.1, 0.24, 0.3, 0.27]]}
    assert "quote_loc" not in next(s for s in doc["claims"] if s["id"] == "c1")  # only the target changed


def test_write_quote_loc_lands_immediately_after_quote(tmp_path):
    # quote_loc must sit right after `quote`, not at the tail of the mapping (behind whatever
    # other keys the slice happens to carry) — that tail position is exactly what let a
    # trailing comment silently re-parent it (see the trap test below).
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Chen2021Sys.yaml"
    p.write_text(
        "claims:\n"
        '  - {id: c1, text: "t", quote: "throughput increased monotonically", '
        "grounded_in: [m1], leads_to: [x]}\n")
    store.write_quote_loc(tmp_path, "Chen2021Sys", "c1", 2, [[0.0, 0.0, 0.1, 0.1]])
    text = p.read_text()
    i_quote, i_loc, i_ground = text.index("quote:"), text.index("quote_loc:"), text.index("grounded_in:")
    assert i_quote < i_loc < i_ground        # quote_loc wedged between quote and the next key


def test_write_quote_loc_avoids_the_silent_reparenting_trap(tmp_path):
    # Reproduces the real bug: a slice ends in a `note:` followed by a section-header comment.
    # The OLD behaviour (append quote_loc at the tail of the mapping) put quote_loc textually
    # AFTER that comment; when a curator later inserts a new slice "above" the comment — the
    # natural place to add content to that section — the orphaned quote_loc block silently
    # re-parents onto the newly-last slice instead of staying with c6. Placing quote_loc right
    # after `quote` (well before `note`) makes that insertion point irrelevant to it.
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Trap2020Jour.yaml"
    p.write_text(
        "# curated paper — comments must survive a write-back\n"
        'title: "T"\n'
        "type: original\n"
        "claims:\n"
        "  - id: c6\n"
        '    text: "some claim"\n'
        '    quote: "verbatim sentence"\n'
        "    note: >-\n"
        "      some curator note\n"
        "\n"
        "  # ─── Intro · section header comment\n"
        "  - id: c7\n"
        '    text: "another"\n'
        '    quote: "another quote"\n')

    store.write_quote_loc(tmp_path, "Trap2020Jour", "c6", 1, [[0.1, 0.2, 0.5, 0.23]])
    text = p.read_text()
    assert "# ─── Intro · section header comment" in text                 # comment preserved
    assert text.index("quote_loc:") < text.index("note:")                 # wedged before note,
    assert text.index("quote_loc:") < text.index("# ─── Intro")           # well before the comment

    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load(text)
    assert next(s for s in doc["claims"] if s["id"] == "c6")["quote_loc"]["page"] == 1
    assert "quote_loc" not in next(s for s in doc["claims"] if s["id"] == "c7")

    # Now simulate a curator inserting a new slice immediately ABOVE that comment — the
    # re-parenting trigger from the bug report.
    injected = text.replace(
        "  # ─── Intro · section header comment\n",
        "  - id: c6.5\n"
        '    text: "urgent addition"\n'
        '    quote: "urgent quote"\n'
        "\n"
        "  # ─── Intro · section header comment\n")
    p.write_text(injected)
    doc2 = YAML(typ="safe").load(p.read_text())
    by_id = {s["id"]: s for s in doc2["claims"]}
    assert by_id["c6"]["quote_loc"]["page"] == 1        # still c6's, untouched
    assert "quote_loc" not in by_id["c6.5"]             # the newly-inserted slice did NOT inherit it
    assert "quote_loc" not in by_id["c7"]


def test_write_quote_loc_replaces_an_existing_location(tmp_path):
    _paper(tmp_path)
    store.write_quote_loc(tmp_path, "Chen2021Sys", "c1", 0, [[0.0, 0.0, 0.1, 0.1]])
    store.write_quote_loc(tmp_path, "Chen2021Sys", "c1", 1, [[0.5, 0.5, 0.6, 0.6]])
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((tmp_path / "curated" / "Chen2021Sys.yaml").read_text())
    assert next(s for s in doc["claims"] if s["id"] == "c1")["quote_loc"]["page"] == 1


def test_write_quote_locs_batch(tmp_path):
    _paper(tmp_path)                                  # c1, c2
    n = store.write_quote_locs(tmp_path, "Chen2021Sys", {
        "c1": {"page": 0, "rects": [[0.0, 0.0, 0.1, 0.1]]},
        "c2": {"page": 2, "rects": [[0.1, 0.1, 0.2, 0.2]]},
        "c9": {"page": 0, "rects": [[0, 0, 1, 1]]},   # absent slice → skipped
    })
    assert n == 2
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((tmp_path / "curated" / "Chen2021Sys.yaml").read_text())
    assert next(s for s in doc["claims"] if s["id"] == "c1")["quote_loc"]["page"] == 0
    assert next(s for s in doc["claims"] if s["id"] == "c2")["quote_loc"]["page"] == 2
    assert "# a hand-authored curated file" in (tmp_path / "curated" / "Chen2021Sys.yaml").read_text()


def test_write_quote_locs_batch_also_lands_after_quote(tmp_path):
    # the batch writer (used by `lit locate`) must place quote_loc the same way as the
    # single-slice writer — this is where the real-world bug was actually triggered from.
    _paper(tmp_path)
    store.write_quote_locs(tmp_path, "Chen2021Sys", {"c2": {"page": 2, "rects": [[0.1, 0.1, 0.2, 0.2]]}})
    text = (tmp_path / "curated" / "Chen2021Sys.yaml").read_text()
    assert text.index('quote: "median latency grew"') < text.index("quote_loc:")


def test_write_quote_loc_overwrite_does_not_move_an_existing_quote_loc(tmp_path):
    # the --force path: re-locating must overwrite the value in place, not relocate the key —
    # otherwise a repeated `lit locate --force` would churn the diff for no reason.
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Chen2021Sys.yaml"
    p.write_text(
        "claims:\n"
        "  - id: c1\n"
        '    quote: "throughput increased monotonically"\n'
        "    quote_loc:\n"
        "      page: 0\n"
        "      rects: [[0.0, 0.0, 0.1, 0.1]]\n"
        "    note: >-\n"
        "      a trailing note\n")
    store.write_quote_loc(tmp_path, "Chen2021Sys", "c1", 5, [[0.5, 0.5, 0.6, 0.6]])
    text = p.read_text()
    assert text.index("quote_loc:") < text.index("note:")   # position unchanged — still before note
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load(text)
    assert doc["claims"][0]["quote_loc"]["page"] == 5


def test_write_quote_loc_errors(tmp_path):
    _paper(tmp_path)
    with pytest.raises(KeyError):
        store.write_quote_loc(tmp_path, "Chen2021Sys", "c9", 0, [[0, 0, 1, 1]])
    with pytest.raises(FileNotFoundError):
        store.write_quote_loc(tmp_path, "Nope2020Xyz", "c1", 0, [[0, 0, 1, 1]])


def _load(path):
    from ruamel.yaml import YAML
    return YAML(typ="safe").load(path.read_text())


def test_edit_tags_add_dedupes_and_preserves_comments(tmp_path):
    p = _paper(tmp_path)
    assert store.edit_tags(tmp_path, "Chen2021Sys", ["batching", "throughput"]) == ["batching", "throughput"]
    # adding again de-dupes (order-preserving) and appends only the new one
    assert store.edit_tags(tmp_path, "Chen2021Sys", ["batching", "queueing"]) == \
        ["batching", "throughput", "queueing"]
    assert _load(p)["tags"] == ["batching", "throughput", "queueing"]
    assert "# a hand-authored curated file" in p.read_text()      # comment survives


def test_edit_tags_inserts_before_authors(tmp_path):
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "X2020Jrnl.yaml"
    p.write_text('title: "T"\ntype: original\nauthors: [{name: "A, B"}]\n')
    store.edit_tags(tmp_path, "X2020Jrnl", ["foo"])
    text = p.read_text()
    assert text.index("tags:") < text.index("authors:")


def test_edit_tags_remove_and_drop_key(tmp_path):
    p = _paper(tmp_path)
    store.edit_tags(tmp_path, "Chen2021Sys", ["a", "b"])
    assert store.edit_tags(tmp_path, "Chen2021Sys", ["a"], remove=True) == ["b"]
    # removing the last tag drops the key entirely
    assert store.edit_tags(tmp_path, "Chen2021Sys", ["b"], remove=True) == []
    assert "tags" not in _load(p)


def test_edit_tags_list_only_and_no_op_do_not_write(tmp_path):
    p = _paper(tmp_path)
    before = p.read_text()
    assert store.edit_tags(tmp_path, "Chen2021Sys", []) == []          # list-only on a tagless paper
    assert p.read_text() == before                                    # untouched
    store.edit_tags(tmp_path, "Chen2021Sys", ["a"])
    mid = p.read_text()
    assert store.edit_tags(tmp_path, "Chen2021Sys", ["a"]) == ["a"]     # re-add same → no change
    assert p.read_text() == mid                                       # not rewritten
    assert store.edit_tags(tmp_path, "Chen2021Sys", []) == ["a"]        # list-only reports current


def test_edit_tags_missing_paper_errors(tmp_path):
    (tmp_path / "curated").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        store.edit_tags(tmp_path, "Nope2020Xyz", ["a"])


def _oa_by_doi(mapping):
    """A minimal OpenAlex stand-in: filter=doi:… -> works assembled from `mapping` (doi -> raw)."""
    from urllib.parse import unquote

    from litgraph.sources.openalex import OpenAlex

    def get_json(url: str) -> dict:
        got = unquote(url.split("filter=doi:", 1)[1].split("&", 1)[0])
        return {"results": [mapping[d] for d in got.split("|") if d in mapping]}

    return OpenAlex(mailto="t@e", get_json=get_json)


def _raw(doi, names, venue):
    return {"id": f"https://openalex.org/W{abs(hash(doi)) % 10**6}", "doi": f"https://doi.org/{doi}",
            "title": "x", "publication_year": 2020, "type": "article",
            "authorships": [{"author": {"display_name": n}} for n in names],
            "primary_location": {"source": {"display_name": venue}}, "referenced_works": []}


def test_enrich_stubs_backfills_authors_and_journal(tmp_path):
    (tmp_path / "stubs.yaml").write_text(
        "# frontier\n"
        "Schwarz2015BBA:\n"
        "  title: Traction force microscopy\n"
        "  year: 2015\n"
        "  doi: 10.1/bba\n"
        "Nodoi2019X:\n"
        "  title: No identifier here\n"
        "  year: 2019\n")
    oa = _oa_by_doi({"10.1/bba": _raw("10.1/BBA", ["Ulrich S. Schwarz", "Jérôme R. D. Soiné"],
                                      "Biochim. Biophys. Acta")})
    res = store.enrich_stubs(tmp_path, oa)

    assert res.enriched == ["Schwarz2015BBA"]
    assert res.no_doi == ["Nodoi2019X"]
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((tmp_path / "stubs.yaml").read_text())
    assert doc["Schwarz2015BBA"]["authors"] == ["Ulrich S. Schwarz", "Jérôme R. D. Soiné"]
    assert doc["Schwarz2015BBA"]["journal"] == "Biochim. Biophys. Acta"
    assert "# frontier" in (tmp_path / "stubs.yaml").read_text()   # comments survive


def test_enrich_stubs_skips_complete_unless_forced(tmp_path):
    (tmp_path / "stubs.yaml").write_text(
        "Done2015BBA:\n"
        "  title: t\n"
        "  authors: [Old Name]\n"
        "  journal: Old Journal\n"
        "  doi: 10.1/bba\n")
    oa = _oa_by_doi({"10.1/bba": _raw("10.1/bba", ["New Name"], "New Journal")})

    res = store.enrich_stubs(tmp_path, oa)
    assert res.already == ["Done2015BBA"] and res.enriched == []

    res2 = store.enrich_stubs(tmp_path, oa, force=True)
    assert res2.enriched == ["Done2015BBA"]
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((tmp_path / "stubs.yaml").read_text())
    assert doc["Done2015BBA"]["authors"] == ["New Name"]
    assert doc["Done2015BBA"]["journal"] == "New Journal"


def test_enrich_stubs_dry_run_writes_nothing(tmp_path):
    before = ("One2015BBA:\n  title: t\n  doi: 10.1/bba\n")
    (tmp_path / "stubs.yaml").write_text(before)
    oa = _oa_by_doi({"10.1/bba": _raw("10.1/bba", ["A Name"], "A Journal")})
    res = store.enrich_stubs(tmp_path, oa, dry_run=True)
    assert res.enriched == ["One2015BBA"]
    assert (tmp_path / "stubs.yaml").read_text() == before   # untouched


# --- healing an unquoted sharpened ref on write (the actual outage) ------------------------
#
# graph.py loads with the strict `typ="safe"` parser (libyaml); this module writes with the
# lax round-trip parser. In a flow sequence the round-trip parser accepts a plain scalar
# carrying a `:` (a sharpened cross-paper ref, `Key2026Journal:c4`) that the safe parser
# rejects outright — so a curator's hand edit that leaves such a ref unquoted produces a file
# this tool can write but not read back. These tests confirm that any store.py write which
# round-trips a curated paper's full document heals that ref in passing, not just the writer
# that happens to be setting the field.

def test_write_quote_loc_quotes_a_preexisting_unquoted_sharpened_ref(tmp_path):
    # write_quote_loc only means to set c1's quote_loc; it round-trips the whole document, so
    # the unquoted ref sitting right next to it must not ride along unfixed.
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Chen2021Sys.yaml"
    p.write_text(
        "claims:\n"
        '  - id: c1\n'
        '    text: "t"\n'
        '    quote: "throughput increased monotonically"\n'
        "    corroborates: [Other2026Journal:c4]\n"
    )
    store.write_quote_loc(tmp_path, "Chen2021Sys", "c1", 2, [[0.1, 0.1, 0.2, 0.2]])
    assert 'corroborates: ["Other2026Journal:c4"]' in p.read_text()

    from litgraph.graph import load_yaml
    doc = load_yaml(p)                                          # the safe loader — used to abort on this file
    assert doc["claims"][0]["corroborates"] == ["Other2026Journal:c4"]


def test_edit_tags_also_heals_an_unrelated_slices_unquoted_ref(tmp_path):
    # The healing isn't special-cased to write_quote_loc — any full-document round-trip does it.
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Chen2021Sys.yaml"
    p.write_text(
        'title: "T"\n'
        "type: original\n"
        "claims:\n"
        '  - id: c1\n    text: "t"\n    contradicts: [Bad2020Journal:c9]\n'
    )
    store.edit_tags(tmp_path, "Chen2021Sys", ["batching"])
    from litgraph.graph import load_yaml
    assert load_yaml(p)["claims"][0]["contradicts"] == ["Bad2020Journal:c9"]


def test_write_abstract_also_heals_an_unrelated_slices_unquoted_ref(tmp_path):
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Chen2021Sys.yaml"
    p.write_text(
        'title: "T"\ntype: original\n'
        "claims:\n"
        '  - id: c1\n    text: "t"\n    corroborates: [Other2026Journal:c4]\n'
    )
    store.write_abstract(tmp_path, "Chen2021Sys", "an abstract")
    from litgraph.graph import load_yaml
    assert load_yaml(p)["claims"][0]["corroborates"] == ["Other2026Journal:c4"]


def test_sharpened_ref_survives_a_store_write_and_the_safe_loader_reads_it_back(tmp_path):
    """The property that matters end to end: anything the writer produces, the reader can
    read. A curated file carrying sharpened refs (the only way they enter curated YAML today
    — CuratedPaper.to_yaml has no affirmations yet, SCHEMA §4, so this is a hand-authored
    file standing in for one), touched by a store.py writer, must come back byte-for-value
    identical through graph.load_yaml — including a ref store.py never even looked at."""
    (tmp_path / "curated").mkdir(parents=True)
    p = tmp_path / "curated" / "Kumar2020Net.yaml"
    p.write_text(
        "claims:\n"
        '  - id: c1\n'
        '    text: "latency falls"\n'
        '    quote: "median latency fell"\n'
        "    corroborates: [Ruppel2026NatPhys:c4, Chen2021Sys:c2]\n"
        "    leads_to: [batching-improves-throughput]\n"   # a broad slug, no colon — must stay untouched
    )
    store.write_quote_locs(tmp_path, "Kumar2020Net", {"c1": {"page": 1, "rects": [[0.0, 0.0, 1.0, 1.0]]}})

    from litgraph.graph import load_yaml
    c1 = load_yaml(p)["claims"][0]
    assert c1["corroborates"] == ["Ruppel2026NatPhys:c4", "Chen2021Sys:c2"]
    assert c1["leads_to"] == ["batching-improves-throughput"]
    assert c1["quote_loc"]["page"] == 1
