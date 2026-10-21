"""The evidence one page offers the table stage, gathered from earlier stage outputs.

Lines and spans come from the layout and the span store (text is read for evidence only,
never copied into a record), the units and streams from the lists stage, rules and fills
from the native drawings, figures and equation regions from their stages, and table boxes
from the learned detectors (support only). Furniture lines (running heads, folios,
production marks, artifacts, invisible text) are never table content.
"""

from dataclasses import dataclass, field
from statistics import median

from book_core.layout.evidence import BOLD_FLAG
from book_core.layout.frames import right_angle
from book_core.model.common import BBox
from book_core.tables.rulings import freeform, page_rules

ITALIC_FLAG = 2
FURNITURE = frozenset(
    {"running_head", "running_foot", "folio", "production_mark", "artifact", "invisible"}
)
ENTRY_KINDS = frozenset({"index_entry", "contents_entry", "definition_entry", "bibliography_entry"})


@dataclass(frozen=True)
class SpanInfo:
    id: str
    line_id: str
    text: str  # raw text, read as evidence only
    bbox: BBox
    size: float
    font: str
    bold: bool
    italic: bool
    color: int


@dataclass(frozen=True)
class LineInfo:
    id: str
    bbox: BBox
    rotation: float | None  # right angle, or None for other angles
    font_size: float
    span_ids: tuple
    unit_id: str | None
    unit_kind: str
    stream_kind: str
    region_type: str
    blank: bool
    visible: bool

    @property
    def furniture(self):
        return self.unit_kind in FURNITURE


@dataclass
class PageEvidence:
    page: int
    content: BBox
    font: float  # median font size of the page's text lines
    lines: list[LineInfo]
    spans: dict[str, SpanInfo]
    rules: list
    fills: list
    layout_tables: list[dict] = field(default_factory=list)  # {bbox, line_ids, reasons, kind}
    figures: list[dict] = field(default_factory=list)  # {id, name, bbox, object_ids, flags,
    # unit_ids, internal_unit_ids}
    equations: list[dict] = field(default_factory=list)  # {id, bbox, presentation, unit_id}
    models: dict[str, list] = field(default_factory=dict)  # {model: [(bbox, score, label)]}
    objects: dict[str, str] = field(default_factory=dict)  # drawing/image object kinds
    members: dict[str, list] = field(default_factory=dict)  # compound -> member object ids
    navigation: str | None = None  # printed navigation kind of the page (structure stage)
    freeform: list = field(default_factory=list)  # boxes of curved / slanted drawings

    def line(self, line_id):
        return self._lines[line_id]

    def __post_init__(self):
        self._lines = {line.id: line for line in self.lines}


def body_style(evidence):
    """The page's dominant (font, size) by characters of visible horizontal lines."""
    weight = {}
    for line in evidence.lines:
        if line.blank or not line.visible or line.rotation != 0 or line.furniture:
            continue
        for sid in line.span_ids:
            span = evidence.spans[sid]
            key = (span.font, round(span.size))
            weight[key] = weight.get(key, 0) + len(span.text.strip())
    return max(weight, key=weight.get) if weight else None


def page_evidence(
    layout, store, objects, built, figures=None, equations=None, models=None, navigation=None
):
    """PageEvidence of one page from its layout, span store, native objects (analysis
    objects and compounds), lists-stage units/order, figure records, equation records and
    the learned detectors' table boxes ``{model: [(bbox, score, label)]}``; ``navigation``
    is the page's printed navigation kind from the structure stage (contents, index, ...)."""
    unit_of = {lid: unit for unit in built.units for lid in unit.line_ids}
    stream_of = {lid: stream.kind for stream in built.order.streams for lid in stream.line_ids}
    region_of = {lid: region.type for region in layout.regions for lid in region.line_ids}
    lines = []
    for line in layout.lines:
        unit = unit_of.get(line.id)
        lines.append(
            LineInfo(
                id=line.id,
                bbox=line.bbox,
                rotation=right_angle(line.rotation),
                font_size=line.font_size,
                span_ids=tuple(line.span_ids),
                unit_id=unit.id if unit else None,
                unit_kind=unit.kind if unit else "none",
                stream_kind=stream_of.get(line.id, "none"),
                region_type=region_of.get(line.id, "none"),
                blank=line.blank,
                visible=line.visible,
            )
        )
    spans = {}
    for line in layout.lines:
        for sid in line.span_ids:
            span = store.spans[sid]
            spans[sid] = SpanInfo(
                id=sid,
                line_id=line.id,
                text=span.raw_text,
                bbox=span.bbox,
                size=span.size,
                font=span.font,
                bold=bool(span.flags & BOLD_FLAG) or "bold" in span.font.lower(),
                italic=bool(span.flags & ITALIC_FLAG) or "italic" in span.font.lower(),
                color=span.color,
            )
    sizes = [line.font_size for line in layout.lines if not line.blank and line.font_size > 0]
    font = median(sizes) if sizes else 10.0
    rules, fills = page_rules(objects, font)
    layout_tables = [
        {
            "bbox": region.bbox,
            "line_ids": list(region.line_ids),
            "reasons": list(region.reasons),
        }
        for region in layout.regions
        if region.type == "table_candidate"
    ]
    for block in layout.blocks:
        if block.kind == "table" and not any(t["bbox"] == block.bbox for t in layout_tables):
            layout_tables.append(
                {"bbox": block.bbox, "line_ids": list(block.line_ids), "reasons": block.reasons}
            )
    figure_rows = [
        {
            "id": record.id,
            "name": record.name,
            "bbox": record.bbox,
            "object_ids": list(getattr(record, "object_ids", []) or []),
            "flags": list(record.review_flags),
            # Units the figure links as captions or credits (never table titles), and the
            # text inside its region (internal text: weaker, a review flag only).
            "unit_ids": [link.unit_id for link in (*record.captions, *record.credits)],
            "internal_unit_ids": [link.unit_id for link in record.internal_text],
        }
        for record in (figures.figures if figures is not None else [])
    ]
    equation_rows = []
    if equations is not None:
        unit_of_region = {u.equation_id: u.id for u in equations.units}
        for region in equations.regions:
            equation_rows.append(
                {
                    "id": region.id,
                    "bbox": region.bbox,
                    "presentation": region.presentation,
                    "source": region.source,
                    "owner": region.owner.kind if region.owner else None,
                    "unit_id": unit_of_region.get(region.id),
                    "line_ids": list(region.line_ids),
                }
            )
    kinds = {o.id: o.kind for o in objects if o.kind in {"drawing", "image", "compound"}}
    members = {o.id: list(o.member_ids) for o in objects if o.kind == "compound"}
    return PageEvidence(
        page=layout.page,
        content=layout.content_bbox,
        font=font,
        lines=lines,
        spans=spans,
        rules=rules,
        fills=fills,
        layout_tables=layout_tables,
        figures=figure_rows,
        equations=equation_rows,
        models=models or {},
        objects=kinds,
        members=members,
        navigation=navigation,
        freeform=freeform(objects),
    )
