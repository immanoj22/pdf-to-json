"""Optional Extractor capability for resolved paint state and exact glyph suppression."""

from pathlib import Path
from typing import Protocol, runtime_checkable

import pymupdf

from book_core.extraction.interfaces import Extractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.model.spans import ExtractedPage
from book_core.paint.device import inspect_page
from book_core.paint.models import PagePaintEvidence, SpanVisibility
from book_core.paint.proof import attribute, candidates, compare_render
from book_core.run_context import open_source

VERSION = "opaque-paint-proof-1"


@runtime_checkable
class PaintExtractor(Extractor, Protocol):
    def extract_paint_evidence(
        self, source: Path, page: ExtractedPage, *, scales: tuple[int, ...]
    ) -> PagePaintEvidence: ...


class PyMuPDFPaintExtractor(PyMuPDFExtractor):
    def extract_paint_evidence(self, source, page, *, scales=(2, 4)):
        decisions, diagnostics = [], []
        with open_source(source) as document:
            pdf_page = document[page.geometry.page - 1]
            try:
                raw = pdf_page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
                events = inspect_page(pdf_page)
                matched, _ = attribute(page, raw, events)
                observations = candidates(page, matched, events)
            except (AssertionError, ValueError, RuntimeError) as error:
                observations = []
                diagnostics.append(
                    f"Paint attribution unsupported: {type(error).__name__}: {error}"
                )
            baselines = {}
            for row in observations:
                result = {}
                reason = "Cover context is unsupported; native visibility retained"
                decision, confidence = "review", 0.0
                if row["screen_candidate"]:
                    try:
                        result = compare_render(
                            pdf_page, matched[row["span_id"]], scales, baselines=baselines
                        )
                    except (AssertionError, ValueError, RuntimeError) as error:
                        result = {"valid": False}
                        reason = f"Render proof unavailable: {type(error).__name__}: {error}"
                    if result.get("valid"):
                        if result["no_pixel_change"]:
                            decision = (
                                "already_trimbox_excluded"
                                if row["trimbox_excluded"]
                                else "invisible"
                            )
                            confidence = 1.0
                            reason = "Exact glyph occurrence fully covered by later opaque paint; "
                            reason += "suppression changes zero pixels at both render resolutions"
                        else:
                            reason = (
                                "Suppression changes rendered pixels; native visibility retained"
                            )
                    elif "reason" in result:
                        reason = "Render proof unavailable: " + result["reason"]
                decisions.append(
                    SpanVisibility(
                        span_id=row["span_id"],
                        line_id=row["line_id"],
                        decision=decision,
                        confidence=confidence,
                        reason=reason,
                        needs_review=decision == "review",
                        text_paint_seqnos=sorted({g["seqno"] for g in row["glyphs"]}),
                        cover_paint_seqnos=sorted({c["seqno"] for c in row["covers"]}),
                        renders=result.get("renders", []),
                    )
                )
        return PagePaintEvidence(
            source_sha256=page.source_sha256,
            page=page.geometry.page,
            version=VERSION,
            spans=decisions,
            diagnostics=diagnostics,
        )


def capable(extractor):
    if isinstance(extractor, PaintExtractor):
        return extractor
    if type(extractor) is PyMuPDFExtractor:
        return PyMuPDFPaintExtractor(extractor.device.resolved)
    return None
