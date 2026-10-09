"""Source-referenced mathematical candidates, with explicit uncertain evidence.

The optional layout model proposes regions. Native Unicode and baseline geometry provide
additional weak candidates. Nothing builds math, changes text ownership or calls OCR.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from book_core.accuracy.cache import canonical_digest
from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.detection.models import DetectionResult
from book_core.device import DeviceResolution
from book_core.extraction.fingerprints import stable_id
from book_core.model.common import (
    BBox,
    Confidence,
    CoreModel,
    Digest,
    Identifier,
    Provenance,
    SpanRef,
)
from book_core.objects.models import NativeObjectPage

VERSION = "math-candidate-evidence-1"
LOADED_CODE_DIGEST = code_digest("accuracy")
LOADED_DETECTION_DIGEST = code_digest("detection")
_RELATIONS = frozenset("=≠≈≤≥∝≡≅∼≃≐≔")
_SCRIPT_DIGITS = frozenset("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉")


class MathEvidenceConfig(CoreModel):
    image_overlap_fraction: Confidence = 0.5
    candidate_overlap_fraction: Confidence = 0.5
    inline_extent_fraction: Confidence = 0.75
    display_symbol_fraction: Confidence = 0.4

    @model_validator(mode="after")
    def positive_fractions(self):
        if any(value <= 0 for value in self.model_dump().values()):
            raise ValueError("Math evidence fractions must be positive")
        if self.inline_extent_fraction >= 1:
            raise ValueError("Inline evidence must leave adjacent native extent")
        return self


class MathCandidate(CoreModel):
    id: Identifier
    page: PositiveInt
    bbox: BBox
    source_refs: list[SpanRef] = Field(default_factory=list)
    context_refs: list[SpanRef] = Field(default_factory=list)
    line_ids: list[Identifier] = Field(default_factory=list)
    image_object_ids: list[Identifier] = Field(default_factory=list)
    detector_region_id: Identifier | None = None
    basis: list[Identifier]
    confidence: Confidence
    source_type: Literal["digital", "image", "mixed", "uncertain"]
    source_confidence: Confidence | None = None
    presentation: Literal["inline", "display", "uncertain"] = "uncertain"
    presentation_confidence: Confidence | None = None
    glyph_evidence: dict[str, int | float]
    reasons: list[Identifier]
    review_required: Literal[True] = True

    @model_validator(mode="after")
    def unresolved_confidence(self):
        if self.source_type == "uncertain" and self.source_confidence is not None:
            raise ValueError("Uncertain source evidence has no confidence")
        if self.presentation == "uncertain" and self.presentation_confidence is not None:
            raise ValueError("Uncertain presentation evidence has no confidence")
        if self.source_type in {"digital", "mixed"} and not self.source_refs:
            raise ValueError("Native formula evidence requires source references")
        if self.source_type in {"image", "mixed"} and not self.image_object_ids:
            raise ValueError("Image formula evidence requires an observed image object")
        return self


class MathPageEvidence(CoreModel):
    source_sha256: Digest
    page: PositiveInt
    cache_key: Digest
    producer_sha256: Digest
    native_sha256: Digest
    detector_sha256: Digest
    render_sha256: Digest
    model_sha256: Digest
    configuration: MathEvidenceConfig
    runtime: dict[str, str]
    provenance: Provenance
    detector_device: DeviceResolution
    candidates: list[MathCandidate]
    retained_line_count: NonNegativeInt
    notes: list[str]


def _area(box):
    return max(0.0, box.x1 - box.x0) * max(0.0, box.y1 - box.y0)


def _intersection(left, right):
    return max(0.0, min(left.x1, right.x1) - max(left.x0, right.x0)) * max(
        0.0, min(left.y1, right.y1) - max(left.y0, right.y0)
    )


def _overlap(left, right):
    denominator = min(_area(left), _area(right))
    return _intersection(left, right) / denominator if denominator > 0 else 0.0


def _union(boxes):
    return BBox(
        x0=min(box.x0 for box in boxes),
        y0=min(box.y0 for box in boxes),
        x1=max(box.x1 for box in boxes),
        y1=max(box.y1 for box in boxes),
    )


def glyph_evidence(text: str) -> dict:
    """Unicode categories work across scripts; all counted text remains transient."""
    visible = [character for character in text if not character.isspace()]
    symbols = sum(unicodedata.category(character) == "Sm" for character in visible)
    relations = sum(character in _RELATIONS for character in visible)
    digits = sum(unicodedata.category(character) == "Nd" for character in visible)
    letters = sum(unicodedata.category(character).startswith("L") for character in visible)
    script_digits = sum(character in _SCRIPT_DIGITS for character in visible)
    return {
        "visible_characters": len(visible),
        "math_symbols": symbols,
        "relation_symbols": relations,
        "decimal_digits": digits,
        "letters": letters,
        "script_digits": script_digits,
        "unmapped_characters": sum(
            character == "\ufffd" or unicodedata.category(character) == "Co"
            for character in visible
        ),
        "symbol_fraction": (symbols + digits + script_digits) / max(1, len(visible)),
    }


def has_math_evidence(counts) -> bool:
    alphanumeric = counts["letters"] + counts["decimal_digits"]
    return bool(
        (counts["relation_symbols"] and alphanumeric)
        or (counts["math_symbols"] >= 2 and alphanumeric)
        or (counts["math_symbols"] and counts["decimal_digits"] >= 2)
        or (counts["script_digits"] and counts["letters"])
    )


def _projected_extent(box, direction):
    length = math.hypot(*direction)
    if length == 0:
        return None
    dx, dy = direction[0] / length, direction[1] / length
    values = [dx * x + dy * y for x in (box.x0, box.x1) for y in (box.y0, box.y1)]
    return min(values), max(values)


def _presentation(native, bounds, lines, counts, config):
    """Local native baseline projection avoids global axis or direction assumptions."""
    inline_support = False
    for line in lines:
        geometry = [native.span_geometry.get(sid) for sid in line.span_ids]
        directions = {item.direction for item in geometry if item is not None}
        if len(directions) != 1:
            continue
        direction = next(iter(directions))
        line_extent = _projected_extent(line.bbox, direction)
        box_extent = _projected_extent(bounds, direction)
        if line_extent is None or box_extent is None:
            continue
        full = line_extent[1] - line_extent[0]
        overlap = max(0.0, min(line_extent[1], box_extent[1]) - max(line_extent[0], box_extent[0]))
        remaining_text = any(
            not bounds.contains_center(native.page.store.spans[sid].bbox)
            and any(character.isalpha() for character in native.page.store.spans[sid].raw_text)
            for sid in line.span_ids
        )
        if full > 0 and overlap / full < config.inline_extent_fraction and remaining_text:
            inline_support = True
    if inline_support:
        return "inline", 0.65, ["partial_native_line_with_adjacent_text"]
    if (
        lines
        and counts["relation_symbols"] + counts["math_symbols"] > 0
        and counts["symbol_fraction"] >= config.display_symbol_fraction
    ):
        return "display", 0.55, ["isolated_dense_symbol_line_candidate"]
    return "uncertain", None, ["presentation_not_established"]


def _make_candidate(native, detection, bounds, identifier, basis, confidence, config):
    page = native.page
    lines = [
        line
        for line in page.store.lines
        if page.geometry.content_bbox.contains_center(line.bbox)
        and _overlap(line.bbox, bounds) >= config.candidate_overlap_fraction
    ]
    span_ids = [
        sid
        for line in lines
        for sid in line.span_ids
        if _overlap(page.store.spans[sid].bbox, bounds) >= config.candidate_overlap_fraction
        and page.store.spans[sid].raw_text.strip()
    ]
    # Native stored text is resolved only for numeric evidence, never copied into output.
    text = "\n".join(page.store.spans[sid].raw_text for sid in span_ids)
    counts = glyph_evidence(text)
    images = [
        item
        for item in native.objects
        if item.kind == "image"
        and item.bbox is not None
        and _overlap(item.bbox, bounds) >= config.image_overlap_fraction
    ]
    usable_native = counts["visible_characters"] > counts["unmapped_characters"]
    if usable_native and images:
        source_type, source_confidence = "mixed", 0.7
    elif usable_native:
        source_type, source_confidence = "digital", 0.8
    elif images:
        source_type, source_confidence = "image", 0.7
    else:
        source_type, source_confidence = "uncertain", None
    presentation, presentation_confidence, reasons = _presentation(
        native, bounds, lines, counts, config
    )
    if not span_ids:
        reasons.append("native_text_unavailable")
    if images:
        reasons.append("native_image_overlap")
    if basis == ["native_math_glyphs"]:
        reasons.append("unicode_math_candidate_may_be_prose_or_label")
    return MathCandidate(
        id=identifier,
        page=page.geometry.page,
        bbox=bounds,
        source_refs=[SpanRef(span_id=sid) for sid in span_ids],
        context_refs=[SpanRef(span_id=sid) for line in lines for sid in line.span_ids],
        line_ids=[line.id for line in lines],
        image_object_ids=[item.id for item in images],
        detector_region_id=detection,
        basis=basis,
        confidence=confidence,
        source_type=source_type,
        source_confidence=source_confidence,
        presentation=presentation,
        presentation_confidence=presentation_confidence,
        glyph_evidence=counts,
        reasons=reasons,
    )


def analyze_math_page(
    native: NativeObjectPage,
    detection: DetectionResult,
    *,
    render_sha256: str,
    model_sha256: str,
    config: MathEvidenceConfig | None = None,
) -> MathPageEvidence:
    """Observations only; neither native objects nor their text store is mutated."""
    assert_producer_unchanged("accuracy", LOADED_CODE_DIGEST)
    assert_producer_unchanged("detection", LOADED_DETECTION_DIGEST)
    config = config or MathEvidenceConfig()
    page = native.page
    if detection.source_sha256 != page.source_sha256 or detection.page != page.geometry.page:
        raise ValueError("Math detector and native evidence belong to different source pages")
    if not native.span_geometry and page.store.spans:
        raise ValueError("Math evidence requires native writing-frame geometry")
    native_digest = canonical_digest(native.model_dump(mode="json"))
    detector_digest = canonical_digest(detection.model_dump(mode="json"))
    runtime = runtime_versions()
    fingerprint = canonical_digest(
        {
            "version": VERSION,
            "source_sha256": page.source_sha256,
            "native_sha256": native_digest,
            "detector_sha256": detector_digest,
            "render_sha256": render_sha256,
            "model_sha256": model_sha256,
            "config": config.model_dump(),
            "runtime": runtime,
            "producer_sha256": code_digest("accuracy"),
            "detector_producer_sha256": code_digest("detection"),
        }
    )
    candidates = []
    retained = [
        line for line in page.store.lines if page.geometry.content_bbox.contains_center(line.bbox)
    ]
    for region in detection.regions:
        if region.raw_label.casefold() != "formula":
            continue
        if not page.geometry.content_bbox.contains_center(region.bbox):
            continue
        candidates.append(
            _make_candidate(
                native,
                region.id,
                region.bbox,
                region.id,
                ["heron_formula"],
                region.confidence,
                config,
            )
        )
    for line in retained:
        counts = glyph_evidence(page.store.raw_line_text(line))
        if not has_math_evidence(counts):
            continue
        math_spans = [
            page.store.spans[sid]
            for sid in line.span_ids
            if has_math_evidence(glyph_evidence(page.store.spans[sid].raw_text))
        ]
        bounds = _union([span.bbox for span in math_spans]) if math_spans else line.bbox
        if any(
            _overlap(candidate.bbox, bounds) >= config.candidate_overlap_fraction
            for candidate in candidates
        ):
            continue
        confidence = 0.6 if counts["relation_symbols"] else 0.45
        candidates.append(
            _make_candidate(
                native,
                None,
                bounds,
                stable_id(page.source_sha256, "native-math-evidence", line.id),
                ["native_math_glyphs"],
                confidence,
                config,
            )
        )
    assert_producer_unchanged("accuracy", LOADED_CODE_DIGEST)
    assert_producer_unchanged("detection", LOADED_DETECTION_DIGEST)
    return MathPageEvidence(
        source_sha256=page.source_sha256,
        page=page.geometry.page,
        cache_key=fingerprint,
        producer_sha256=code_digest("accuracy"),
        native_sha256=native_digest,
        detector_sha256=detector_digest,
        render_sha256=render_sha256,
        model_sha256=model_sha256,
        configuration=config,
        runtime=runtime,
        provenance=Provenance(
            source_sha256=page.source_sha256,
            engine="native-math-evidence",
            engine_version=VERSION,
            method="derived",
            resolved_device="cpu",
            execution_device="cpu",
        ),
        detector_device=detection.device,
        candidates=candidates,
        retained_line_count=len(retained),
        notes=[
            "Candidates and confidence are unvalidated evidence, not mathematical truth.",
            "Missing native text does not by itself establish an image formula.",
            "Native order is preserved; no formula conversion, OCR or ledger edit is performed.",
            "Only explicit TrimBox-excluded extraction lines are outside this evidence scope.",
        ],
    )
