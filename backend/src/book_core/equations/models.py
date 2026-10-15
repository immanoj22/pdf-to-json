"""Neutral equation-region and character-repair records (Step 13a: detection only).

A region references native objects, spans (with character ranges) and lines by id; no
source text is copied and nothing is converted. Where an equation lands is recorded as the
id and kind of the unit that holds or neighbours it. Confidence is a rule heuristic, not a
calibrated probability.

Character repairs are a separate traceable layer: the original text stays in the span store
unchanged; a repair records the original and the proposed character with its evidence,
confidence and review status. Only unambiguous evidence proposes a repair; anything else is
a flag that keeps the original.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import BBox, Confidence, CoreModel, Digest, Identifier, SpanRef

Feature = float | int | str | bool | None
Presentation = Literal["inline", "display", "uncertain"]
EquationSource = Literal["text", "vector", "image", "mixed"]
ReviewStatus = Literal["needs_review", "accepted", "rejected"]


class ModelSupport(CoreModel):
    """Layout-model formula boxes that overlap the region (evidence only)."""

    heron: bool = False
    pp_doclayoutv3: bool = False
    labels: list[str] = Field(default_factory=list)


class Host(CoreModel):
    """The unit the region lies in (inline) or follows (display), and its kind."""

    unit_id: Identifier | None = None
    unit_kind: str = "none"
    relation: Literal["inside", "after", "before", "none"] = "none"
    region_type: str | None = None  # layout region type around the objects, if any


class EquationRegion(CoreModel):
    id: Identifier
    page: int = Field(gt=0)
    bbox: BBox
    presentation: Presentation
    source: EquationSource
    object_ids: list[Identifier] = Field(default_factory=list)
    span_refs: list[SpanRef] = Field(default_factory=list)
    line_ids: list[Identifier] = Field(default_factory=list)
    signals: dict[str, Feature] = Field(default_factory=dict)
    rules: list[str] = Field(min_length=1)
    model_support: ModelSupport = Field(default_factory=ModelSupport)
    host: Host = Field(default_factory=Host)
    confidence: Confidence
    review_required: Literal[True] = True
    review_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_present(self):
        if not self.object_ids and not self.span_refs:
            raise ValueError("An equation region needs native objects or spans")
        if self.source == "text" and self.object_ids:
            raise ValueError("A text equation region references no drawn objects")
        if self.source in {"vector", "image"} and self.span_refs:
            raise ValueError("A drawn equation region references no spans")
        return self


class ModelOnlyRegion(CoreModel):
    """A layout-model formula box with no native equation evidence: recorded, not detected."""

    page: int = Field(gt=0)
    bbox: BBox
    models: list[str] = Field(min_length=1)
    labels: list[str] = Field(min_length=1)


class CharacterRepair(CoreModel):
    """One proposed character correction; the span store keeps the original text."""

    id: Identifier
    span_id: Identifier
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    original: str = Field(min_length=1)
    corrected: str = Field(min_length=1)
    glyph_id: int
    glyph_name: str
    font: str
    evidence: list[str] = Field(min_length=2)
    confidence: Confidence
    review_status: ReviewStatus = "needs_review"
    in_equation: Identifier | None = None

    @model_validator(mode="after")
    def changes_text(self):
        if self.end <= self.start:
            raise ValueError("A repair covers a nonempty character range")
        if self.original == self.corrected:
            raise ValueError("A repair must change the character")
        return self


class CharacterReviewFlag(CoreModel):
    """Disagreeing glyph evidence that is not unambiguous: the original is kept."""

    span_id: Identifier
    start: int = Field(ge=0)
    glyph_id: int
    glyph_name: str | None
    proposed: str | None
    reasons: list[str] = Field(min_length=1)
    in_equation: Identifier | None = None


class PageEquations(CoreModel):
    source_sha256: Digest
    page: int = Field(gt=0)
    version: str
    regions: list[EquationRegion] = Field(default_factory=list)
    model_only: list[ModelOnlyRegion] = Field(default_factory=list)
    repairs: list[CharacterRepair] = Field(default_factory=list)
    character_flags: list[CharacterReviewFlag] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique(self):
        ids = [r.id for r in self.regions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate equation region")
        owned = [o for r in self.regions for o in r.object_ids]
        if len(owned) != len(set(owned)):
            raise ValueError("A native object belongs to at most one equation region")
        spans = [(ref.span_id, ref.start, ref.end) for r in self.regions for ref in r.span_refs]
        if len(spans) != len(set(spans)):
            raise ValueError("A span range belongs to at most one equation region")
        return self


class BookEquations(CoreModel):
    source_sha256: Digest
    pages: int = Field(gt=0)
    version: str
    config: dict[str, Feature | dict[str, Feature]]
    glyph_shapes: int = Field(ge=0)  # distinct recurring vector glyph shapes in the book
    vector_glyphs: int = Field(ge=0)
    regions: int = Field(ge=0)
    by_presentation: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    repairs: int = Field(ge=0)
    character_flags: int = Field(ge=0)
    model_evidence: bool
    font_evidence: dict[str, dict[str, Feature]] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
