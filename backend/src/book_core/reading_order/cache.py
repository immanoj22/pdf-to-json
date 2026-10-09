"""Cached page reading order, keyed on the layout fingerprint and the producing code."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from book_core.caching import assert_producer_unchanged, code_digest
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.layout.pipeline import analyze_layout, layout_fingerprint
from book_core.objects.analysis import atomic_write, fingerprints, verified_read
from book_core.reading_order.builder import READING_ORDER_VERSION, build_reading_order
from book_core.reading_order.models import PageReadingOrder

LOADED_CODE_DIGEST = code_digest("reading_order")


def vocabulary_digest(vocabulary: Mapping[str, int] | None) -> str:
    if not vocabulary:
        return "no-vocabulary"
    data = json.dumps(sorted(vocabulary.items()), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def order_fingerprint(layout_key, vocabulary=None):
    return stable_id(
        layout_key,
        READING_ORDER_VERSION,
        code_digest("reading_order"),
        vocabulary_digest(vocabulary),
    )


def analyze_reading_order(
    source, page_number, extractor, repetition=None, cache_dir=None, vocabulary=None
):
    """(reading order, layout, object analysis) for one page; cached when cache_dir is set."""
    assert_producer_unchanged("reading_order", LOADED_CODE_DIGEST)
    source = Path(source)
    layout, analysis = analyze_layout(source, page_number, extractor, repetition, cache_dir)
    digest = source_digest(source)
    _, analysis_key = fingerprints(digest, extractor, repetition)
    fingerprint = order_fingerprint(
        layout_fingerprint(analysis_key, extractor.device.resolved), vocabulary
    )
    path = (
        Path(cache_dir) / "reading_order" / fingerprint / f"{page_number}.json"
        if cache_dir is not None
        else None
    )
    if path is not None and path.exists():
        order = verified_read(path, PageReadingOrder, fingerprint)
        if order.source_sha256 != digest or order.page != page_number:
            raise ValueError("Reading-order cache belongs to another source or page")
        return order, layout, analysis
    order = build_reading_order(
        layout, analysis.native.page.store, vocabulary, extractor.device.resolved
    )
    assert_producer_unchanged("reading_order", LOADED_CODE_DIGEST)
    if path is not None:
        atomic_write(path, order, fingerprint)
    return order, layout, analysis
