# tests/test_config.py
"""config.toml round-trip: the `[curation] active` worklist writer (the "move")."""
from litgraph.config import load_config, set_active


def test_set_active_creates_file_table_and_array(tmp_path):
    # a repo with no config.toml at all: the first move authors the whole thing
    active = set_active(tmp_path, "Chen2021Sys", True)
    assert active == ("Chen2021Sys",)
    assert load_config(tmp_path).active == ("Chen2021Sys",)


def test_set_active_add_is_idempotent(tmp_path):
    set_active(tmp_path, "Chen2021Sys", True)
    active = set_active(tmp_path, "Chen2021Sys", True)      # already there → no duplicate
    assert active == ("Chen2021Sys",)


def test_set_active_remove_and_remove_absent(tmp_path):
    set_active(tmp_path, "Chen2021Sys", True)
    set_active(tmp_path, "Kumar2020Net", True)
    active = set_active(tmp_path, "Chen2021Sys", False)
    assert active == ("Kumar2020Net",)
    # removing one that isn't there is a no-op, not an error
    assert set_active(tmp_path, "Nope2099X", False) == ("Kumar2020Net",)


def test_set_active_preserves_existing_keys_and_comments(tmp_path):
    (tmp_path / "config.toml").write_text(
        '# my library config\n'
        'mailto = "me@example.org"  # polite pool\n'
        'pdf_dir = "/data/pdfs"\n'
    )
    set_active(tmp_path, "Chen2021Sys", True)
    text = (tmp_path / "config.toml").read_text()
    # the human's comments and other keys survive the round-trip
    assert "# my library config" in text
    assert "# polite pool" in text
    cfg = load_config(tmp_path)
    assert cfg.mailto == "me@example.org"
    assert str(cfg.pdf_dir) == "/data/pdfs"
    assert cfg.active == ("Chen2021Sys",)
