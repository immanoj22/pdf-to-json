"""Neutral equation-region, ownership and character-repair records (no MathML yet).

A region references native objects, spans (with character ranges) and lines by id; no
source text is copied and nothing is converted. Every region has one owner (Step 13b): the
text unit holding its spans or reading its drawn objects at an inline place, a display
equation unit of its own anchored in reading order, or a real figure that keeps the drawn
objects in its image. Equation units hold no lines, so units, lines and order are unchanged.
A figure of equation evidence only is converted (recorded here; its image is not exported).
Confidence is a rule heuristic, not a calibrated probability.

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
    line_id: Identifier | None = None  # the line beside it (inline) or above/below (display)
    relation: Literal["inside", "after", "before", "none"] = "none"
    region_type: str | None = None  # layout region type around the objects, if any


OwnerKind = Literal["text_unit", "equation_unit", "figure", "review"]


class InlinePlace(CoreModel):
    """Reading position inside a text unit: before character ``offset`` of span ``span_id``
    on line ``line_id`` (``offset`` equal to the span's length: after the span)."""

    line_id: Identifier
    span_id: Identifier
    offset: int = Field(ge=0)


class EquationOwner(CoreModel):
    """What holds the region's evidence in the document.

    ``text_unit``: the unit whose lines hold its spans, or (drawn objects of an inline
    equation) the unit read at ``place``; ``equation_unit``: a display equation unit of its
    own; ``figure``: a real figure keeps the drawn objects in its image and the equation is
    recorded beside it; ``review``: no owner can be decided (never read as an equation).
    """

    kind: OwnerKind
    unit_id: Identifier | None = None
    place: InlinePlace | None = None
    figure_id: Identifier | None = None
    reasons: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self):
        if self.kind in {"text_unit", "equation_unit"} and self.unit_id is None:
            raise ValueError("A unit owner names its unit")
        if (self.kind == "figure") != (self.figure_id is not None):
            raise ValueError("A figure owner, and only a figure owner, names its figure")
        if self.place is not None and self.kind != "text_unit":
            raise ValueError("Only a text unit owner has an inline place")
        if self.kind == "review" and self.unit_id is not None:
            raise ValueError("A region for review has no owner unit")
        return self


class EquationAnchor(CoreModel):
    """Where a display equation unit is read: after a line of a reading-order stream."""

    stream_id: Identifier
    after_line_id: Identifier | None = None
    position: int = Field(ge=-1)  # index of after_line_id in its stream; -1 = stream start
    order: int = Field(ge=0)  # among equation units sharing this anchor (native order)
    reading_index: int = Field(ge=1)  # 1-based position among the page's equation units
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_required: bool = False


class EquationUnit(CoreModel):
    """A display equation read as a unit of its own. It holds the drawn objects of one
    region (no lines, no text); its place in reading order is the anchor."""

    id: Identifier
    page: int = Field(gt=0)
    equation_id: Identifier
    anchor: EquationAnchor
    converted_figure_id: Identifier | None = None


class FigureConversion(CoreModel):
    """A figure region whose content is only equation evidence: its equations replace it,
    and its image is not exported."""

    figure_id: Identifier
    figure_name: str
    image_file: str | None = None
    equation_ids: list[Identifier] = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)


class FigureMath(CoreModel):
    """A real figure kept with equations inside it (recorded beside the figure)."""

    figure_id: Identifier
    equation_ids: list[Identifier] = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)


class GlyphOwnership(CoreModel):
    """Drawn objects of typeset equation regions by owner (one page or the book)."""

    objects: int = Field(ge=0)
    text_unit: int = Field(ge=0)
    equation_unit: int = Field(ge=0)
    figure: int = Field(ge=0)
    review: int = Field(ge=0)
    unowned: int = Field(ge=0)


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
    owner: EquationOwner | None = None

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
    units: list[EquationUnit] = Field(default_factory=list)
    figure_conversions: list[FigureConversion] = Field(default_factory=list)
    figure_math: list[FigureMath] = Field(default_factory=list)
    ownership: GlyphOwnership
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

    @model_validator(mode="after")
    def owned_once(self):
        if any(r.owner is None for r in self.regions):
            raise ValueError("Every equation region has an owner")
        regions = {r.id: r for r in self.regions}
        unit_ids = [u.id for u in self.units]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("Duplicate equation unit")
        by_unit = {u.id: u for u in self.units}
        for region in self.regions:
            owner = region.owner
            if owner.kind == "equation_unit" and (
                owner.unit_id not in by_unit or by_unit[owner.unit_id].equation_id != region.id
            ):
                raise ValueError("An equation unit owner names its own unit")
        if sorted(u.equation_id for u in self.units) != sorted(
            r.id for r in self.regions if r.owner.kind == "equation_unit"
        ):
            raise ValueError("Every equation unit holds one region it owns")
        if sorted(u.anchor.reading_index for u in self.units) != list(
            range(1, len(self.units) + 1)
        ):
            raise ValueError("Equation unit reading indexes must number the page's units")
        for record in (*self.figure_conversions, *self.figure_math):
            if any(e not in regions for e in record.equation_ids):
                raise ValueError("A figure record names an unknown equation region")
        converted = [c.figure_id for c in self.figure_conversions]
        kept = [m.figure_id for m in self.figure_math]
        if len(set(converted)) != len(converted) or set(converted) & set(kept):
            raise ValueError("A figure is converted once, or kept with its math, not both")
        for region in self.regions:
            if region.owner.kind == "figure" and region.owner.figure_id not in kept:
                raise ValueError("A figure owner is a kept figure with math")
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
    units: int = Field(ge=0)  # display equation units in reading order
    by_owner: dict[str, int] = Field(default_factory=dict)
    ownership: GlyphOwnership
    figures_converted: int = Field(ge=0)
    figures_kept_with_math: int = Field(ge=0)
    images_not_exported: list[str] = Field(default_factory=list)
    line_pitch: float | None = None  # the book's median text line pitch (display rows)
    model_evidence: bool
    font_evidence: dict[str, dict[str, Feature]] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
