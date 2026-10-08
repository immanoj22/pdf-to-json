"""Layout invariants that must hold on any page, checked from a layout and its evidence.

The checker reads a serialised layout (dict) so that layouts written by older versions can
be measured too; it never repairs anything. Each invariant returns human-readable
violations. Thresholds are in font, line-height or content-frame units.

I1  Lanes have positive width.
I2  Bands of one scope do not overlap along the scope's stacking axis.
I3  Figures embed no paragraph-like lines.
I4  Figure boxes stay inside the content frame; furniture-zone lines are never embedded.
I5  Rotated lines that share a right-angle rotation take part in structure; rotated text is
    a credit only when small, isolated and beside a figure edge.
I6  Aligned-cell tables are table candidates; continuous ruled grids are one table.
I7  Narrow edge strips open no full-height lane; locator columns are not text columns.
"""

from collections import defaultdict

from book_core.layout.evidence import (
    ROTATED_STRUCTURE_LINES,
    credit_like,
    line_text,
    median_font,
    page_body_style,
    paragraph_like,
    rotation_key,
    short_reference,
    text_lines,
    token_count,
)
from book_core.layout.frames import across_axis, frame_line, right_angle
from book_core.layout.models import VisualBlock, VisualLine
from book_core.layout.tables import aligned_tables, grid_profile, same_grid
from book_core.model.common import BBox

INVARIANTS = ["I1", "I2", "I3", "I4", "I5", "I6", "I7"]
EDGE_ZONE = 0.07
EDGE_STRIP_WIDTH = 0.10
EDGE_STRIP_HEIGHT = 0.5
EDGE_TOUCH = 0.05


def _bbox(value):
    return value if isinstance(value, BBox) else BBox(**value)


def check(layout, analysis):
    """Violations per invariant for one page. `layout` is a PageLayout or its dict."""
    data = layout if isinstance(layout, dict) else layout.model_dump(mode="json")
    store = analysis.native.page.store
    objects = {obj.id: obj for obj in analysis.all_objects()}
    lines = [VisualLine.model_validate(line) for line in data["lines"]]
    by_id = {line.id: line for line in lines}
    blocks = [VisualBlock.model_validate(block) for block in data["blocks"]]
    content = _bbox(data["content_bbox"])
    scopes = {scope["id"]: scope for scope in data["scopes"]}
    page_scope = next(scope["id"] for scope in data["scopes"] if scope["kind"] == "page")
    region_of = {lid: region for region in data["regions"] for lid in region["line_ids"]}
    texts = text_lines(lines)
    body = page_body_style(lines, store)
    body_size = body[1] if body else None
    font_unit = median_font(lines)
    figures = [block for block in blocks if block.kind == "figure"]
    result = {name: [] for name in INVARIANTS}

    # I1
    for band in data["bands"]:
        for lane in band["lanes"]:
            if lane["x1"] <= lane["x0"]:
                result["I1"].append(
                    f"band {band['id'][:8]} lane {lane['index']} x0={lane['x0']:.1f}"
                    f" >= x1={lane['x1']:.1f}"
                )

    # I2
    tolerance = max(1.0, 0.5 * font_unit)
    by_scope = defaultdict(list)
    for band in data["bands"]:
        by_scope[band["scope_id"]].append(band)
    for scope_id, bands in by_scope.items():
        axis = across_axis(scopes.get(scope_id, {}).get("rotation", 0))
        lo, hi = ("y0", "y1") if axis == "y" else ("x0", "x1")
        for i, a in enumerate(bands):
            for b in bands[i + 1 :]:
                overlap = min(a["bbox"][hi], b["bbox"][hi]) - max(a["bbox"][lo], b["bbox"][lo])
                if overlap > tolerance:
                    result["I2"].append(
                        f"bands {a['id'][:8]} and {b['id'][:8]} overlap {overlap:.1f}pt"
                    )

    # I3 and I4
    horizontal_texts = [line for line in texts if line.horizontal]
    height = content.y1 - content.y0
    for region in data["regions"]:
        if region["type"] != "figure":
            continue
        for lid in region["line_ids"]:
            line = by_id[lid]
            if paragraph_like(line, store, body, horizontal_texts):
                result["I3"].append(
                    f"paragraph-like line embedded: {line_text(line, store)[:50]!r}"
                )
            centre = (line.bbox.y0 + line.bbox.y1) / 2
            if (
                centre <= content.y0 + EDGE_ZONE * height
                or centre >= content.y1 - EDGE_ZONE * height
            ):
                result["I4"].append(
                    f"furniture-zone line embedded: {line_text(line, store)[:50]!r}"
                )
    for block in figures:
        b = block.bbox
        if (
            b.x0 < content.x0 - 1
            or b.y0 < content.y0 - 1
            or b.x1 > content.x1 + 1
            or b.y1 > content.y1 + 1
        ):
            result["I4"].append(
                f"figure {block.id[:8]} box {b.x0:.0f},{b.y0:.0f},{b.x1:.0f},{b.y1:.0f}"
                " leaves the content frame"
            )

    # I5
    rotated = [line for line in texts if not line.horizontal]
    groups = defaultdict(list)
    for line in rotated:
        groups[rotation_key(line)].append(line)
    figure_boxes = [block.bbox for block in figures]
    for key, members in groups.items():
        if len(members) < ROTATED_STRUCTURE_LINES or right_angle(key) is None:
            continue
        for line in members:
            region = region_of.get(line.id)
            if region is None or region.get("band_id") is None:
                result["I5"].append(
                    f"rotated line outside structure ({key} deg): {line_text(line, store)[:40]!r}"
                )
            # Cells of a rotated structure are credits only with full credit evidence.
            if region and region["type"] == "credit_candidate":
                if credit_like(line, lines, figure_boxes, body_size):
                    continue
                result["I5"].append(
                    f"rotated text labelled credit without credit evidence: "
                    f"{line_text(line, store)[:40]!r}"
                )

    # I6 (a): aligned-cell tables among free text, per reading frame.
    tabled = {
        lid
        for region in data["regions"]
        if region["type"] in {"table_candidate", "figure"}
        or (region["type"] == "unknown" and region.get("proposed_type") == "table_candidate")
        for lid in region["line_ids"]
    }
    frames = defaultdict(list)
    for line in texts:
        angle = 0 if line.horizontal else right_angle(line.rotation)
        if angle is not None:
            frames[angle].append(line if angle == 0 else frame_line(line, angle))
    for angle, members in frames.items():
        for table in aligned_tables(members, store, body):
            missing = [lid for lid in table.line_ids if lid not in tabled]
            if len(missing) > 0.5 * len(table.line_ids):
                result["I6"].append(
                    f"aligned table ({table.rows} rows x {table.columns} columns, {angle} deg)"
                    f" not a table candidate"
                )
    # I6 (b): one ruled grid split into several table candidates.
    tables = [block for block in blocks if block.kind == "table"]
    profiles = {}
    for block in tables:
        verticals, horizontals = [], []
        for oid in block.object_ids:
            if oid in objects:
                v, h = grid_profile(objects[oid], objects)
                verticals += v
                horizontals += h
        profiles[block.id] = (sorted(verticals), sorted(horizontals))
    for i, a in enumerate(tables):
        for b in tables[i + 1 :]:
            if same_grid(a.bbox, profiles[a.id], b.bbox, profiles[b.id], font_unit):
                result["I6"].append(f"ruled grid split into tables {a.id[:8]} and {b.id[:8]}")

    # I7 (a): narrow edge strip opening a full-height lane.
    width = content.x1 - content.x0
    for band in data["bands"]:
        if band["scope_id"] != page_scope:
            continue
        box = _bbox(band["bbox"])
        if box.y1 - box.y0 < EDGE_STRIP_HEIGHT * height or len(band["lanes"]) < 2:
            continue
        for lane in band["lanes"]:
            narrow = lane["x1"] - lane["x0"] <= EDGE_STRIP_WIDTH * width
            at_edge = (
                lane["x0"] <= content.x0 + EDGE_TOUCH * width
                or lane["x1"] >= content.x1 - EDGE_TOUCH * width
            )
            if lane["line_count"] == 0 and narrow and at_edge:
                result["I7"].append(
                    f"band {band['id'][:8]} has a text-free edge lane"
                    f" {lane['x0']:.0f}-{lane['x1']:.0f} across {box.y1 - box.y0:.0f}pt"
                )
    # I7 (b): a lane of short locator cells counted as a text column.
    lane_lines = defaultdict(list)
    for region in data["regions"]:
        if region.get("band_id") is not None and region.get("lane_index") is not None:
            for lid in region["line_ids"]:
                line = by_id[lid]
                if not line.blank:
                    lane_lines[(region["band_id"], region["lane_index"])].append(line)
    for band in data["bands"]:
        for lane in band["lanes"]:
            if lane["kind"] != "column":
                continue
            members = lane_lines.get((band["id"], lane["index"]), [])
            if len(members) < 3:
                continue
            words = [line_text(line, store) for line in members]
            if not all(token_count(text) <= 3 for text in words):
                continue
            if sum(short_reference(text) for text in words) < 0.75 * len(words):
                continue
            neighbours = [
                line
                for other in band["lanes"]
                if abs(other["index"] - lane["index"]) == 1
                for line in lane_lines.get((band["id"], other["index"]), [])
            ]
            aligned = sum(
                any(
                    min(line.bbox.y1, other.bbox.y1) > max(line.bbox.y0, other.bbox.y0)
                    for other in neighbours
                )
                for line in members
            )
            if aligned >= 0.75 * len(members):
                result["I7"].append(
                    f"band {band['id'][:8]} lane {lane['index']}: locator column counted as text"
                )
    return result


def counts(violations):
    return {name: len(items) for name, items in violations.items()}
