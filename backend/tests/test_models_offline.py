"""Runtime model access: pinned revisions, project cache, no network in a book run."""

import ast
import re
from pathlib import Path

import book_core.book_run as book_run

MODELS = {
    "HeronDetector",
    "PPDocLayoutV3Detector",
    "PPFormulaNet",
    "TableFormerStructure",
    "TATRDetector",
}


def test_every_model_constructed_by_a_book_run_is_local_only():
    tree = ast.parse(Path(book_run.__file__).read_text("utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in MODELS
    ]
    assert {c.func.id for c in calls} == MODELS
    for call in calls:
        keywords = {k.arg: k.value for k in call.keywords}
        assert isinstance(keywords.get("local_files_only"), ast.Constant)
        assert keywords["local_files_only"].value is True, call.func.id
        assert "cache_dir" in keywords


def test_default_revisions_are_immutable_commits():
    from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector
    from book_core.mathml.recognition import PPFormulaNet
    from book_core.tables.recognizers import TableFormerStructure, TATRDetector, TATRStructure

    for kind in (
        HeronDetector,
        PPDocLayoutV3Detector,
        PPFormulaNet,
        TATRDetector,
        TATRStructure,
        TableFormerStructure,
    ):
        assert re.fullmatch(r"[0-9a-f]{40}", kind.default_revision), kind.__name__
