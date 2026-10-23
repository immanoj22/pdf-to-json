"""OCR span store and confidence records; the native span store is never rewritten."""

import math
import unicodedata
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from book_core.extraction.fingerprints import stable_id
from book_core.extraction.rasters import RasterPage
from book_core.model.common import BBox, Confidence, CoreModel, Digest, Identifier, Provenance
from book_core.model.spans import ExtractedPage, ExtractorIdentity, SourceLine, SpanStore, TextSpan
from book_core.ocr.engines import OcrReading
from book_core.ocr.geometry import pixel_box_to_pdf
from book_core.ocr.settings import Calibration


class OcrWordEvidence(CoreModel):
    span_id: Identifier
    source: Literal["ocr"] = "ocr"
    engine: str
    language: str
    confidence: Confidence
    line_confidence: Confidence
    granularity: Literal["word", "line"] = "word"
    raw_confidence: float | None = None
    review_status: Literal["needs_review"] | None = None
    alternatives: list[dict] = Field(default_factory=list)
    separator_inferred: bool = False
    region_index: int = 0
    origin: tuple[float, float]
    direction: tuple[float, float]
    writing_mode: Literal["horizontal", "vertical"] = "horizontal"


class OcrPage(CoreModel):
    """All OCR text lives in ``page.store``; records reference spans, never copy it."""

    source: Literal["ocr"] = "ocr"
    page: ExtractedPage
    words: list[OcrWordEvidence]
    mean_confidence: Confidence | None
    review_status: Literal["needs_review", "must_check"] | None
    calibration: Calibration | None
    orientation: dict
    transform: dict
    warnings: list[str]
    model_fingerprints: dict[str, str]
    unmatched_secondary: list[dict] = Field(default_factory=list)
    raster_asset: str | None = None
    raster_sha256: Digest | None = None

    @model_validator(mode="after")
    def consistent(self):
        ids = [word.span_id for word in self.words]
        if len(ids) != len(set(ids)) or set(ids) != set(self.page.store.spans):
            raise ValueError("Every OCR word must name exactly one stored OCR span")
        if any(s.provenance.method != "ocr" for s in self.page.store.spans.values()):
            raise ValueError("OCR source must never contain native-marked text")
        if (self.raster_asset is None) != (self.raster_sha256 is None):
            raise ValueError("OCR raster name and checksum must be present together")
        if self.raster_asset and Path(self.raster_asset).name != self.raster_asset:
            raise ValueError("OCR raster asset must be a file name")
        if not self.words and self.review_status != "must_check":
            raise ValueError("An OCR result with no words requires a page check")
        return self


def disagrees(word):
    """The second reader read the word differently (an agreeing reading is no flag)."""
    text = unicodedata.normalize("NFKC", word.text)
    return any(unicodedata.normalize("NFKC", a.text) != text for a in word.alternatives)


def page_status(confidences, calibration):
    """must_check with no words, or when the share of words below the word threshold reaches
    the page threshold; needs_review without a calibration; else None."""
    if not confidences:
        return "must_check"
    if calibration is None:
        return "needs_review"
    flagged = sum(c < calibration.word_threshold for c in confidences) / len(confidences)
    return "must_check" if flagged >= calibration.page_threshold else None


def _box_union(boxes):
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def _separator(left, right):
    # No inserted spaces between Han/kana words; this does not change ledger token rules.
    def no_space(character):
        return any(
            name in unicodedata.name(character, "") for name in ("CJK", "HIRAGANA", "KATAKANA")
        )

    return "" if no_space(left.text[-1:]) and no_space(right.text[:1]) else " "


def _point(reading, raster, x, y):
    a, b, c, d, e, f = reading.transform.source_to_processed
    determinant = a * e - b * d
    return (
        ((e * (x - c) - b * (y - f)) / determinant) * raster.page_width / raster.width,
        ((a * (y - f) - d * (x - c)) / determinant) * raster.page_height / raster.height,
    )


def build_ocr_page(
    native: ExtractedPage,
    raster: RasterPage,
    reading: OcrReading,
    key: str,
    calibration: Calibration | None = None,
) -> OcrPage:
    """Map through orientation/deskew back to PDF coordinates in engine evidence order."""
    identity = ExtractorIdentity(
        name=reading.engine,
        version=reading.version,
        configuration={"source": "ocr", "cache_key": key},
    )
    provenance = Provenance(
        source_sha256=native.source_sha256,
        engine=reading.engine,
        engine_version=reading.version,
        method="ocr",
        resolved_device=reading.execution_device,
        execution_device=reading.execution_device,
        notes=["Font size estimated from OCR line height; no native font evidence"],
    )
    grouped = OrderedDict()
    uncalibrated_lines = any(w.text and w.granularity == "line" for w in reading.words)
    if uncalibrated_lines:
        calibration = None
    for word in reading.words:
        if word.text:
            grouped.setdefault(word.line_key, []).append(word)
    spans, lines, evidence = {}, [], []
    for index, members in enumerate(grouped.values()):
        line_id = stable_id(native.source_sha256, key, native.geometry.page, "ocr-line", index)
        boxes = [pixel_box_to_pdf(reading.transform, w.pixel_bbox, raster) for w in members]
        line_box = _box_union(boxes)
        p0, p1, pn = (_point(reading, raster, x, y) for x, y in ((0, 0), (1, 0), (0, 1)))
        vector = (p1[0] - p0[0], p1[1] - p0[1])
        length = math.hypot(*vector)
        direction = (vector[0] / length, vector[1] / length)
        line_height = max(w.pixel_bbox[3] for w in members) - min(w.pixel_bbox[1] for w in members)
        estimated_size = line_height * math.hypot(pn[0] - p0[0], pn[1] - p0[1])
        span_ids = []
        for word_index, (word, box) in enumerate(zip(members, boxes, strict=True)):
            sid = stable_id(line_id, "word", word_index)
            separator = (
                _separator(word, members[word_index + 1]) if word_index + 1 < len(members) else ""
            )
            raw = word.text + separator
            spans[sid] = TextSpan(
                id=sid,
                line_id=line_id,
                page=native.geometry.page,
                raw_text=raw,
                text=unicodedata.normalize("NFKC", raw),
                bbox=box,
                font="unknown",
                size=estimated_size,
                color=0,
                flags=0,
                language=word.language,
                script=word.script,
                text_direction=word.text_direction,
                provenance=provenance,
            )
            span_ids.append(sid)
            evidence.append(
                OcrWordEvidence(
                    span_id=sid,
                    engine=reading.engine,
                    language=word.language,
                    confidence=word.confidence,
                    line_confidence=word.line_confidence,
                    granularity=word.granularity,
                    raw_confidence=word.raw_confidence,
                    review_status="needs_review"
                    if calibration is None
                    or word.confidence < calibration.word_threshold
                    or disagrees(word)
                    else None,
                    alternatives=[asdict(a) for a in word.alternatives],
                    separator_inferred=bool(separator),
                    origin=_point(reading, raster, word.pixel_bbox[0], word.pixel_bbox[3]),
                    direction=direction,
                )
            )
        lines.append(
            SourceLine(id=line_id, page=native.geometry.page, bbox=line_box, span_ids=span_ids)
        )
    mean = reading.mean_confidence
    status = page_status([w.confidence for w in reading.words if w.text], calibration)
    if uncalibrated_lines:
        status = "must_check"
    return OcrPage(
        page=ExtractedPage(
            source_sha256=native.source_sha256,
            extractor=identity,
            geometry=native.geometry,
            store=SpanStore(spans=spans, lines=lines),
        ),
        words=evidence,
        mean_confidence=mean,
        review_status=status,
        calibration=calibration,
        orientation=asdict(reading.orientation),
        transform=asdict(reading.transform),
        warnings=list(reading.warnings) + (
            ["Line-level OCR scores are not word-calibrated; check the page image"]
            if uncalibrated_lines else []
        ),
        model_fingerprints=dict(reading.model_fingerprints),
        unmatched_secondary=[asdict(w) for w in reading.unmatched_secondary],
    )
