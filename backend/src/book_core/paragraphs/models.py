"""Neutral paragraph data: units over ordered lines, joins, hyphen decisions, inline runs.

Units reference line ids and span ranges only; no source text is copied. Raw spans are never
rewritten: a join that removes a break hyphen is a recorded decision, and normalized paragraph
text is a derived view (``paragraphs.text``). Every line of a page belongs to exactly one unit.
Confidence is a rule heuristic, not a calibrated probability; below REVIEW_BELOW it is flagged.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier, Provenance, SpanRef
from book_core.reading_order.models import PageReadingOrder

UnitKind = Literal[
    "paragraph",
    "heading_candidate",
    "list_item_candidate",
    "caption",
    "figure_text",
    "table_text",
    "running_head",
    "running_foot",
    "folio",
    "production_mark",
    "artifact",
    "invisible",
]
TEXT_KINDS = frozenset(
    {"paragraph", "heading_candidate", "list_item_candidate", "caption", "figure_text",
     "table_text"}
)  # fmt: skip
JoinKind = Literal["line", "row", "column", "page"]
HyphenChoice = Literal["join", "keep", "soft_join"]
Feature = float | int | str | bool | None
REVIEW_BELOW = 0.6


class HyphenDecision(CoreModel):
    """A line-end hyphen: removed by the join (break hyphen) or kept (real compound)."""

    hyphen: SpanRef  # the hyphen character in the raw span (never rewritten)
    choice: HyphenChoice
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)


class WordJoin(CoreModel):
    """A word split across lines without a hyphen, joined on strong vocabulary evidence."""

    left: SpanRef
    right: SpanRef
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)


class LineJoin(CoreModel):
    """Two consecutive lines of one unit (or of a cross-page chain) read as continuous text."""

    previous_line_id: Identifier
    next_line_id: Identifier
    kind: JoinKind
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    hyphen: HyphenDecision | None = None
    word: WordJoin | None = None
    review_required: bool = False


class Boundary(CoreModel):
    """Why a unit starts where it does (first line of a stream, or a decided break)."""

    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False


class StyleRun(CoreModel):
    refs: list[SpanRef] = Field(min_length=1)
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    subscript: bool = False
    small_caps: bool = False
    color: int | None = None  # set when the colour differs from the unit's dominant colour


class LanguageRun(CoreModel):
    refs: list[SpanRef] = Field(min_length=1)
    language: str
    confidence: Confidence


class ParagraphUnit(CoreModel):
    id: Identifier
    page: int
    stream_id: Identifier
    stream_kind: str
    kind: UnitKind
    line_ids: list[Identifier] = Field(min_length=1)
    boundary: Boundary
    joins: list[LineJoin] = Field(default_factory=list)
    style_runs: list[StyleRun] = Field(default_factory=list)
    language: str = "und"
    language_confidence: Confidence = 0.0
    language_runs: list[LanguageRun] = Field(default_factory=list)
    continues_from: Identifier | None = None  # unit on the previous page (cross-page join)
    continues_to: Identifier | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def joins_chain_lines(self):
        pairs = list(zip(self.line_ids, self.line_ids[1:], strict=False))
        if [(j.previous_line_id, j.next_line_id) for j in self.joins] != pairs:
            raise ValueError("Unit joins must chain its lines in order")
        return self


class AnchorMove(CoreModel):
    """A float anchor at a paragraph boundary instead of the Step 7 line centre.

    ``applied`` tells whether the page order uses it; otherwise it is a recorded proposal and
    the order keeps the Step 7 anchor (see docs/step9_report.md, float anchors).
    """

    stream_id: Identifier
    original_after_line_id: Identifier | None
    original_position: int
    after_line_id: Identifier | None
    position: int
    unit_id: Identifier | None
    rule: str
    applied: bool = True
    reasons: list[str] = Field(min_length=1)


class PageParagraphs(CoreModel):
    source_sha256: Digest
    page: int
    paragraphs_version: str
    units: list[ParagraphUnit]
    order: PageReadingOrder  # Step 8 order; float anchors per the configured anchor rule
    anchor_moves: list[AnchorMove] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def every_line_in_one_unit(self):
        lines = [lid for unit in self.units for lid in unit.line_ids]
        if len(lines) != len(set(lines)):
            raise ValueError("A line belongs to more than one unit")
        ordered = {lid for stream in self.order.streams for lid in stream.line_ids}
        if set(lines) != ordered:
            raise ValueError("Every ordered line belongs to exactly one unit")
        ids = [unit.id for unit in self.units]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate unit id")
        return self


class PageJoin(CoreModel):
    """A paragraph continued from the last main-flow unit of one page onto the next page."""

    from_page: int
    from_unit_id: Identifier
    to_page: int
    to_unit_id: Identifier
    join: LineJoin
    evidence: dict[str, Feature] = Field(default_factory=dict)


class BookParagraphs(CoreModel):
    source_sha256: Digest
    paragraphs_version: str
    pages: int
    page_joins: list[PageJoin] = Field(default_factory=list)
    page_join_candidates: list[dict[str, Feature]] = Field(default_factory=list)
    profile: dict[str, Feature | list | dict] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance
