"""The published book model (Stage 1 output): one JSON document per book.

Adapters (the output formats of Stage 2) read this model without knowing the stages
behind it. ``docs/json_schema.md`` describes it in plain words; the JSON Schema
(``assembly/book.schema.json``) is generated from these classes and versioned with
``SCHEMA_VERSION`` (semantic versioning: a new optional field is a minor version, a removed or
changed field a major one).

Principles:

- **Nothing is lost.** Every retained source token is in exactly one place: a unit of
  ``content``, a ``furniture`` record, or a ``suppressed`` record that says why it is not
  content. Text outside the PDF TrimBox is listed in ``suppressed`` too.
- **Nothing is invented.** A unit's ``text`` is the source text (NFKC, as the span store holds
  it) of its lines, joined by ``"\\n"`` at source line ends; it is never edited. Hyphen and
  split-word decisions at those line ends are recorded in ``joins``; styling, links,
  languages and inline math are ``spans`` over the text (character offsets). List markers,
  index locators and terms are offsets or separate fields, never rewritten text.
- **Every uncertain item is flagged.** Every unit has a ``review_status`` (``ok``,
  ``needs_review``, ``must_check``) and ``flags`` (reasons); ``review`` lists them all.
- **Deterministic.** Ids are stable digests (16 hex characters) of the stage records; keys
  are sorted and no timestamp enters the content (``metadata.run`` is outside the content
  hash).

The model holds no output-format tag names: kinds and roles are neutral words.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

SCHEMA_NAME = "universal-book"
SCHEMA_VERSION = "1.0.0"

Id = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Confidence = Annotated[float, Field(ge=0, le=1)]
ReviewStatus = Literal["ok", "needs_review", "must_check"]
Source = Literal["native", "ocr"]
Direction = Literal["ltr", "rtl", "ttb"]
Evidence = dict[str, str | int | float | bool | None]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- text


class Box(Model):
    """A rectangle on one physical page, in PDF points (unrotated crop box, y down)."""

    page: Annotated[int, Field(ge=1)]
    x0: float
    y0: float
    x1: float
    y1: float


class LinkTarget(Model):
    """An internal link target: a physical page, and the unit at the target point when one
    holds it."""

    page: Annotated[int, Field(ge=1)]
    unit: Id | None = None


SpanKind = Literal[
    "italic",
    "bold",
    "bold_italic",
    "superscript",
    "subscript",
    "small_caps",
    "underline",
    "link",
    "language",
    "math",
    "run_in_heading",
]


class InlineSpan(Model):
    """Inline meaning over ``text[start:end]`` of its unit (``start == end`` only for a math
    insertion point: drawn inline math read at that place)."""

    kind: SpanKind
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    href: str | None = None  # link: an external URI
    target: LinkTarget | None = None  # link: an internal target
    language: str | None = None  # language: BCP 47 code of the span
    equation: Id | None = None  # math: the equation record
    mathml: str | None = None
    latex: str | None = None
    confidence: Confidence | None = None
    review_status: ReviewStatus = "ok"

    @model_validator(mode="after")
    def consistent(self):
        if self.end < self.start or (self.end == self.start and self.kind != "math"):
            raise ValueError("A span covers characters (only math may be an insertion point)")
        if self.kind == "link" and self.href is None and self.target is None:
            raise ValueError("A link names an external URI or an internal target")
        if self.kind == "language" and not self.language:
            raise ValueError("A language span names its language")
        if self.kind == "math" and self.equation is None:
            raise ValueError("A math span names its equation record")
        return self


class LineJoin(Model):
    """A decision at a source line end inside ``text`` (the ``"\\n"`` at ``at``): a break
    hyphen removed (``join``/``soft_join``: the hyphen at ``hyphen_at`` and the line end
    vanish when read), a real hyphen kept (``keep``: the line end vanishes), or a word split
    without a hyphen (``word``: the line end vanishes). Line ends without a record read as a
    space."""

    at: Annotated[int, Field(ge=0)]
    decision: Literal["join", "soft_join", "keep", "word"]
    hyphen_at: Annotated[int, Field(ge=0)] | None = None
    confidence: Confidence
    review_status: ReviewStatus = "ok"


class SourceRun(Model):
    """A slice of existing text in a source line split by suppression; no text copy.

    Reassemble slices by (page, line), then (position, source_start) to recover the
    ledger's token boundaries even when part of a token was hidden.
    """

    page: Annotated[int, Field(ge=1)]
    line: Id
    span: Id
    position: Annotated[int, Field(ge=0)]
    source_start: Annotated[int, Field(ge=0)] = 0
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]


def validate_source_runs(text, runs):
    previous_end = 0
    for run in sorted(runs, key=lambda r: r.start):
        if not 0 <= run.start < run.end <= len(text):
            raise ValueError("A source run covers characters within its text")
        if run.start < previous_end:
            raise ValueError("Source runs must not overlap")
        previous_end = run.end


class TextContent(Model):
    """Text of one unit: the source text, never edited, with spans and join decisions."""

    text: str
    spans: list[InlineSpan] = Field(default_factory=list)
    joins: list[LineJoin] = Field(default_factory=list)
    raw: str | None = None  # the original (pre-NFKC) text when normalization changed it
    language: str | None = None  # BCP 47; None: the book's language
    script: str | None = None
    direction: Direction | None = None
    source_runs: list[SourceRun] = Field(default_factory=list)

    @model_validator(mode="after")
    def offsets(self):
        n = len(self.text)
        validate_source_runs(self.text, self.source_runs)
        for span in self.spans:
            if span.end > n:
                raise ValueError("A span ends past its text")
        for join in self.joins:
            if join.at >= n or self.text[join.at] != "\n":
                raise ValueError("A line join sits on a line end of the text")
            if join.hyphen_at is not None and not 0 <= join.hyphen_at < join.at:
                raise ValueError("A joined hyphen precedes its line end")
        return self


class SourceRefs(Model):
    """Where a unit's text comes from: layout line ids, and span ranges for parts of lines
    (``span``: 16-hex span id; ``start``/``end``: original code points, half-open)."""

    lines: list[Id] = Field(default_factory=list)
    spans: list[SpanRange] = Field(default_factory=list)


class SpanRange(Model):
    span: Id
    start: Annotated[int, Field(ge=0)] | None = None
    end: Annotated[int, Field(ge=0)] | None = None


SourceRefs.model_rebuild()


class Provenance(Model):
    """Which stages produced the unit and a short evidence summary."""

    stages: list[str] = Field(min_length=1)
    reasons: list[str] = Field(default_factory=list)


class PageMarkerRef(Model):
    page: Annotated[int, Field(ge=1)]
    label: str | None = None


class Continuation(Model):
    """A link to the next (``continues_to``) or previous (``continues_from``) piece of the same
    logical paragraph, item, entry or table across a page or column break."""

    unit: Id
    kind: Literal["page", "column"]
    page_marker: PageMarkerRef | None = None  # the page that begins at the break
    hyphen: Literal["join", "soft_join", "keep"] | None = None  # a hyphen at the break
    word_join: bool = False
    skipped: list[Id] = Field(default_factory=list)  # floats read between the two pieces
    confidence: Confidence
    review_status: ReviewStatus = "ok"


class UnitBase(Model):
    id: Id
    pages: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)
    boxes: list[Box] = Field(default_factory=list)
    order: Annotated[int, Field(ge=0)]  # position in the book's reading order
    source: Source = "native"
    confidence: Confidence | None = None
    review_status: ReviewStatus = "ok"
    flags: list[str] = Field(default_factory=list)
    continues_from: Continuation | None = None
    continues_to: Continuation | None = None
    provenance: Provenance
    refs: SourceRefs = Field(default_factory=SourceRefs)


# --------------------------------------------------------------------------- units


class PageMarker(UnitBase):
    """The start of a physical page in reading order, with its printed label."""

    type: Literal["page_marker"] = "page_marker"
    page: Annotated[int, Field(ge=1)]
    label: str | None = None
    label_source: Literal["printed", "metadata", "inferred", "none"] = "none"


ParagraphRole = Literal[
    "body",
    "display_title",
    "label",
    "credit",
    "list_item_candidate",
    "heading_candidate",
    "figure_text",
    "table_text",
]


class Paragraph(UnitBase):
    type: Literal["paragraph"] = "paragraph"
    role: ParagraphRole = "body"
    content: TextContent


class Heading(UnitBase):
    type: Literal["heading"] = "heading"
    level: Annotated[int, Field(ge=1)]
    role: str  # book_title, part, unit, chapter, lesson, section, subsection, ...
    level_method: str
    section: Id | None = None
    content: TextContent


class Caption(UnitBase):
    """A caption that is not linked to a figure or table (review)."""

    type: Literal["caption"] = "caption"
    content: TextContent


class Footnote(UnitBase):
    """A note set apart from the running text (footnote area). Its marker in the text is a
    superscript span; the link between them is not decided (flagged)."""

    type: Literal["footnote"] = "footnote"
    content: TextContent


class IndexDivider(UnitBase):
    """A letter heading inside an index ("A", "B"...): neither a heading nor an entry."""

    type: Literal["index_divider"] = "index_divider"
    content: TextContent


class Marker(Model):
    """A list marker as structure: its printed text, kind and ordinal value."""

    text: str
    type: Literal[
        "bullet", "dash", "decimal", "lower_alpha", "upper_alpha", "lower_roman", "upper_roman"
    ]
    value: int | None = None
    punctuation: str = "none"


class Locator(Model):
    """An index or glossary locator: offsets in the entry text and the resolved target."""

    kind: Literal["page", "range", "cross_reference"]
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    label: str | None = None
    end_label: str | None = None
    target_page: int | None = None
    end_target_page: int | None = None
    confidence: Confidence


class PersonName(Model):
    """A parsed personal name (client profile option, off by default); the printed text is
    always kept in the entry."""

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    family: str
    given: str | None = None
    confidence: Confidence
    review_status: ReviewStatus = "needs_review"


ItemType = Literal[
    "list_item",
    "index_entry",
    "glossary_entry",
    "definition_entry",
    "bibliography_entry",
    "contents_entry",
]


class ListItem(UnitBase):
    """A list item or entry; the marker is structure, not text. ``children`` holds nested
    lists (and sub-entries) that directly follow it."""

    type: ItemType = "list_item"
    marker: Marker | None = None
    item_role: str | None = None  # item, question, answer, entry, sub_entry
    level: Annotated[int | None, Field(ge=1)] = None  # entry depth may differ from its list
    term: tuple[int, int] | None = None  # offsets of a definition or index term
    locators: list[Locator] = Field(default_factory=list)
    names: list[PersonName] = Field(default_factory=list)
    content: TextContent
    children: list[Unit] = Field(default_factory=list)
    _list: tuple | None = PrivateAttr(default=None)  # assembly grouping hint, not published


class ListNode(UnitBase):
    """One run of consecutive items of a list on one page (a ``segment``); segments of the
    same list share ``list_id`` and link with ``continues_from``/``continues_to``."""

    type: Literal["list"] = "list"
    list_id: Id
    segment: Annotated[int, Field(ge=0)]
    list_type: str  # bulleted, numbered, lettered, unmarked, definition, glossary, index, ...
    list_role: str = "general"
    marker_type: str | None = None
    start: int | None = None
    level: Annotated[int, Field(ge=1)] = 1
    items: list[ListItem] = Field(min_length=1)


class TextFragment(Model):
    """Text inside a table cell that is not a whole unit (lines or parts of lines)."""

    type: Literal["text"] = "text"
    refs: SourceRefs
    content: TextContent


class Cell(Model):
    id: Id
    row: Annotated[int, Field(ge=0)]
    column: Annotated[int, Field(ge=0)]
    row_span: Annotated[int, Field(ge=1)] = 1
    column_span: Annotated[int, Field(ge=1)] = 1
    role: Literal["column_header", "row_header", "section", "data"] = "data"
    headers: list[Id] = Field(default_factory=list)  # cells labelling this one
    box: Box
    content: list[Annotated[TextFragment | Unit, Field(discriminator="type")]] = Field(
        default_factory=list
    )


class TableText(Model):
    """A table's title or note: a unit next to the table (``unit``) or lines inside it."""

    id: Id
    role: Literal["title", "note"]
    numbered: bool = False
    number: str | None = None
    refs: SourceRefs
    content: TextContent


class TableContinuation(Model):
    repeated_header_rows: Annotated[int, Field(ge=0)] = 0
    column_map: list[int] = Field(default_factory=list)


class Table(UnitBase):
    type: Literal["table"] = "table"
    rows: Annotated[int, Field(ge=1)]
    columns: Annotated[int, Field(ge=1)]
    header_rows: Annotated[int, Field(ge=0)] = 0
    row_header_columns: Annotated[int, Field(ge=0)] = 0
    rotation: Literal[0, 90, 180, 270] = 0
    title: TableText | None = None
    notes: list[TableText] = Field(default_factory=list)
    cells: list[Cell] = Field(min_length=1)
    continuation: TableContinuation | None = None  # with ``continues_from``


class Image(Model):
    file: str
    format: Literal["jpg", "png"]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]
    dpi: Annotated[int, Field(gt=0)]
    sha256: Sha256
    bytes: Annotated[int, Field(gt=0)]


class AltText(Model):
    """Description slot. Empty and ``needs_review`` unless a person supplies it; a model
    draft (optional, off by default) is never verified."""

    text: str = ""
    status: Literal["needs_review", "verified"] = "needs_review"
    source: Literal["none", "model_draft", "human", "original_text", "latex"] = "none"
    language: str | None = None
    model: str | None = None


class FigureText(Model):
    """A caption, credit or text inside the figure (embedded text), with its unit id."""

    id: Id
    refs: SourceRefs
    content: TextContent
    review_status: ReviewStatus = "ok"


class Figure(UnitBase):
    type: Literal["figure"] = "figure"
    kind: Literal["photo", "drawing"]
    image: Image | None = None
    name: str
    label: str | None = None  # printed page label used in the name
    small: bool = False  # small artwork (icon, bullet, logo); an adapter may skip it
    captions: list[FigureText] = Field(default_factory=list)
    credits: list[FigureText] = Field(default_factory=list)
    text: list[FigureText] = Field(default_factory=list)  # embedded text (inside the figure)
    alt_text: AltText = Field(default_factory=AltText)
    spread_with: Id | None = None
    equations: list[Id] = Field(default_factory=list)  # equations drawn inside the figure


class Equation(UnitBase):
    """A display equation. ``output`` says what the default rendering uses; an image
    fallback always carries an alt-text slot."""

    type: Literal["equation"] = "equation"
    presentation: Literal["inline", "display", "uncertain"] = "display"
    mathml: str | None = None
    latex: str | None = None
    output: Literal["text", "mathml", "mathml_parts", "image"]
    parts: list[str] = Field(default_factory=list)  # MathML of drawn parts (mathml_parts)
    image: Image | None = None
    alt_text: AltText | None = None
    content: TextContent | None = None  # text-set math kept as its text

    @model_validator(mode="after")
    def fallback_alt_text(self):
        if self.image is not None and self.alt_text is None:
            raise ValueError("An equation image fallback needs an alt-text slot")
        if self.output == "image" and self.image is None:
            raise ValueError("An image output needs its image")
        if self.output == "mathml" and not self.mathml:
            raise ValueError("A MathML output needs MathML")
        return self


class BoxNode(UnitBase):
    """Text set apart from the running text: a sidebar, a coloured callout box or a card,
    with its own units in reading order."""

    type: Literal["box"] = "box"
    box_kind: Literal["sidebar", "callout", "card"]
    children: list[Unit] = Field(default_factory=list)


Unit = Annotated[
    PageMarker
    | Paragraph
    | Heading
    | Caption
    | Footnote
    | IndexDivider
    | ListNode
    | ListItem
    | Table
    | Figure
    | Equation
    | BoxNode,
    Field(discriminator="type"),
]

for _model in (ListItem, Cell, BoxNode):
    _model.model_rebuild()


# --------------------------------------------------------------------------- book parts


class Furniture(Model):
    """A running head or foot, folio or production mark: kept, outside ``content``."""

    id: Id
    kind: Literal["running_head", "running_foot", "folio", "production_mark"]
    page: Annotated[int, Field(ge=1)]
    boxes: list[Box] = Field(default_factory=list)
    refs: SourceRefs
    content: TextContent
    confidence: Confidence | None = None
    review_status: ReviewStatus = "ok"
    flags: list[str] = Field(default_factory=list)


SuppressedReason = Literal[
    "outside_trimbox",
    "invisible_render_mode",
    "covered_by_paint",
    "not_rendered",
]


class Suppressed(Model):
    """Source text that is not content, and why: nothing disappears silently. Text outside
    the TrimBox is the ledger's explicit discard; hidden text was retained by the ledger and
    is dropped from content here with its evidence."""

    id: Id
    reason: SuppressedReason
    page: Annotated[int, Field(ge=1)]
    boxes: list[Box] = Field(default_factory=list)
    refs: SourceRefs
    text: str
    source_runs: list[SourceRun] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=dict)
    retained_by_ledger: bool  # False only for TrimBox discards

    @model_validator(mode="after")
    def offsets(self):
        validate_source_runs(self.text, self.source_runs)
        return self


class PageEntry(Model):
    index: Annotated[int, Field(ge=1)]
    label: str | None = None
    label_source: Literal["printed", "metadata", "inferred", "none"] = "none"
    width: float
    height: float
    rotation: int = 0
    source: Literal["native", "ocr", "mixed"] = "native"
    zone: Literal["front", "body", "rear"] | None = None
    section: Id | None = None
    review_status: ReviewStatus = "ok"
    flags: list[str] = Field(default_factory=list)


class TocEntry(Model):
    entry: Id | None = None  # the contents entry unit (None: a PDF outline entry)
    target_page: int | None = None
    target_label: str | None = None
    target_units: list[Id] = Field(default_factory=list)
    level: int | None = None
    confidence: Confidence


class OutlineEntry(Model):
    heading: Id
    level: Annotated[int, Field(ge=1)]
    role: str
    page: Annotated[int, Field(ge=1)]
    parent: Id | None = None


class Section(Model):
    id: Id
    zone: Literal["front", "body", "rear"]
    kind: str
    first_page: Annotated[int, Field(ge=1)]
    last_page: Annotated[int, Field(ge=1)]
    heading: Id | None = None


class PageListEntry(Model):
    page: Annotated[int, Field(ge=1)]
    label: str | None = None
    marker: Id


class Navigation(Model):
    toc: list[TocEntry] = Field(default_factory=list)
    outline: list[OutlineEntry] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    page_list: list[PageListEntry] = Field(default_factory=list)


Severity = Literal["needs_review", "must_check"]


class ReviewItem(Model):
    """One thing a person should look at: what, where, why and what to do."""

    id: Id
    unit: Id | None = None
    page: Annotated[int, Field(ge=1)]
    kind: str  # ocr_page, ocr_word, table, mathml, figure, alt_text, caption, join, ...
    reason: str
    severity: Severity
    action: str
    crop: str | None = None  # relative path of the crop image, when written
    box: Box | None = None


class Review(Model):
    counts: dict[str, int] = Field(default_factory=dict)  # by "severity:kind"
    items: list[ReviewItem] = Field(default_factory=list)


class FontStyle(Model):
    """What the book's fonts were learned to be (per book, from flags and names)."""

    name: str
    bold: bool
    italic: bool
    small_caps: bool
    characters: Annotated[int, Field(ge=0)]
    evidence: list[str] = Field(default_factory=list)


class Styles(Model):
    fonts: list[FontStyle] = Field(default_factory=list)
    body_font: str | None = None
    body_size: float | None = None


class Language(Model):
    code: str
    share: Annotated[float, Field(ge=0, le=1)]  # of the content's letters


class SourceInfo(Model):
    sha256: Sha256
    pages: Annotated[int, Field(ge=1)]


class Converter(Model):
    name: str
    version: str
    producer: Sha256  # digest of the producing code


class ProfileInfo(Model):
    id: str
    version: str
    sha256: Sha256


class RunInfo(Model):
    """Not part of the content hash."""

    date: str | None = None


class Metadata(Model):
    title: str | None = None
    languages: list[Language] = Field(default_factory=list)
    source: SourceInfo
    converter: Converter
    profile: ProfileInfo
    settings_sha256: Sha256
    content_sha256: Sha256
    run: RunInfo = Field(default_factory=RunInfo)


class Asset(Model):
    file: str
    kind: Literal["figure", "equation", "page_scan"]
    sha256: Sha256
    bytes: Annotated[int, Field(gt=0)]
    unit: Id | None = None


class SchemaInfo(Model):
    name: Literal["universal-book"] = SCHEMA_NAME
    version: Literal["1.0.0"] = SCHEMA_VERSION


class Book(Model):
    """The whole book."""

    schema_: SchemaInfo = Field(default_factory=SchemaInfo, alias="schema")
    metadata: Metadata
    pages: list[PageEntry] = Field(min_length=1)
    content: list[Unit] = Field(default_factory=list)
    furniture: list[Furniture] | None = None
    navigation: Navigation | None = None
    suppressed: list[Suppressed] | None = None
    review: Review | None = None
    styles: Styles | None = None
    assets: list[Asset] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def pages_in_order(self):
        if [p.index for p in self.pages] != list(range(1, len(self.pages) + 1)):
            raise ValueError("One page entry per physical page, in page order")
        return self


def iter_units(units):
    """Every unit of a content tree, depth first in reading order (cells and items too)."""
    for unit in units:
        yield unit
        for child in getattr(unit, "items", ()) or ():
            yield from iter_units([child])
        for child in getattr(unit, "children", ()) or ():
            yield from iter_units([child])
        for cell in getattr(unit, "cells", ()) or ():
            yield from iter_units([c for c in cell.content if not isinstance(c, TextFragment)])
