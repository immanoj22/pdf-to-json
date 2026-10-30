"""Cache and output paths stay short under any install folder (Windows' 260 characters).

Step 18: a 275-character table-reading cache path stopped a run. Paths below a cache or
output root stay within PATH_BUDGET characters, leaving room for a long install folder.
"""

from pathlib import Path
from types import SimpleNamespace

from test_continuity import _book, _run

from book_core.mathml.recognition import RecognitionCache
from book_core.tables.recognizers import ReadingCache

PATH_BUDGET = 120


def longest(root):
    return max(len(p.relative_to(root).as_posix()) for p in Path(root).rglob("*") if p.is_file())


def test_a_book_run_keeps_every_path_within_the_budget(tmp_path):
    result = _run(_book(tmp_path / "b.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    assert longest(tmp_path / "cache") <= PATH_BUDGET
    assert longest(tmp_path / "out") <= PATH_BUDGET
    assert result["output"] and result["book_json"]


def test_model_reading_caches_use_short_names(tmp_path):
    reader = SimpleNamespace(
        identity={"name": "fake"},
        read=lambda png: {"cells": []},
        recognize=lambda png: ("x", False),
        device=SimpleNamespace(model_dump=lambda: {}),
    )
    tables = ReadingCache(reader, tmp_path / "t")
    formulas = RecognitionCache(reader, tmp_path / "f")
    assert tables.read(b"png") == tables.read(b"png") == {"cells": []}
    assert formulas.read(b"png")["latex"] == "x" and formulas.read(b"png")["cached"]
    assert longest(tmp_path) <= 90  # two full digests made these about 155 characters
