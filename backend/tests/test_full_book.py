"""Optional available full-book gate; external paths remain test-only."""

import json

import pytest
from conftest import ROOT, reference_path

from book_core.cli import ledger_check
from book_core.evaluation.cached_benchmark import CachedBenchmark
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

SOURCE = reference_path("spanish_pdf")
OLD = reference_path("spanish_cache")


@pytest.mark.full_book
def test_full_available_book():
    if not SOURCE.exists() or not (OLD / "manifest.json").exists():
        pytest.skip("Original full book and independent extraction cache unavailable")
    extractor = CachedExtractor(PyMuPDFExtractor(), ROOT / "experiments/out/step2/page_cache")
    result = ledger_check(SOURCE, extractor, CachedBenchmark(OLD))
    assert result["passing"], result["failures"]
    assert result["pages"] == 758
    assert result["node_token_count"] == 495751
    assert result["source_line_count"] == 92228
    assert result["excluded_line_count"] == 7194
    assert result["retained_line_count"] == 85034
    assert result["expected_missing_token_count"] == result["expected_extra_token_count"] == 0
    out = ROOT / "experiments/out/step4a"
    out.mkdir(parents=True, exist_ok=True)
    (out / "full_book.json").write_text(json.dumps(result, indent=2) + "\n", "utf-8")
