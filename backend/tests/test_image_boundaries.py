"""Regression: native image blocks affect text segmentation even in a text-only store."""

import hashlib
import json
from collections import Counter

import pymupdf
import pytest
from conftest import ROOT

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check

CASES = json.loads(
    (ROOT / "backend/tests/fixtures/image_boundary_manifest.json").read_text("utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["fixture"] for case in CASES])
def test_native_image_boundaries_remain_in_text_extraction(case):
    path = ROOT / "backend/tests/fixtures" / case["fixture"]
    page = list(PyMuPDFExtractor().extract_pages(path))[0]
    truth = json.loads(
        (ROOT / "backend/tests/fixtures/image_boundary_expected_counters.json").read_text("utf-8")
    )["cases"][case["fixture"]]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == truth["fixture_sha256"]
    document, ledger = provision_page(page)
    result = check(document, ledger, Counter(truth["counter"]))
    assert result.passing, result.model_dump()
    assert result.expected_missing_token_count == result.expected_extra_token_count == 0
    assert result.node_token_count == truth["expected_retained_tokens"]
    lines = [page.store.raw_line_text(line) for line in page.store.lines]
    assert all(label in lines for label in case["separate_labels"])
    assert case["fused_label"] not in lines
    assert page.extractor.configuration["preserve_images"] is True
    with pymupdf.open(path) as pdf:
        raw = pdf[0].get_text(
            "rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
        )
    dropped_lines = [
        "".join(char["c"] for span in line["spans"] for char in span["chars"])
        for block in raw["blocks"]
        if block["type"] == 0
        for line in block["lines"]
    ]
    assert case["fused_label"] in dropped_lines
