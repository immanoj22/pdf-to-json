"""Universal semantic nodes; source content consists exclusively of span references."""

from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from book_core.model.common import (
    BBox,
    Confidence,
    CoreModel,
    ExternalDescription,
    Identifier,
    Provenance,
    Relationship,
    SemanticRole,
    SpanRef,
    TextDirection,
    VisualStyle,
)


class BaseNode(CoreModel):
    id: Identifier
    type: str
    role: SemanticRole | None = None
    content: list[SpanRef] = Field(default_factory=list)
    children: list["Node"] = Field(default_factory=list)
    source_page: PositiveInt | None = None
    bbox: BBox | None = None
    source_spans: list[Identifier] = Field(default_factory=list)
    visual_refs: list[Identifier] = Field(default_factory=list)
    language: str = "und"
    script: str | None = None
    text_direction: TextDirection | None = None
    style: VisualStyle = Field(default_factory=VisualStyle)
    confidence: Confidence | None = None
    relationships: list[Relationship] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def source_refs(self) -> "BaseNode":
        ids = [ref.span_id for ref in self.content]
        ranges = [(ref.span_id, ref.start, ref.end) for ref in self.content]
        if len(ranges) != len(set(ranges)):
            raise ValueError("Repeated content span inside a node")
        if not set(ids).issubset(self.source_spans):
            raise ValueError("Content must have corresponding source-span provenance")
        return self


class InlineRun(BaseNode):
    type: Literal["inline_run"] = "inline_run"
    guessed_role: SemanticRole | None = None
    role_confidence: Confidence | None = None


class Heading(BaseNode):
    type: Literal["heading"] = "heading"
    level: PositiveInt


class Paragraph(BaseNode):
    type: Literal["paragraph"] = "paragraph"


class ListNode(BaseNode):
    type: Literal["list"] = "list"
    list_kind: Literal["ordered", "unordered", "unknown"] = "unknown"


class ListItem(BaseNode):
    type: Literal["list_item"] = "list_item"


class DefinitionList(BaseNode):
    type: Literal["definition_list"] = "definition_list"


class TableCell(CoreModel):
    row: NonNegativeInt
    column: NonNegativeInt
    row_span: PositiveInt = 1
    column_span: PositiveInt = 1
    node_ids: list[Identifier] = Field(default_factory=list)


class Table(BaseNode):
    type: Literal["table"] = "table"
    row_count: NonNegativeInt | None = None
    column_count: NonNegativeInt | None = None
    cells: list[TableCell] = Field(default_factory=list)

    @model_validator(mode="after")
    def grid_bounds(self) -> "Table":
        occupied: set[tuple[int, int]] = set()
        for cell in self.cells:
            if self.row_count is not None and cell.row + cell.row_span > self.row_count:
                raise ValueError("Table cell extends past row count")
            if self.column_count is not None and cell.column + cell.column_span > self.column_count:
                raise ValueError("Table cell extends past column count")
            for row in range(cell.row, cell.row + cell.row_span):
                for column in range(cell.column, cell.column + cell.column_span):
                    if (row, column) in occupied:
                        raise ValueError("Overlapping table cells")
                    occupied.add((row, column))
        return self


class Figure(BaseNode):
    type: Literal["figure"] = "figure"
    asset_ids: list[Identifier] = Field(default_factory=list)
    embedded_text: list[InlineRun] = Field(default_factory=list)
    image_description: ExternalDescription = Field(
        description="Required but external; unresolved descriptions require review",
        json_schema_extra={"required_but_external": True},
    )


class Caption(BaseNode):
    type: Literal["caption"] = "caption"


class Sidebar(BaseNode):
    type: Literal["sidebar"] = "sidebar"


class Callout(BaseNode):
    type: Literal["callout"] = "callout"


class Quote(BaseNode):
    type: Literal["quote"] = "quote"


class Equation(BaseNode):
    type: Literal["equation"] = "equation"


class Math(BaseNode):
    type: Literal["math"] = "math"


class Footnote(BaseNode):
    type: Literal["footnote"] = "footnote"


class Note(BaseNode):
    type: Literal["note"] = "note"


class NoteRef(BaseNode):
    type: Literal["note_ref"] = "note_ref"
    target_id: Identifier


class Reference(BaseNode):
    type: Literal["reference"] = "reference"
    external_identifier: str | None = None


class IndexEntry(BaseNode):
    type: Literal["index_entry"] = "index_entry"
    target_ids: list[Identifier] = Field(default_factory=list)


class PageMarker(BaseNode):
    type: Literal["page_marker"] = "page_marker"


Node = Annotated[
    InlineRun
    | Heading
    | Paragraph
    | ListNode
    | ListItem
    | DefinitionList
    | Table
    | Figure
    | Caption
    | Sidebar
    | Callout
    | Quote
    | Equation
    | Math
    | Footnote
    | Note
    | NoteRef
    | Reference
    | IndexEntry
    | PageMarker,
    Field(discriminator="type"),
]

for _node_class in [BaseNode, *BaseNode.__subclasses__()]:
    _node_class.model_rebuild(_types_namespace=globals())
