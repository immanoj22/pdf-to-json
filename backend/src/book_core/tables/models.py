"""Table records: a grid of cells over line ids and span ranges, with its evidence.

A cell holds whole lines (``line_ids``) and, where one PDF line carries the text of several
cells, span ranges (``span_refs``); no text is copied. Display equation units and figures
read inside a cell are named by id. Every line of a table belongs to it once: as a whole
line of one cell, or through span ranges that cover the line's text exactly once across
its cells. Rows and columns are frame intervals (``rotation``: the table's reading frame).
Confidence is a rule heuristic, not a calibrated probability. A table spanning pages is one
record per page; continuation is marked, never joined here.

Each cell has a role (column header, row header, section row or data), the ids of the
header cells that label it (column headers above it including spanning group headers, the
row header of its row, the section row above it) and its content in reading order: whole
lists-stage units (paragraphs, list items), the remaining lines and span ranges as text,
display equation units and figures, all by reference. A table's title and notes are linked
units next to it (or lines inside its region, which the table owns); candidates that are not
linked are kept with the reason, for review.
"""

from typing import Literal

from pydantic import Field, model_validator

from book_core.furniture.models import LabelSource
from book_core.model.common import (
    BBox,
    Confidence,
    CoreModel,
    Digest,
    Identifier,
    Provenance,
    SpanRef,
)

Feature = float | int | str | bool | None
RejectKind = Literal[
    "no_text",
    "mixed_rotation",
    "graphic_organizer",
    "timeline",
    "multi_column_text",
    "index_or_contents",
    "single_source",
    "not_a_grid",
    "overlaps_table",
    "figure_panel",
]


CellRole = Literal["column_header", "row_header", "section", "data"]
ContentKind = Literal["paragraph", "list_item", "text", "equation", "figure"]


class CellContent(CoreModel):
    """One piece of a cell's content in reading order, by reference: a whole unit (its
    lines listed), loose lines or span ranges (``text``), an equation unit or a figure."""

    kind: ContentKind
    unit_id: Identifier | None = None  # lists-stage unit, or equation unit
    line_ids: list[Identifier] = Field(default_factory=list)
    span_refs: list[SpanRef] = Field(default_factory=list)
    figure_id: Identifier | None = None


class TableCell(CoreModel):
    id: Identifier
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    header: bool = False
    bbox: BBox  # page coordinates
    line_ids: list[Identifier] = Field(default_factory=list)
    span_refs: list[SpanRef] = Field(default_factory=list)  # parts of lines shared by cells
    # Lists-stage units lying wholly in this cell (list items, paragraphs): the cell's content
    # structure, kept as it was (lists in cells). Units cut by cell boundaries are not here.
    unit_ids: list[Identifier] = Field(default_factory=list)
    equation_unit_ids: list[Identifier] = Field(default_factory=list)
    figure_ids: list[Identifier] = Field(default_factory=list)
    role: CellRole = "data"
    header_cell_ids: list[Identifier] = Field(default_factory=list)  # cells labelling this one
    content: list[CellContent] = Field(default_factory=list)  # reading order

    @property
    def empty(self):
        return not (self.line_ids or self.span_refs or self.equation_unit_ids or self.figure_ids)

    @model_validator(mode="after")
    def content_covers(self):
        lines = [lid for item in self.content for lid in item.line_ids]
        refs = [r for item in self.content for r in item.span_refs]
        if sorted(lines) != sorted(self.line_ids) or len(refs) != len(self.span_refs):
            raise ValueError("Cell content must hold the cell's lines and span ranges once")
        if {(r.span_id, r.start, r.end) for r in refs} != {
            (r.span_id, r.start, r.end) for r in self.span_refs
        }:
            raise ValueError("Cell content must hold the cell's span ranges")
        equations = [i.unit_id for i in self.content if i.kind == "equation"]
        figures = [i.figure_id for i in self.content if i.kind == "figure"]
        if sorted(equations) != sorted(self.equation_unit_ids) or sorted(figures) != sorted(
            self.figure_ids
        ):
            raise ValueError("Cell content must hold the cell's equations and figures")
        return self


class Continuation(CoreModel):
    table_id: Identifier
    page: int = Field(ge=1)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)


class TableText(CoreModel):
    """A title or note of a table: a final-view unit next to it (``unit_id``), or lines
    inside its region that the table owns (``unit_id`` None)."""

    role: Literal["title", "note"]
    unit_id: Identifier | None = None
    line_ids: list[Identifier] = Field(min_length=1)
    rule: str
    numbered: bool = False  # opens with the book's table label and a number
    confidence: Confidence


class UnlinkedText(CoreModel):
    """A title or note candidate next to a table that is not linked (review)."""

    role: Literal["title", "note"]
    unit_id: Identifier | None = None
    line_ids: list[Identifier] = Field(min_length=1)
    reason: str


class TableAnchor(CoreModel):
    """Where the table is read: the place of its first line in the lists-stage order (the
    stream and the line before it there, None at the stream start)."""

    stream_id: Identifier
    after_line_id: Identifier | None = None
    position: int = Field(ge=-1)


class TableRecord(CoreModel):
    id: Identifier
    owns_text: bool = True  # False: a possible table; its lines stay in their units
    page: int = Field(ge=1)
    page_label: str | None = None
    label_source: LabelSource = "none"
    bbox: BBox
    rotation: Literal[0, 90, 180, 270] = 0
    rows: list[tuple[float, float]] = Field(min_length=1)  # frame intervals
    columns: list[tuple[float, float]] = Field(min_length=1)
    header_rows: int = Field(default=0, ge=0)
    row_header_columns: int = Field(default=0, ge=0)  # stub columns holding row headers
    cells: list[TableCell] = Field(min_length=1)
    line_ids: list[Identifier] = Field(min_length=1)  # every line of the table, once
    source_unit_ids: list[Identifier] = Field(default_factory=list)  # units the lines left
    structure_method: str
    evidence: dict[str, float] = Field(default_factory=dict)  # source -> strength
    families: list[str] = Field(min_length=2)  # never one evidence family alone
    structure_evidence: dict[str, Feature] = Field(default_factory=dict)
    absorbed_figure_ids: list[Identifier] = Field(default_factory=list)  # rules/fills as figures
    anchor: TableAnchor
    continues_from: Continuation | None = None
    continues_to: Continuation | None = None
    title: TableText | None = None
    notes: list[TableText] = Field(default_factory=list)
    unlinked_texts: list[UnlinkedText] = Field(default_factory=list)
    confidence: Confidence
    reasons: list[str] = Field(min_length=1)
    review_flags: list[str] = Field(default_factory=list)
    provenance: Provenance | None = None

    @property
    def review_required(self):
        return bool(self.review_flags)

    @model_validator(mode="after")
    def consistent(self):
        rows, columns = len(self.rows), len(self.columns)
        taken = set()
        for cell in self.cells:
            if cell.row + cell.row_span > rows or cell.column + cell.column_span > columns:
                raise ValueError("A table cell extends past the grid")
            for r in range(cell.row, cell.row + cell.row_span):
                for c in range(cell.column, cell.column + cell.column_span):
                    if (r, c) in taken:
                        raise ValueError("Overlapping table cells")
                    taken.add((r, c))
        if len(taken) != rows * columns:
            raise ValueError("Table cells must cover the grid exactly")
        whole = [lid for cell in self.cells for lid in cell.line_ids]
        if len(whole) != len(set(whole)):
            raise ValueError("A whole line belongs to one cell")
        if not set(whole) <= set(self.line_ids) or len(self.line_ids) != len(set(self.line_ids)):
            raise ValueError("Cell lines must be lines of the table, listed once")
        if self.header_rows > rows:
            raise ValueError("More header rows than rows")
        ids = {cell.id for cell in self.cells}
        if len(ids) != len(self.cells):
            raise ValueError("Duplicate table cell id")
        if any(h not in ids or h == c.id for c in self.cells for h in c.header_cell_ids):
            raise ValueError("A header reference must name another cell of the table")
        texts = [t for t in [self.title, *self.notes] if t is not None]
        inside = [lid for t in texts if t.unit_id is None for lid in t.line_ids]
        if len(inside) != len(set(inside)) or set(inside) & set(whole):
            raise ValueError("A title or note line inside the table belongs to no cell")
        if not set(inside) <= set(self.line_ids):
            raise ValueError("Title or note lines inside the table must be table lines")
        if any(t.role != "title" for t in [self.title] if t) or any(
            t.role != "note" for t in self.notes
        ):
            raise ValueError("Title and note roles must match their fields")
        return self


class RejectedRegion(CoreModel):
    """A candidate that is not a table, kept for review with its reason."""

    bbox: BBox
    kind: RejectKind
    evidence: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(min_length=1)
    figure_ids: list[Identifier] = Field(default_factory=list)  # figures it overlaps


class FigureNote(CoreModel):
    """A figure the table stage has evidence about (recorded beside the figure)."""

    figure_id: Identifier
    kind: Literal["table_piece", "in_table_cell", "graphic_organizer_piece"]
    table_id: Identifier | None = None
    reasons: list[str] = Field(min_length=1)


class PageTables(CoreModel):
    source_sha256: Digest
    page: int = Field(gt=0)
    version: str
    tables: list[TableRecord] = Field(default_factory=list)  # own their text
    possible_tables: list[TableRecord] = Field(default_factory=list)  # review; own nothing
    rejected: list[RejectedRegion] = Field(default_factory=list)
    figure_notes: list[FigureNote] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def lines_once(self):
        if any(not t.owns_text for t in self.tables) or any(
            t.owns_text for t in self.possible_tables
        ):
            raise ValueError("Only tables that own their text are tables; others are possible")
        lines = [lid for table in self.tables for lid in table.line_ids]
        if len(lines) != len(set(lines)):
            raise ValueError("A line belongs to at most one table")
        ids = [t.id for t in self.tables]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate table record")
        return self


class BookTables(CoreModel):
    source_sha256: Digest
    pages: int = Field(gt=0)
    version: str
    config: dict
    settings: dict
    models: dict[str, str] = Field(default_factory=dict)  # model -> repo@revision/settings
    tables: int = Field(ge=0)
    possible_tables: int = Field(default=0, ge=0)
    by_page: dict[str, int] = Field(default_factory=dict)
    rejected: dict[str, int] = Field(default_factory=dict)
    continuations: int = Field(default=0, ge=0)
    figure_notes: dict[str, int] = Field(default_factory=dict)
    review: dict[str, int] = Field(default_factory=dict)
    texts: dict = Field(default_factory=dict)  # learned labels, title side, link counts
    cells: dict = Field(default_factory=dict)  # role and content kind counts
    diagnostics: list[str] = Field(default_factory=list)
    cache_key_inputs: dict[str, str] = Field(default_factory=dict)
