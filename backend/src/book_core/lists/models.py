"""Neutral list data: items and entries over ordered lines, and the lists they form.

Step 11 refines the Step 9 units of a page: a list item or entry is its own unit, split from or
merged over Step 9 units, always over whole lines in stream order. Units reference line ids
and span ranges only; no source text is copied. A marker, a definition term and a locator are
span ranges kept as evidence with normalized descriptors (type, value, target page). Every
line of a page belongs to exactly one unit. Confidence is a rule heuristic, not a calibrated
probability; below REVIEW_BELOW a decision is flagged for review.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.model.common import Confidence, CoreModel, Digest, Identifier, Provenance, SpanRef
from book_core.paragraphs.models import Boundary, LanguageRun, LineJoin, StyleRun
from book_core.reading_order.models import OrderDecision, PageReadingOrder

Feature = float | int | str | bool | None
REVIEW_BELOW = 0.6
ItemKind = Literal[
    # Step 11 kinds
    "list_item",
    "definition_entry",
    "index_entry",
    "bibliography_entry",
    "contents_entry",
    # Step 9 kinds kept as they are
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
ENTRY_KINDS = frozenset(
    {"list_item", "definition_entry", "index_entry", "bibliography_entry", "contents_entry"}
)
TEXT_KINDS = frozenset(
    {*ENTRY_KINDS, "paragraph", "heading_candidate", "list_item_candidate", "caption",
     "figure_text", "table_text"}
)  # fmt: skip
MarkerType = Literal[
    "bullet", "dash", "decimal", "lower_alpha", "upper_alpha", "lower_roman", "upper_roman"
]
Punctuation = Literal["period", "parenthesis", "parentheses", "colon", "space", "none"]
ListKind = Literal[
    "bulleted", "numbered", "lettered", "unmarked", "definition", "glossary", "index",
    "bibliography", "contents",
]  # fmt: skip
ListRole = Literal["general", "questions", "question_answer", "objectives", "activities"]
LocatorKind = Literal["page", "range", "cross_reference"]


class Marker(CoreModel):
    """A list marker: its characters in the raw spans, normalized type and ordinal value."""

    refs: list[SpanRef] = Field(min_length=1)
    type: MarkerType
    value: int | None = None  # 1-based ordinal for numbered, lettered and roman markers
    punctuation: Punctuation = "none"
    padded: bool = False  # "01", "02": zero-padded numbers
    own_line: bool = False  # the marker stands on a visual line of its own


class Locator(CoreModel):
    """A locator of an index or glossary entry: a page, a range or a cross-reference.

    ``label``/``end_label`` are the normalized printed labels (derived values used to resolve
    pages), ``qualifier`` a short letter prefix the book puts before a page number (for
    example a figure or map mark); targets are physical pages through the Step 8 labels.
    """

    refs: list[SpanRef] = Field(min_length=1)
    kind: LocatorKind
    label: str | None = None
    end_label: str | None = None
    qualifier: str | None = None
    target_page: int | None = None
    end_target_page: int | None = None
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)


class ItemUnit(CoreModel):
    """A Step 11 unit: a Step 9 unit unchanged, or an item/entry split from or merged over
    Step 9 units (``source_unit_ids``)."""

    id: Identifier
    page: int
    stream_id: Identifier
    stream_kind: str
    kind: ItemKind
    line_ids: list[Identifier] = Field(min_length=1)
    source_unit_ids: list[Identifier] = Field(min_length=1)
    boundary: Boundary
    joins: list[LineJoin] = Field(default_factory=list)
    style_runs: list[StyleRun] = Field(default_factory=list)
    language: str = "und"
    language_confidence: Confidence = 0.0
    language_runs: list[LanguageRun] = Field(default_factory=list)
    continues_from: Identifier | None = None
    continues_to: Identifier | None = None
    list_id: Identifier | None = None
    level: int | None = Field(default=None, ge=1)  # nesting level inside its list tree
    marker: Marker | None = None
    term: list[SpanRef] = Field(default_factory=list)  # definition / index term spans
    locators: list[Locator] = Field(default_factory=list)
    item_role: Literal["item", "question", "answer", "entry", "sub_entry"] | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def joins_chain_lines(self):
        pairs = list(zip(self.line_ids, self.line_ids[1:], strict=False))
        if [(j.previous_line_id, j.next_line_id) for j in self.joins] != pairs:
            raise ValueError("Unit joins must chain its lines in order")
        if (self.list_id is None) != (self.kind not in ENTRY_KINDS):
            raise ValueError("List items, and only list items, belong to a list")
        return self


class StructuredList(CoreModel):
    """A list: items in reading order (possibly over several columns and pages)."""

    id: Identifier
    kind: ListKind
    role: ListRole = "general"
    marker_type: MarkerType | None = None
    start: int | None = None  # first ordinal of a numbered, lettered or roman list
    item_ids: list[Identifier] = Field(min_length=1)
    parent_item_id: Identifier | None = None  # a nested list belongs to an item
    level: int = Field(ge=1)
    first_page: int = Field(ge=1)
    last_page: int = Field(ge=1)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    evidence: dict[str, Feature] = Field(default_factory=dict)
    review_required: bool = False


class PageLists(CoreModel):
    source_sha256: Digest
    page: int
    lists_version: str
    units: list[ItemUnit]
    order: PageReadingOrder  # the Step 9 order; entry order applied on glossary pages
    order_changes: list[OrderDecision] = Field(default_factory=list)
    provenance: Provenance

    @model_validator(mode="after")
    def every_line_in_one_unit(self):
        lines = [lid for unit in self.units for lid in unit.line_ids]
        if len(lines) != len(set(lines)):
            raise ValueError("A line belongs to more than one unit")
        ordered = [lid for stream in self.order.streams for lid in stream.line_ids]
        if set(lines) != set(ordered) or len(ordered) != len(set(ordered)):
            raise ValueError("Every ordered line belongs to exactly one unit")
        ids = [unit.id for unit in self.units]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate unit id")
        position = {
            lid: i for stream in self.order.streams for i, lid in enumerate(stream.line_ids)
        }
        for unit in self.units:
            places = [position[lid] for lid in unit.line_ids]
            if places != sorted(places):
                raise ValueError("A unit's lines must follow the stream order")
        return self


class EntryLink(CoreModel):
    """An entry continued on the next page (or column of the next page): the continuation is
    a separate unit; entries never join across pages like prose."""

    from_page: int
    from_unit_id: Identifier
    to_page: int
    to_unit_id: Identifier
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)


class BookLists(CoreModel):
    source_sha256: Digest
    lists_version: str
    pages: int
    lists: list[StructuredList] = Field(default_factory=list)
    entry_links: list[EntryLink] = Field(default_factory=list)
    dropped_page_joins: list[dict[str, Feature]] = Field(default_factory=list)
    profile: dict[str, Feature | list | dict] = Field(default_factory=dict)
    config: dict[str, Feature | list | dict] = Field(default_factory=dict)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance
