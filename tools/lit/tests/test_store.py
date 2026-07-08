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


def test_write_quote_loc_errors(tmp_path):
    _paper(tmp_path)
    with pytest.raises(KeyError):
        store.write_quote_loc(tmp_path, "Chen2021Sys", "c9", 0, [[0, 0, 1, 1]])
    with pytest.raises(FileNotFoundError):
        store.write_quote_loc(tmp_path, "Nope2020Xyz", "c1", 0, [[0, 0, 1, 1]])
