"""External reference paths are configured, while local fixtures remain portable."""

import ast

import pytest
from conftest import ROOT, reference_path


def test_environment_reference_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOK_CONVERTER_SPANISH_PDF", str(tmp_path / "book.pdf"))
    assert reference_path("spanish_pdf") == tmp_path / "book.pdf"


def test_reference_config_relative_paths(tmp_path, monkeypatch):
    config = tmp_path / "references.toml"
    config.write_text('[paths]\nspanish_pdf = "book.pdf"\n', "utf-8")
    monkeypatch.delenv("BOOK_CONVERTER_SPANISH_PDF", raising=False)
    monkeypatch.setenv("BOOK_CONVERTER_REFERENCE_CONFIG", str(config))
    assert reference_path("spanish_pdf") == tmp_path / "book.pdf"


def test_no_absolute_reference_paths_in_source():
    for path in (ROOT / "backend/src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not (len(node.value) > 2 and node.value[1:3] in {":/", ":\\"}), path
                assert not node.value.startswith("\\\\"), path


def test_local_config_overrides_committed_keys(tmp_path, monkeypatch):
    config = tmp_path / "references.toml"
    config.write_text('[paths]\nspanish_pdf = ""\nsmall_pdf = "small.pdf"\n', "utf-8")
    local = tmp_path / "references.local.toml"
    local.write_text('[paths]\nspanish_pdf = "private/book.pdf"\n', "utf-8")
    for key in ("SPANISH_PDF", "SMALL_PDF"):
        monkeypatch.delenv(f"BOOK_CONVERTER_{key}", raising=False)
    monkeypatch.setenv("BOOK_CONVERTER_REFERENCE_CONFIG", str(config))
    assert reference_path("spanish_pdf") == tmp_path / "private/book.pdf"
    assert reference_path("small_pdf") == tmp_path / "small.pdf"


def test_key_without_path_or_unknown_key_is_an_error(tmp_path, monkeypatch):
    config = tmp_path / "references.toml"
    config.write_text('[paths]\nspanish_pdf = ""\n', "utf-8")
    monkeypatch.delenv("BOOK_CONVERTER_SPANISH_PDF", raising=False)
    monkeypatch.setenv("BOOK_CONVERTER_REFERENCE_CONFIG", str(config))
    with pytest.raises(KeyError, match="has no path"):
        reference_path("spanish_pdf")
    (tmp_path / "references.local.toml").write_text('[paths]\nother = "x.pdf"\n', "utf-8")
    with pytest.raises(KeyError, match="Unknown reference key"):
        reference_path("other")


def test_committed_reference_config_holds_keys_only():
    import tomllib

    values = tomllib.loads((ROOT / "experiments/references.toml").read_text("utf-8"))["paths"]
    assert values and all(value == "" for value in values.values())
