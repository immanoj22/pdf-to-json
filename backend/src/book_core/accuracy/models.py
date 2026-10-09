"""Source-referenced requests and evidence envelopes for optional accuracy providers.

Requests do not own text or change its ledger. Images are supplied by the Extractor.
A provider's score is evidence, never a calibrated probability or a final decision.
"""

import math
from typing import Annotated, Literal

from pydantic import Field, JsonValue, NonNegativeInt, PositiveInt, model_validator

from book_core.device import DeviceResolution
from book_core.extraction.rasters import RasterPage
from book_core.model.common import (
    BBox,
    Confidence,
    CoreModel,
    Digest,
    Finite,
    Identifier,
    Provenance,
    SpanRef,
    TextDirection,
)
from book_core.model.math import MathTree


def source_ref_within(ref: SpanRef, originals: list[SpanRef]) -> bool:
    return any(
        ref.span_id == original.span_id
        and (
            original.start is None
            or (ref.start is not None and original.start <= ref.start and ref.end <= original.end)
        )
        for original in originals
    )


class ExtensionMetadata(CoreModel):
    """Complete provider identity, including the actual optional model bytes."""

    name: Identifier
    version: Identifier
    configuration: dict[str, JsonValue] = Field(default_factory=dict)
    producer_source_sha256: Digest
    model_sha256: Digest | None = None
    model_repository: Identifier | None = None
    model_revision: Identifier | None = None
    dependency_versions: dict[str, str] = Field(default_factory=dict)
    device: DeviceResolution = Field(default_factory=DeviceResolution)

    @model_validator(mode="after")
    def model_identity(self):
        if self.device.requested == "cpu" and self.device.resolved != "cpu":
            raise ValueError("A CPU device policy cannot execute on CUDA")
        if (self.model_repository is not None or self.model_revision is not None) and (
            self.model_sha256 is None
        ):
            raise ValueError("A model identity requires its actual content digest")
        return self


class EvidenceReference(CoreModel):
    id: Identifier
    sha256: Digest
    kind: Identifier


class SourceRegion(CoreModel):
    """Source coordinates and references; no column, script or direction is inferred."""

    id: Identifier
    page: PositiveInt
    bbox: BBox | None = None
    source_refs: list[SpanRef] = Field(default_factory=list)
    languages: list[Identifier] = Field(default_factory=list)
    native_object_ids: list[Identifier] = Field(default_factory=list)
    script: str | None = None
    text_direction: TextDirection | None = None

    @model_validator(mode="after")
    def unique_references(self):
        refs = [(ref.span_id, ref.start, ref.end) for ref in self.source_refs]
        if len(refs) != len(set(refs)):
            raise ValueError("Repeated source range")
        if len(self.native_object_ids) != len(set(self.native_object_ids)):
            raise ValueError("Repeated native object reference")
        if len(self.languages) != len(set(self.languages)):
            raise ValueError("Repeated language code")
        return self


class AccuracyInput(CoreModel):
    source_sha256: Digest
    regions: list[SourceRegion] = Field(min_length=1)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    # Numeric features are optional evidence supplied by a caller, never copied text.
    features: dict[str, Finite | bool | None | list[Finite]] = Field(default_factory=dict)
    raster: RasterPage | None = None
    raster_bbox: BBox | None = None
    raster_page: PositiveInt | None = None

    @model_validator(mode="after")
    def source_identity(self):
        if len({region.id for region in self.regions}) != len(self.regions):
            raise ValueError("Repeated source region")
        if len({item.id for item in self.evidence_refs}) != len(self.evidence_refs):
            raise ValueError("Repeated evidence reference")
        if (self.raster is None) != (self.raster_bbox is None):
            raise ValueError("An image requires its source coordinate frame")
        if (self.raster is None) != (self.raster_page is None):
            raise ValueError("An image requires its explicit source page")
        if self.raster_page is not None and {region.page for region in self.regions} != {
            self.raster_page
        }:
            raise ValueError("One image cannot silently cross source pages")
        if self.raster_bbox is not None and (
            self.raster_bbox.x0 >= self.raster_bbox.x1 or self.raster_bbox.y0 >= self.raster_bbox.y1
        ):
            raise ValueError("An image frame must have positive area")
        return self


class TableStructureInput(AccuracyInput):
    pass


class FormulaInput(AccuracyInput):
    source_kind: Literal["digital", "image"]

    @model_validator(mode="after")
    def image_source(self):
        if self.source_kind == "image" and self.raster is None:
            raise ValueError("Image formula recognition requires extractor pixels")
        return self


class FormulaObservation(CoreModel):
    id: Identifier
    region_id: Identifier
    source_kind: Literal["digital", "image"]
    source_refs: list[SpanRef] = Field(default_factory=list)
    recognized_latex: str | None = None
    confidence: Confidence | None = None
    review_required: bool = True

    @model_validator(mode="after")
    def preserve_digital_text(self):
        if self.source_kind == "digital" and self.recognized_latex is not None:
            raise ValueError("Digital formula content must use source references")
        if self.source_kind == "digital" and not self.source_refs:
            raise ValueError("Digital formula evidence requires source references")
        return self


class GlyphEvidence(CoreModel):
    """A native glyph refers to original codepoints, including multi-codepoint ligatures."""

    id: Identifier
    region_id: Identifier
    native_evidence_id: Identifier
    source_ref: SpanRef
    bbox: BBox
    origin: tuple[Finite, Finite]
    writing_vector: tuple[Finite, Finite]

    @model_validator(mode="after")
    def explicit_native_range(self):
        if self.source_ref.start is None:
            raise ValueError("A native glyph requires an explicit original character range")
        if math.hypot(*self.writing_vector) == 0:
            raise ValueError("A native glyph requires a nonzero writing vector")
        return self


class RuleEvidence(CoreModel):
    region_id: Identifier
    native_evidence_id: Identifier
    object_id: Identifier
    segment_index: NonNegativeInt = 0
    start: tuple[Finite, Finite]
    end: tuple[Finite, Finite]
    stroke_width: Annotated[float, Field(ge=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def nonzero_rule(self):
        if self.start == self.end:
            raise ValueError("A native rule requires distinct endpoints")
        return self


class MathBuildInput(AccuracyInput):
    source_kind: Literal["digital", "image"]
    observation: FormulaObservation | None = None
    glyphs: list[GlyphEvidence] = Field(default_factory=list)
    rules: list[RuleEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def observation_source(self):
        regions = {region.id: region for region in self.regions}
        artifacts = {ref.id for ref in self.evidence_refs if ref.kind == "native_objects"}
        if self.observation is not None:
            if self.observation.source_kind != self.source_kind:
                raise ValueError("Formula observation source kind differs")
            if self.observation.region_id not in regions:
                raise ValueError("Formula observation references an unknown source region")
            if any(
                not source_ref_within(ref, regions[self.observation.region_id].source_refs)
                for ref in self.observation.source_refs
            ):
                raise ValueError("Formula observation references another source region")
        if len({glyph.id for glyph in self.glyphs}) != len(self.glyphs):
            raise ValueError("Repeated native glyph")
        rule_keys = [(rule.region_id, rule.object_id, rule.segment_index) for rule in self.rules]
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("Repeated native rule segment")
        for item in [*self.glyphs, *self.rules]:
            if item.region_id not in regions:
                raise ValueError("Math geometry references an unknown source region")
            if item.native_evidence_id not in artifacts:
                raise ValueError("Math geometry requires its native object artifact digest")
        for glyph in self.glyphs:
            if not source_ref_within(glyph.source_ref, regions[glyph.region_id].source_refs):
                raise ValueError("Native glyph references another source region")
        for rule in self.rules:
            if rule.object_id not in regions[rule.region_id].native_object_ids:
                raise ValueError("Native rule references another source region")
        return self


class MathConversionInput(AccuracyInput):
    tree: MathTree | None = None
    recognized_latex: str | None = None
    input_source: Literal["digital", "image"] | None = None
    input_provenance: Provenance | None = None
    target_format: Literal["latex", "mathml"]

    @model_validator(mode="after")
    def one_mathematical_input(self):
        if (self.tree is None) == (self.recognized_latex is None):
            raise ValueError("Conversion requires exactly one math tree or derived formula")
        if self.input_provenance is not None:
            if self.input_provenance.source_sha256 != self.source_sha256:
                raise ValueError("Conversion input provenance differs from its source")
        if self.recognized_latex is not None:
            if not self.recognized_latex.strip():
                raise ValueError("A derived formula cannot be blank")
            if (
                self.input_source is None
                or self.input_provenance is None
                or self.input_provenance.method != "derived"
            ):
                raise ValueError("A derived formula requires explicit source and provenance")
        return self


class ContinuationInput(AccuracyInput):
    """The supplied candidate pair is a hypothesis, never an inferred reading order."""

    first_region_id: Identifier
    second_region_id: Identifier
    first_text_sha256: Digest | None = None
    second_text_sha256: Digest | None = None

    @model_validator(mode="after")
    def candidate_pair(self):
        if (self.first_text_sha256 is None) != (self.second_text_sha256 is None):
            raise ValueError("Continuation text digests must be supplied together")
        ids = {region.id for region in self.regions}
        if (
            self.first_region_id not in ids
            or self.second_region_id not in ids
            or self.first_region_id == self.second_region_id
        ):
            raise ValueError("Continuation requires two distinct supplied source regions")
        return self


class HeadingInput(AccuracyInput):
    candidate_region_id: Identifier

    @model_validator(mode="after")
    def candidate_exists(self):
        if self.candidate_region_id not in {region.id for region in self.regions}:
            raise ValueError("Heading evidence references an unknown source region")
        return self


class PageReviewInput(AccuracyInput):
    page: PositiveInt
    candidate_ids: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def one_page(self):
        if any(region.page != self.page for region in self.regions):
            raise ValueError("A page review cannot silently mix source pages")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("Repeated review candidate")
        return self


class AccuracyResult(CoreModel):
    source_sha256: Digest
    request_sha256: Digest
    cache_key: Digest
    metadata: ExtensionMetadata
    status: Literal["unavailable", "undecided", "evidence"]
    reason: Identifier
    confidence: Confidence | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def source_and_device(self):
        if self.provenance.source_sha256 != self.source_sha256:
            raise ValueError("Extension provenance must identify its source")
        if (
            self.provenance.engine != self.metadata.name
            or self.provenance.engine_version != self.metadata.version
        ):
            raise ValueError("Extension provenance identity differs from its metadata")
        device = self.metadata.device.resolved
        if self.provenance.resolved_device != device or self.provenance.execution_device != device:
            raise ValueError("Extension provenance must record the actual execution device")
        if self.status == "unavailable" and self.confidence is not None:
            raise ValueError("Unavailable evidence has no confidence score")
        return self


class TableCellEvidence(CoreModel):
    row: Annotated[int, Field(ge=0)]
    column: Annotated[int, Field(ge=0)]
    row_span: PositiveInt = 1
    column_span: PositiveInt = 1
    bbox: BBox | None = None
    source_refs: list[SpanRef] = Field(default_factory=list)
    confidence: Confidence | None = None


class TableStructureResult(AccuracyResult):
    row_count: PositiveInt | None = None
    column_count: PositiveInt | None = None
    cells: list[TableCellEvidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_grid(self):
        if self.status != "evidence" and (
            self.row_count is not None or self.column_count is not None or self.cells
        ):
            raise ValueError("An undecided table must not invent a grid")
        occupied = set()
        for cell in self.cells:
            if self.row_count is not None and cell.row + cell.row_span > self.row_count:
                raise ValueError("Cell extends past observed rows")
            if self.column_count is not None and cell.column + cell.column_span > self.column_count:
                raise ValueError("Cell extends past observed columns")
            for row in range(cell.row, cell.row + cell.row_span):
                for column in range(cell.column, cell.column + cell.column_span):
                    if (row, column) in occupied:
                        raise ValueError("Overlapping observed cells")
                    occupied.add((row, column))
        return self


class FormulaResult(AccuracyResult):
    observations: list[FormulaObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_only(self):
        if self.status != "evidence" and self.observations:
            raise ValueError("Unavailable or undecided formula has no recognition output")
        if len({item.id for item in self.observations}) != len(self.observations):
            raise ValueError("Repeated formula observation")
        return self


class MathBuildResult(AccuracyResult):
    tree: MathTree | None = None

    @model_validator(mode="after")
    def evidence_only(self):
        if self.status != "evidence" and self.tree is not None:
            raise ValueError("Unavailable or undecided math has no generated tree")
        return self


class MathConversionResult(AccuracyResult):
    target_format: Literal["latex", "mathml"]
    generated_value: str | None = None

    @model_validator(mode="after")
    def evidence_only(self):
        if self.status != "evidence" and self.generated_value is not None:
            raise ValueError("Unavailable or undecided conversion has no generated value")
        return self


class ContinuationResult(AccuracyResult):
    continuation_score: Confidence | None = None

    @model_validator(mode="after")
    def evidence_only(self):
        if self.status != "evidence" and self.continuation_score is not None:
            raise ValueError("Unavailable or undecided continuity has no score")
        return self


class HeadingResult(AccuracyResult):
    label: Literal["heading", "not_heading", "undecided"] | None = None
    level: PositiveInt | None = None
    heading_likelihood: Confidence | None = None

    @model_validator(mode="after")
    def evidence_only(self):
        if self.status != "evidence" and (
            self.heading_likelihood is not None or self.label is not None or self.level is not None
        ):
            raise ValueError("Unavailable or undecided heading evidence has no label or level")
        if self.level is not None and self.label != "heading":
            raise ValueError("Only a heading hypothesis can carry level evidence")
        return self


class ReviewFinding(CoreModel):
    """A reviewer reports concerns with references; it never edits the page."""

    id: Identifier
    kind: Identifier
    region_ids: list[Identifier] = Field(default_factory=list)
    source_refs: list[SpanRef] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    confidence: Confidence | None = None
    review_required: Literal[True] = True


class PageReviewResult(AccuracyResult):
    findings: list[ReviewFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_only(self):
        if self.status != "evidence" and self.findings:
            raise ValueError("Unavailable or undecided review has no findings")
        if len({item.id for item in self.findings}) != len(self.findings):
            raise ValueError("Repeated review finding")
        return self
