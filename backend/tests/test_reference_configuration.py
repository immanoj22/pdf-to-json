"""External reference paths are configured, while local fixtures remain portable."""

import ast

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
