"""Per-page inputs of the furniture stage: native page, Step 4 layout and Step 7 reading order.

Cached layouts and orders are read directly by their fingerprints (checksummed, as written by
their producers), so a whole-book pass does not reload each page's object analysis. On any cache
miss the unchanged Step 7 entry point computes (and caches) the page. Native pages come through
the Extractor interface, and every layout span must exist in the page's span store.
"""

from __future__ import annotations

from pathlib import Path

from book_core.extraction.fingerprints import source_digest
from book_core.layout.models import PageLayout
from book_core.layout.pipeline import layout_fingerprint
from book_core.objects.analysis import fingerprints, verified_read
from book_core.reading_order.cache import analyze_reading_order, order_fingerprint
from book_core.reading_order.models import PageReadingOrder


def _cached(path, model, fingerprint, digest, number):
    if not path.exists():
        return None
    value = verified_read(path, model, fingerprint)
    if value.source_sha256 != digest or value.page != number:
        raise ValueError(f"{model.__name__} cache belongs to another source or page")
    return value


class PageInputs:
    """(layout, order) per native page of one source; keys are computed once per book."""

    def __init__(self, source, extractor, repetition, cache_dir, vocabulary):
        self.source = Path(source)
        self.extractor, self.repetition = extractor, repetition
        self.cache_dir, self.vocabulary = Path(cache_dir), vocabulary
        self.digest = source_digest(self.source)
        _, analysis_key = fingerprints(self.digest, extractor, repetition)
        self.layout_key = layout_fingerprint(analysis_key, extractor.device.resolved)
        self.order_key = order_fingerprint(self.layout_key, vocabulary)

    def __call__(self, page):
        number = page.geometry.page
        if page.source_sha256 != self.digest:
            raise ValueError("Native page belongs to another source")
        root = self.cache_dir
        layout = _cached(
            root / "layout" / self.layout_key / f"{number}.json",
            PageLayout,
            self.layout_key,
            self.digest,
            number,
        )
        order = _cached(
            root / "reading_order" / self.order_key / f"{number}.json",
            PageReadingOrder,
            self.order_key,
            self.digest,
            number,
        )
        if layout is None or order is None:
            order, layout, analysis = analyze_reading_order(
                self.source, number, self.extractor, self.repetition, root, self.vocabulary
            )
            if analysis.native.page.model_dump() != page.model_dump():
                raise ValueError("Native page differs from the page the layout was built from")
        spans = page.store.spans
        if any(span not in spans for line in layout.lines for span in line.span_ids):
            raise ValueError(f"Layout of page {number} references spans missing from the page")
        return layout, order
