"""Tests that detect ownership errors even when equal words cancel in Counters."""

from collections import Counter

import pytest
from pydantic import ValidationError

from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check
from book_core.ledger.records import NodeAssignment, WordLedger
from book_core.ledger.tokenization import line_tokens, token_counter
from book_core.model.document import Document
from book_core.model.spans import TextSpan


def test_exact_unicode_benchmark_tokenization(make_page):
    assert token_counter("\uff21 A a \ufb01 \u00bd a\u00f1o e\u0301") == Counter(
        ["A", "A", "a", "fi", "1", "2", "a\u00f1o", "\u00e9"],
    )
    page = make_page(("A", "\u030a", " \ufb01 ", "\u00bd"))
    document, ledger = provision_page(page)
    assert check(document, ledger, Counter(["\u00c5", "fi", "1", "2"])).passing
    occurrence = list(line_tokens(page.store, page.store.lines[0]))[0]
    assert set(occurrence.span_ids) == {"span-0", "span-1"}
    assert page.store.spans["span-1"].raw_text == "\u030a"


def test_missing_unknown_and_duplicate_occurrences(make_page):
    document, ledger = provision_page(make_page(("same same",)))
    # Duplicate one occurrence while losing another: value Counters alone would pass.
    forged = WordLedger(assignments=[ledger.assignments[0], ledger.assignments[0]])
    report = check(document, forged)
    assert report.missing_token_count == report.extra_token_count == 0
    assert not report.passing
    assert any("assignments" in error for error in report.ownership_errors)
    missing = check(document, WordLedger())
    assert missing.missing_token_count == 2
    extra = ledger.model_copy(
        update={
            "assignments": [
                *ledger.assignments,
                NodeAssignment(token_id="unknown", node_id="unknown"),
            ],
        }
    )
    assert check(document, extra).extra_token_count == 1


def test_realized_node_content_not_merely_ledger_counter(make_page):
    document, ledger = provision_page(make_page(("a ", "b")))
    payload = document.model_dump()
    payload["body_matter"]["children"][0]["content"].reverse()
    changed = Document.model_validate(payload)
    report = check(changed, ledger)
    assert not report.passing
    assert report.retained_missing_token_count == 2
    assert report.retained_extra_token_count == 1


def test_only_trimbox_discard_allowed(make_page):
    document, ledger = provision_page(make_page(("footer words",), outside=True))
    report = check(document, ledger, Counter())
    assert report.passing and report.discard_token_count == 2
    assert not document.body_matter.children
    assert len(document.span_store.spans) == 1
    with pytest.raises(ValidationError):
        type(ledger.discards[0])(**{**ledger.discards[0].model_dump(), "reason_code": "furniture"})
    assert not check(document, ledger.model_copy(update={"discards": []})).passing
    retained, retained_ledger = provision_page(make_page(("footer words",)))
    assert check(retained, retained_ledger).node_token_count == 2


def test_span_normalization_must_match_original(make_page):
    span = next(iter(make_page().store.spans.values()))
    with pytest.raises(ValidationError, match="Normalized"):
        TextSpan.model_validate({**span.model_dump(), "text": "different"})
