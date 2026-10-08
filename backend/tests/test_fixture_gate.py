"""Seven Spanish regressions compare complete token multisets against frozen old evidence."""

import hashlib
import json
from collections import Counter

import pytest
from conftest import ROOT

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check
from book_core.model.document import Document

CASES = json.loads((ROOT / "backend/tests/fixtures/expected_counters.json").read_text("utf-8"))[
    "cases"
]


@pytest.mark.parametrize("case", CASES, ids=[case["fixture"] for case in CASES])
def test_seven_fixture_gate(case):
    source = ROOT / "experiments/fixtures" / f"{case['fixture']}.pdf"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == case["fixture_sha256"]
    pages = list(PyMuPDFExtractor().extract_pages(source))
    assert len(pages) == 1
    document, ledger = provision_page(pages[0])
    expected = Counter(case["counter"])
    result = check(document, ledger, expected)
    assert result.passing, result.model_dump()
    assert result.node_token_count == case["expected_retained_tokens"]
    assert result.expected_missing_token_count == result.expected_extra_token_count == 0
    assert {node.type for node in document.body_matter.children} == {"inline_run"}
    assert all(
        discard.reason == "Outside explicit PDF TrimBox; retained in raw evidence."
        for discard in ledger.discards
    )
    restored = Document.model_validate_json(document.model_dump_json())
    assert restored == document
    assert check(restored, ledger, expected).passing
