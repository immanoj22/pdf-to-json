"""Table evidence without ruled grids, and continuity of ruled grids.

Aligned tables: rows are lines sharing a baseline band with at least two separated cells;
consecutive rows form a run; cells are grouped into columns by overlap or edge alignment.
A run is a table candidate when at least two columns recur in most rows, at least one of
them holds mostly numeric cells, and no cell reads as running text. Text-only alignment is
not enough: unframed card grids and indexes align the same way.

Ruled grids: separate ruled objects that share at least two interior column rules and sit
within one row height of each other are one table; a heavy rule between them does not
split it. Shared outer edges alone are not evidence (any two boxes of equal width share them).

All distances are in font or line-height units. The geometry is frame-agnostic: callers
pass horizontal lines of one reading frame.
"""

from dataclasses import dataclass, field
from statistics import median

from book_core.layout.evidence import line_text, numeric_cell, paragraph_like

MIN_ROWS = 3
COLUMN_SUPPORT = 0.6
NUMERIC_SHARE = 0.7


@dataclass
class AlignedTable:
    line_ids: list[str]
    rows: int
    columns: int
    numeric_columns: int
    bbox: tuple[float, float, float, float]
    reasons: list[str] = field(default_factory=list)


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent, a, b):
    a, b = _find(parent, a), _find(parent, b)
    if a != b:
        parent[max(a, b)] = min(a, b)


def _clusters(items, linked):
    parent = list(range(len(items)))
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if linked(items[i], items[j]):
                _union(parent, i, j)
    groups = {}
    for i, item in enumerate(items):
        groups.setdefault(_find(parent, i), []).append(item)
    return list(groups.values())


def aligned_tables(lines, store, body_style=None):
    """Aligned-cell table candidates among horizontal, visible text lines of one frame."""
    cells = [line for line in lines if not line.blank and line_text(line, store)]
    if len(cells) < 2 * MIN_ROWS:
        return []
    height = median(line.bbox.y1 - line.bbox.y0 for line in cells)
    font_unit = median(line.font_size for line in cells if line.font_size > 0)

    def same_row(a, b):
        overlap = min(a.bbox.y1, b.bbox.y1) - max(a.bbox.y0, b.bbox.y0)
        shorter = min(a.bbox.y1 - a.bbox.y0, b.bbox.y1 - b.bbox.y0)
        centre = abs((a.bbox.y0 + a.bbox.y1) - (b.bbox.y0 + b.bbox.y1)) / 2
        return overlap >= 0.5 * shorter and centre <= 0.4 * height

    rows = []
    for members in _clusters(cells, same_row):
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda line: line.bbox.x0)
        gaps = [b.bbox.x0 - a.bbox.x1 for a, b in zip(ordered, ordered[1:], strict=False)]
        if min(gaps) < font_unit:
            continue
        rows.append(ordered)
    if len(rows) < MIN_ROWS:
        return []

    def centre_y(row):
        return median((line.bbox.y0 + line.bbox.y1) / 2 for line in row)

    def x_range(row):
        return min(line.bbox.x0 for line in row), max(line.bbox.x1 for line in row)

    # Runs of vertically adjacent multi-cell rows with overlapping horizontal extent. Ordering
    # rows by position only finds neighbours inside one candidate; it is not reading order.
    rows.sort(key=centre_y)
    runs, current = [], [rows[0]]
    for previous, row in zip(rows, rows[1:], strict=False):
        (a0, a1), (b0, b1) = x_range(previous), x_range(row)
        overlap = min(a1, b1) - max(a0, b0)
        close = centre_y(row) - centre_y(previous) <= 3.0 * height
        if close and overlap >= 0.5 * min(a1 - a0, b1 - b0):
            current.append(row)
        else:
            runs.append(current)
            current = [row]
    runs.append(current)

    tables = []
    for run in runs:
        if len(run) < MIN_ROWS:
            continue
        found = _table_from_run(run, store, body_style, font_unit, lines)
        if found is not None:
            tables.append(found)
    return tables


def _table_from_run(run, store, body_style, font_unit, neighbours):
    members = [(index, line) for index, row in enumerate(run) for line in row]

    def same_column(a, b):
        (_, x), (_, y) = a, b
        overlap = min(x.bbox.x1, y.bbox.x1) - max(x.bbox.x0, y.bbox.x0)
        narrower = min(x.bbox.x1 - x.bbox.x0, y.bbox.x1 - y.bbox.x0)
        edges = (
            abs(x.bbox.x0 - y.bbox.x0) <= 0.75 * font_unit
            or abs(x.bbox.x1 - y.bbox.x1) <= 0.75 * font_unit
            or abs((x.bbox.x0 + x.bbox.x1) - (y.bbox.x0 + y.bbox.x1)) <= 1.5 * font_unit
        )
        return overlap >= 0.5 * narrower or edges

    columns = []
    for group in _clusters(members, same_column):
        if len({index for index, _ in group}) >= COLUMN_SUPPORT * len(run):
            columns.append([line for _, line in group])
    if len(columns) < 2:
        return None
    # Two separate clusters may still interleave; each supported column must be distinct.
    columns.sort(key=lambda column: median(line.bbox.x0 for line in column))
    numeric = sum(
        sum(numeric_cell(line_text(line, store)) for line in column) >= NUMERIC_SHARE * len(column)
        for column in columns
    )
    cells = [line for column in columns for line in column]
    if any(paragraph_like(line, store, body_style, neighbours) for line in cells):
        return None
    if not numeric:
        # Short text-only cells also occur in unframed card grids and indexes; without
        # numeric columns or rules the alignment alone is not table evidence.
        return None
    reasons = [f"{numeric} aligned column(s) of numeric cells across {len(run)} rows"]
    run_lines = [line for row in run for line in row]
    return AlignedTable(
        line_ids=[line.id for line in run_lines],
        rows=len(run),
        columns=len(columns),
        numeric_columns=numeric,
        bbox=(
            min(line.bbox.x0 for line in run_lines),
            min(line.bbox.y0 for line in run_lines),
            max(line.bbox.x1 for line in run_lines),
            max(line.bbox.y1 for line in run_lines),
        ),
        reasons=["Cells aligned in rows and columns without a ruled grid", *reasons],
    )


def grid_profile(obj, objects):
    """Positions of the vertical and horizontal strokes of a ruled object (or compound)."""
    parts = [objects[m] for m in getattr(obj, "member_ids", [])] if obj.kind == "compound" else []
    parts = parts or [obj]
    verticals, horizontals = [], []
    for part in parts:
        for item in part.path_items:
            c = item.coordinates
            if item.operator == "l" and len(c) >= 4:
                if abs(c[1] - c[3]) < 0.5 and abs(c[0] - c[2]) >= 8:
                    horizontals.append((c[1] + c[3]) / 2)
                elif abs(c[0] - c[2]) < 0.5 and abs(c[1] - c[3]) >= 8:
                    verticals.append((c[0] + c[2]) / 2)
            elif item.operator == "re" and len(c) >= 4:
                verticals += [c[0], c[2]]
                horizontals += [c[1], c[3]]
    return sorted(verticals), sorted(horizontals)


def row_height(horizontals, fallback):
    unique = []
    for y in sorted(horizontals):
        if not unique or y - unique[-1] > 1.0:
            unique.append(y)
    steps = [b - a for a, b in zip(unique, unique[1:], strict=False)]
    return median(steps) if steps else fallback


def same_grid(a_box, a_profile, b_box, b_profile, font_unit):
    """Two ruled grids continue one table: shared column rules, at most a row apart."""
    overlap = min(a_box.x1, b_box.x1) - max(a_box.x0, b_box.x0)
    narrower = min(a_box.x1 - a_box.x0, b_box.x1 - b_box.x0)
    if overlap < 0.5 * narrower:
        return False
    gap = max(b_box.y0 - a_box.y1, a_box.y0 - b_box.y1)
    reach = max(
        row_height(a_profile[1], a_box.y1 - a_box.y0), row_height(b_profile[1], b_box.y1 - b_box.y0)
    )
    if gap > reach:
        return False
    tolerance = 0.25 * font_unit
    edges = [a_box.x0, a_box.x1, b_box.x0, b_box.x1]
    distinct = []
    for x in a_profile[0]:
        # Outer edges are shared by any two boxes of one width; only interior column
        # rules show that two grids divide the same columns.
        if any(abs(x - edge) <= tolerance for edge in edges):
            continue
        if not distinct or x - distinct[-1] > tolerance:
            distinct.append(x)
    shared = [x for x in distinct if any(abs(x - y) <= tolerance for y in b_profile[0])]
    return len(shared) >= 2
