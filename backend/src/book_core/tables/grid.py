"""Grid structure of one table in its reading frame: rows, columns, spans and header rows.

Frame x runs along the text, frame y down the lines (``layout.frames``), so a rotated table
is read like an upright one. The text atoms are the spans of the table's lines.

- **Columns**: interior vertical rules covering most of the table height; otherwise, and
  in addition where no rule exists, gaps that no text crosses in nearly every text band
  (a few bands may cross: spanning headers and section rows). A gap must be wider than a
  word space. Sparse bands (at most half as many text pieces as the fullest band: group
  headers, centred counts, section labels) may cross a gap that at least half of all bands
  leave clear; they become spanning cells.
- **Rows**: text bands (lines overlapping vertically). When interior horizontal rules
  separate the bands densely the table's rows are ruled: rows are the bands between rules
  (several lines in one row are one multi-line cell). Otherwise every band is a row, except
  a band that continues the cells above it: no text in the first column, close below, and
  text only in columns already filled above (a wrapped cell).
- **Spans**: a text atom crossing a column boundary spans those columns; in ruled tables a
  rule segment missing inside one row (or column) where the rule exists elsewhere merges
  the two cells it would separate. Merged areas are made rectangular. A section row (a row
  whose only text is one continuous line crossing a column boundary) spans the whole row,
  except across a rule that parts the row.
- **Header rows**: rows covered by a header fill, rows above the first interior rule of an
  unboxed table, or top rows in a style the body does not use (or spanning group headers);
  none without evidence.
- **Group headers**: a cell of an upper header row spans the empty positions of the
  sub-columns it groups (columns with a header below): rightward up to the midpoint to the
  next group header, leftward as far as its text centre makes symmetric (or to the midpoint
  to the previous one), never into a stub column.
- **Cell roles**: cells of the header rows are column headers; a body row made of one cell
  spanning every column is a section row; the first column holds row headers (a stub) when
  its body cells are text beside mostly numeric data, or when the header rows leave the
  head of that column empty above text. Other cells are data.

All distances are in font units of the table's text. No coordinate, font or book is named.
"""

from collections import Counter
from dataclasses import dataclass, field
from statistics import median

from book_core.layout.evidence import NUMERIC_CELL
from book_core.layout.frames import to_frame
from book_core.tables.rulings import in_frame, merged

WORD_GAP = 0.8  # font sizes: narrower gaps are word spaces
CROSS_SHARE = 0.15  # bands allowed to cross a text gap (spanning rows)
RULE_COVER = 0.6  # a separator rule covers this share of the table's other extent
DENSE_RULES = 0.5  # interior rules per band gap above which rows are ruled
BOXED_RULES = 1  # interior rules that make a boxed grid's rows ruled (a lattice)
CONTINUE_GAP = 0.6  # line heights: a wrapped cell's next line is this close
SEGMENT_COVER = 0.5  # share of a row (column) a rule segment must cover to separate it
EDGE = 0.5  # font sizes: rules this close to the table edge are borders
SPARSE_SHARE = 0.5  # bands with at most this share of the fullest band's text pieces
CLEAR_SHARE = 0.5  # ... may cross a gap that this share of all bands leaves clear
SPARSE_BANDS = 4  # bands needed before sparse bands may cross gaps
STUB_NUMERIC = 0.6  # share of numeric data cells beside a text first column (a stub)


@dataclass
class Atom:
    span_id: str
    line_id: str
    box: object  # frame BBox
    text: str
    bold: bool
    italic: bool
    font: str
    size: float
    start: int | None = None  # character range of the span (None: the whole span)
    end: int | None = None


@dataclass
class Cell:
    row: int
    column: int
    row_span: int = 1
    column_span: int = 1
    atoms: list[Atom] = field(default_factory=list)
    header: bool = False
    role: str = "data"  # column_header, row_header, section or data


@dataclass
class GridDraft:
    rows: list[tuple[float, float]]
    columns: list[tuple[float, float]]
    cells: list[Cell]
    header_rows: int
    method: str
    evidence: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


def _bands(boxes, overlap=0.5):
    """Indexes grouped into vertical bands (boxes overlapping by half the smaller height)."""
    order = sorted(range(len(boxes)), key=lambda i: (boxes[i].y0 + boxes[i].y1) / 2)
    bands = []
    for i in order:
        b = boxes[i]
        if bands:
            top, bottom, members = bands[-1]
            common = min(bottom, b.y1) - max(top, b.y0)
            if common >= overlap * min(bottom - top, b.y1 - b.y0):
                bands[-1] = (min(top, b.y0), max(bottom, b.y1), members + [i])
                continue
        bands.append((b.y0, b.y1, [i]))
    return bands


def _clusters(values, tolerance):
    out = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tolerance:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(c) / len(c) for c in out]


def atoms_of(evidence, lines, rotation):
    atoms = []
    for line in lines:
        for sid in line.span_ids:
            span = evidence.spans[sid]
            if not span.text.strip():
                continue
            atoms.append(
                Atom(
                    span_id=sid,
                    line_id=line.id,
                    box=to_frame(span.bbox, rotation) if rotation else span.bbox,
                    text=span.text,
                    bold=span.bold,
                    italic=span.italic,
                    font=span.font,
                    size=span.size,
                )
            )
    return atoms


def _pieces(members, atoms, gap):
    """Text pieces of a band: its atoms merged where they are closer than ``gap``."""
    boxes = sorted((atoms[i].box.x0, atoms[i].box.x1) for i in members)
    count, right = 0, None
    for x0, x1 in boxes:
        if right is None or x0 - right > gap:
            count += 1
            right = x1
        else:
            right = max(right, x1)
    return count


def columns_from_text(atoms, x0, x1, font, allowed_share=CROSS_SHARE, min_gap=WORD_GAP):
    """Column separators (frame x) from gaps no text crosses in nearly every band."""
    if not atoms:
        return [], 0
    bands = _bands([a.box for a in atoms])
    if len(bands) < 2:
        return [], len(bands)
    step = 0.5
    size = int((x1 - x0) / step) + 2
    # Sparse bands (group headers, centred counts, section labels) may cross a gap the full
    # bands show; only when spanning cells are allowed at all and the table has some rows.
    pieces = [_pieces(members, atoms, min_gap * font) for _, _, members in bands]
    full = max(pieces)
    sparse = [
        bool(allowed_share) and len(bands) >= SPARSE_BANDS and n <= SPARSE_SHARE * full
        for n in pieces
    ]
    coverage = [0] * size  # dense bands covering each position
    everyone = [0] * size  # all bands
    for (_, _, members), thin in zip(bands, sparse, strict=True):
        covered = [False] * size
        for i in members:
            box = atoms[i].box
            a = max(0, int((box.x0 - x0) / step))
            b = min(size - 1, int((box.x1 - x0) / step) + 1)
            for k in range(a, b):
                covered[k] = True
        for k in range(size):
            if covered[k]:
                everyone[k] += 1
                coverage[k] += not thin
    dense = len(bands) - sum(sparse)
    allowed = int(allowed_share * dense)
    if allowed_share and dense >= 4:
        allowed = max(1, allowed)  # one spanning row (a title, a section) may cross
    clear = CLEAR_SHARE * len(bands)
    # Gaps strictly inside the text: between the leftmost and rightmost covered positions.
    first = next((k for k in range(size) if everyone[k]), 0)
    last = max((k for k in range(size) if everyone[k]), default=size - 1)
    gaps, start = [], None
    for k in range(first, last + 1):
        open_gap = coverage[k] <= allowed and (not any(sparse) or len(bands) - everyone[k] >= clear)
        if open_gap:
            start = k if start is None else start
        elif start is not None:
            gaps.append((start, k))
            start = None
    separators = []
    for a, b in gaps:
        if (b - a) * step >= min_gap * font:
            # A gap crossed by some bands keeps the position the fewest bands cross.
            low = min(everyone[a:b])
            ks = [k for k in range(a, b) if everyone[k] == low]
            separators.append(x0 + (ks[0] + ks[-1]) / 2 * step)
    return separators, len(bands)


def _marker(atom, evidence):
    """A list marker: a short non-word atom opening a list-item line."""
    line = evidence.line(atom.line_id)
    text = atom.text.strip()
    return (
        line.unit_kind in {"list_item", "list_item_candidate"}
        and len(text) <= 2
        and line.span_ids
        and line.span_ids[0] == atom.span_id
        and not any(ch.isdigit() for ch in text)
    )


def _without_marker_columns(atoms, separators, left, right, evidence):
    """Drop separators that only set list markers apart from their text: a column holding
    nothing but markers belongs to the column it marks."""
    edges = [left, *separators, right]
    keep = []
    for k, x in enumerate(separators):
        inside = [a for a in atoms if edges[k] <= (a.box.x0 + a.box.x1) / 2 < x]
        if inside and all(_marker(a, evidence) for a in inside):
            continue
        keep.append(x)
    return keep


def _section_lines(atoms, separators, font):
    """Lines that alone fill their band with one continuous run of text crossing a column
    separator (a section or title row): their text is not split between columns."""
    by_line = {}
    for atom in atoms:
        by_line.setdefault(atom.line_id, []).append(atom)
    boxes = {}
    for lid, found in by_line.items():
        boxes[lid] = type(found[0].box)(
            x0=min(a.box.x0 for a in found), y0=min(a.box.y0 for a in found),
            x1=max(a.box.x1 for a in found), y1=max(a.box.y1 for a in found),
        )  # fmt: skip
    ids = list(boxes)
    sections = set()
    for _, _, members in _bands([boxes[i] for i in ids]):
        if len(members) != 1:
            continue
        lid = ids[members[0]]
        found = sorted(by_line[lid], key=lambda a: a.box.x0)
        continuous = all(
            b.box.x0 - a.box.x1 <= WORD_GAP * font for a, b in zip(found, found[1:], strict=False)
        )
        box = boxes[lid]
        if continuous and any(box.x0 < x < box.x1 for x in separators):
            sections.add(lid)
    return sections


def _split_atoms(atoms, separators, font, keep=frozenset()):
    """Atoms crossing a column separator split at the whitespace nearest to it (character
    positions estimated by an even share of the span's width); others, and atoms of the
    lines in ``keep``, unchanged."""
    out, count = [], 0
    for atom in atoms:
        if atom.line_id in keep:
            out.append(atom)
            continue
        pieces = [atom]
        for x in separators:
            piece = next((a for a in pieces if a.box.x0 < x < a.box.x1), None)
            if piece is None:
                continue
            first = piece.start or 0
            text = piece.text
            width = (piece.box.x1 - piece.box.x0) / max(1, len(text))
            best = None
            for k, ch in enumerate(text):
                if not ch.isspace():
                    continue
                at = piece.box.x0 + (k + 0.5) * width
                if abs(at - x) <= font and (best is None or abs(at - x) < abs(best[1] - x)):
                    best = (k, at)
            if best is None:
                continue
            k = best[0]
            left_text, right_text = text[: k + 1], text[k + 1 :]
            if not left_text.strip() or not right_text.strip():
                continue
            box = piece.box
            cut = box.x0 + k * width
            left = Atom(
                piece.span_id,
                piece.line_id,
                type(box)(x0=box.x0, y0=box.y0, x1=cut, y1=box.y1),
                left_text,
                piece.bold,
                piece.italic,
                piece.font,
                piece.size,
                first,
                first + k + 1,
            )
            right = Atom(piece.span_id, piece.line_id,
                         type(box)(x0=cut + width, y0=box.y0, x1=box.x1, y1=box.y1), right_text,
                         piece.bold, piece.italic, piece.font, piece.size, first + k + 1,
                         first + len(text))  # fmt: skip
            pieces[pieces.index(piece) : pieces.index(piece) + 1] = [left, right]
            count += 1
        out += pieces
    return out, count


def _numeric(text):
    return bool(NUMERIC_CELL.match(text.strip())) and any(ch.isdigit() for ch in text)


def structure(evidence, box, rotation, lines, rules, fills):
    """GridDraft of one table region (page ``box``) read in frame ``rotation``."""
    frame_box = to_frame(box, rotation) if rotation else box
    atoms = atoms_of(evidence, lines, rotation)
    font = median([a.size for a in atoms if a.size > 0] or [evidence.font])
    frules, ffills = in_frame(rules, fills, rotation)
    frules = [r for r in merged(frules, 0.3 * font) if not r.light]
    width = frame_box.x1 - frame_box.x0
    height = frame_box.y1 - frame_box.y0
    flags = []

    # Columns.
    verticals = [
        r
        for r in frules
        if r.axis == "v"
        and frame_box.x0 + EDGE * font < r.at < frame_box.x1 - EDGE * font
        and r.length >= 0.3 * height
    ]
    v_positions = _clusters([r.at for r in verticals], 0.3 * font)
    text_x0 = min((a.box.x0 for a in atoms), default=frame_box.x0)
    text_x1 = max((a.box.x1 for a in atoms), default=frame_box.x1)
    left, right = min(frame_box.x0, text_x0), max(frame_box.x1, text_x1)
    if v_positions:
        strong, _ = columns_from_text(atoms, left, right, font, allowed_share=0.0, min_gap=2.0)
        edges = [left, *v_positions, right]

        def splits_text(x):
            # A gap inside a ruled column separates columns only with text on both sides.
            lo = max(e for e in edges if e <= x)
            hi = min(e for e in edges if e >= x)
            before = {a.line_id for a in atoms if lo <= a.box.x0 and a.box.x1 <= x}
            after = {a.line_id for a in atoms if x <= a.box.x0 and a.box.x1 <= hi}
            return len(before) >= 2 and len(after) >= 2

        separators = sorted(
            v_positions
            + [
                s
                for s in strong
                if all(abs(s - v) > 1.5 * font for v in v_positions) and splits_text(s)
            ]
        )
        method = "rules"
    else:
        separators, _ = columns_from_text(atoms, left, right, font)
        method = "text"
    separators = _without_marker_columns(atoms, separators, left, right, evidence)
    col_edges = [left, *separators, right]
    columns = list(zip(col_edges, col_edges[1:], strict=False))
    sections = _section_lines(atoms, separators, font)
    atoms, split = _split_atoms(atoms, separators, font, sections)
    if split:
        flags.append(f"{split} span(s) split at a column boundary (estimated character positions)")

    # Rows.
    line_boxes = {}
    for a in atoms:
        b = line_boxes.get(a.line_id)
        line_boxes[a.line_id] = a.box if b is None else type(b)(
            x0=min(b.x0, a.box.x0), y0=min(b.y0, a.box.y0),
            x1=max(b.x1, a.box.x1), y1=max(b.y1, a.box.y1))  # fmt: skip
    line_ids = list(line_boxes)
    bands = _bands([line_boxes[i] for i in line_ids])
    bands = [(top, bottom, [line_ids[i] for i in members]) for top, bottom, members in bands]
    horizontals = [
        r
        for r in frules
        if r.axis == "h"
        and frame_box.y0 + EDGE * font < r.at < frame_box.y1 - EDGE * font
        and r.length >= 0.3 * width
    ]
    h_positions = _clusters([r.at for r in horizontals], 0.3 * font)
    # Rules that fall between two bands (no band crosses them).
    between = [
        y
        for y in h_positions
        if not any(top + 0.2 * font < y < bottom - 0.2 * font for top, bottom, _ in bands)
    ]
    # Rows are ruled when rules part the bands densely, or when a boxed grid (vertical
    # rules) parts its body by full rules: its bands between rules are multi-line cells.
    ruled = len(bands) > 1 and (
        len(between) >= DENSE_RULES * (len(bands) - 1)
        or (bool(v_positions) and len(between) >= BOXED_RULES)
    )
    pitch = median([b - t for t, b, _ in bands]) if bands else font

    def column_of(x):
        for index, (c0, c1) in enumerate(columns):
            if c0 <= x <= c1:
                return index
        return 0 if x < columns[0][0] else len(columns) - 1

    def occupied(band):
        found = set()
        for a in atoms:
            if a.line_id in band[2]:
                found.add(column_of((a.box.x0 + a.box.x1) / 2))
        return found

    groups = []  # lists of band indexes forming one row
    for index, band in enumerate(bands):
        if not groups:
            groups.append([index])
            continue
        previous = bands[groups[-1][-1]]
        rule_between = any(previous[1] - 0.2 * font <= y <= band[0] + 0.2 * font for y in between)
        if ruled:
            same = not rule_between
        else:
            above = set().union(*(occupied(bands[i]) for i in groups[-1]))
            here = occupied(band)
            close = band[0] - previous[1] <= CONTINUE_GAP * pitch
            same = (
                not rule_between
                and close
                and len(columns) > 1
                and 0 not in here
                and here <= above
                and len(here) < len(columns)
            )
        if same:
            groups[-1].append(index)
        else:
            groups.append([index])
    row_edges = []
    for group in groups:
        top = min(bands[i][0] for i in group)
        bottom = max(bands[i][1] for i in group)
        row_edges.append((top, bottom))
    rows = []
    for k, (top, bottom) in enumerate(row_edges):
        start = frame_box.y0 if k == 0 else (row_edges[k - 1][1] + top) / 2
        end = frame_box.y1 if k == len(row_edges) - 1 else (bottom + row_edges[k + 1][0]) / 2
        if ruled:
            # Snap to the rules between rows.
            near = (
                [y for y in between if row_edges[k - 1][1] - font <= y <= top + font] if k else []
            )
            start = near[0] if near else start
        rows.append((min(start, top), max(end, bottom)))
    for k in range(1, len(rows)):  # rows meet without overlap
        middle = (rows[k - 1][1] + rows[k][0]) / 2 if rows[k - 1][1] > rows[k][0] else None
        if middle is not None:
            rows[k - 1] = (rows[k - 1][0], middle)
            rows[k] = (middle, rows[k][1])
    band_row = {}
    for k, group in enumerate(groups):
        for i in group:
            for lid in bands[i][2]:
                band_row[lid] = k

    # Cells and spans.
    grid = {}
    for a in atoms:
        r = band_row[a.line_id]
        c0 = column_of(a.box.x0 + 0.25 * font)
        c1 = column_of(a.box.x1 - 0.25 * font)
        centre = column_of((a.box.x0 + a.box.x1) / 2)
        grid.setdefault((r, centre), []).append(a)
        if c1 > c0:  # text crossing a column boundary spans those columns
            grid.setdefault(("span", r, c0, c1), [])
    parent = {(r, c): (r, c) for r in range(len(rows)) for c in range(len(columns))}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    def covered(position, axis, lo, hi):
        span = hi - lo
        for rule in frules:
            if rule.axis != axis or abs(rule.at - position) > 0.4 * font:
                continue
            if min(rule.end, hi) - max(rule.start, lo) >= SEGMENT_COVER * span:
                return True
        return False

    def ruled_at(c, r):
        """A rule parts columns c and c + 1 in row r."""
        x = separators[c]
        return any(abs(x - v) <= 0.3 * font for v in v_positions) and covered(x, "v", *rows[r])

    for key in list(grid):
        if key[0] == "span":
            _, r, c0, c1 = key
            for c in range(c0, c1):
                join((r, c), (r, c + 1))
    # A section row: its only text is a section line; it spans the row up to a parting rule.
    row_lines = {}
    for a in atoms:
        row_lines.setdefault(band_row[a.line_id], set()).add(a.line_id)
    section_rows = sorted(r for r, found in row_lines.items() if found and found <= sections)
    for r in section_rows:
        for c in range(len(columns) - 1):
            if not ruled_at(c, r):
                join((r, c), (r, c + 1))
    if section_rows:
        flags.append(f"{len(section_rows)} section row(s) span the table")
    if verticals or horizontals:
        # Rule segments missing inside a row (or column) merge the cells they would part.
        for c, x in enumerate(separators[:], start=0):
            if not any(abs(x - v) <= 0.3 * font for v in v_positions):
                continue  # a text gap, not a rule: no segment test
            for r, (top, bottom) in enumerate(rows):
                if not covered(x, "v", top, bottom):
                    join((r, c), (r, c + 1))
        if ruled:
            for r in range(len(rows) - 1):
                y = rows[r][1]
                for c, (left_x, right_x) in enumerate(columns):
                    if not covered(y, "h", left_x, right_x):
                        has_text_below = (r + 1, c) in grid
                        has_text_above = (r, c) in grid
                        if not (has_text_below and has_text_above):
                            join((r, c), (r + 1, c))
    groups_of = {}
    for key in parent:
        groups_of.setdefault(find(key), []).append(key)
    cells, taken = [], set()
    for root in sorted(groups_of):
        members = groups_of[root]
        r0 = min(r for r, _ in members)
        r1 = max(r for r, _ in members)
        c0 = min(c for _, c in members)
        c1 = max(c for _, c in members)
        block = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)} - taken
        if not block:
            continue
        taken |= block
        rows_in = sorted({r for r, _ in block})
        cols_in = sorted({c for _, c in block})
        rectangle = len(block) == len(rows_in) * len(cols_in) and (
            rows_in[-1] - rows_in[0] + 1 == len(rows_in)
            and cols_in[-1] - cols_in[0] + 1 == len(cols_in)
        )
        if rectangle:
            parts = [(rows_in[0], cols_in[0], len(rows_in), len(cols_in), sorted(block))]
        else:
            # A merged area cut by another one is not a rectangle: its positions stay
            # single cells (every grid position belongs to exactly one cell).
            flags.append("overlapping merged areas kept as single cells")
            parts = [(r, c, 1, 1, [(r, c)]) for r, c in sorted(block)]
        for r, c, rs, cs, keys in parts:
            cell = Cell(r, c, rs, cs)
            for key in keys:
                cell.atoms += grid.get(key, [])
            cells.append(cell)
    cells.sort(key=lambda c: (c.row, c.column))

    wide = [
        (y, any(abs(r.at - y) <= 0.3 * font and r.length >= 0.9 * width for r in horizontals))
        for y in between
    ]
    header_rows, header_evidence = _header_rows(cells, rows, columns, ffills, wide, ruled,
                                                bands, groups, font)  # fmt: skip
    for cell in cells:
        cell.header = cell.row < header_rows
    stub = _roles(cells, header_rows, len(columns))
    cells, grouped = _group_headers(cells, header_rows, columns, 1 if stub else 0)
    if grouped:
        flags.append(f"{grouped} group header(s) widened over their sub-columns")
    return GridDraft(
        rows=rows,
        columns=columns,
        cells=cells,
        header_rows=header_rows,
        method=method + ("+ruled_rows" if ruled else "+text_rows"),
        evidence={
            "vertical_rules": len(v_positions),
            "horizontal_rules_between_rows": len(between),
            "text_bands": len(bands),
            "header": header_evidence,
            "stub": stub,
        },
        flags=flags,
    )


def _group_headers(cells, header_rows, columns, stub):
    """(cells with upper header cells widened over their sub-columns, count widened)."""
    if header_rows < 2:
        return cells, 0
    at = {}
    for cell in cells:
        for r in range(cell.row, cell.row + cell.row_span):
            for c in range(cell.column, cell.column + cell.column_span):
                at[(r, c)] = cell
    middle = [(c0 + c1) / 2 for c0, c1 in columns]
    widened, gone = 0, set()
    for row in range(header_rows - 1):
        heads = sorted(
            (c for c in cells if c.row == row and c.row_span == 1 and c.atoms),
            key=lambda c: c.column,
        )
        centres = [
            (min(a.box.x0 for a in h.atoms) + max(a.box.x1 for a in h.atoms)) / 2 for h in heads
        ]

        def free(c, row=row):
            # An empty position of this row over a column with a header below it.
            cell = at.get((row, c))
            below = any(
                at.get((r, c)) is not None and at[(r, c)].atoms and at[(r, c)].row > row
                for r in range(row + 1, header_rows)
            )
            return (
                c >= stub and cell is not None and not cell.atoms and cell.row_span == 1
                and cell.column_span == 1 and id(cell) not in gone and below
            )  # fmt: skip

        for k, head in enumerate(heads):
            right_limit = (centres[k] + centres[k + 1]) / 2 if k + 1 < len(heads) else None
            first, last = head.column, head.column + head.column_span - 1
            while (
                last + 1 < len(columns)
                and free(last + 1)
                and (right_limit is None or middle[last + 1] < right_limit)
            ):
                last += 1
            reach = columns[last][1] - centres[k]
            left_limit = (centres[k - 1] + centres[k]) / 2 if k else centres[k] - reach
            while first - 1 >= 0 and free(first - 1) and middle[first - 1] > left_limit:
                first -= 1
            if (first, last) == (head.column, head.column + head.column_span - 1):
                continue
            for c in range(first, last + 1):
                other = at.get((row, c))
                if other is not head:
                    gone.add(id(other))
                    at[(row, c)] = head
            head.column, head.column_span = first, last - first + 1
            widened += 1
    kept = sorted((c for c in cells if id(c) not in gone), key=lambda c: (c.row, c.column))
    return kept, widened


def _text(cell):
    return " ".join(a.text.strip() for a in cell.atoms).strip()


def _roles(cells, header_rows, columns):
    """Cell roles (see the module); returns the stub evidence or None."""
    for cell in cells:
        if cell.header:
            cell.role = "column_header"
        elif cell.column_span == columns and columns > 1 and _text(cell):
            cell.role = "section"
    body = [c for c in cells if not c.header and c.role != "section"]
    first = [c for c in body if c.column == 0 and c.column_span == 1 and _text(c)]
    rest = [c for c in body if c.column > 0 and _text(c)]
    if columns < 2 or len(first) < 2 or not rest:
        return None
    reason = None
    if not any(_numeric(_text(c)) for c in first) and (
        sum(_numeric(_text(c)) for c in rest) >= STUB_NUMERIC * len(rest)
    ):
        reason = "text first column beside numeric data"
    else:
        heads = [c for c in cells if c.header and c.column == 0]
        others = [c for c in cells if c.header and c.column > 0 and _text(c)]
        rows = {c.row for c in body}
        if (
            header_rows
            and others
            and not any(_text(c) for c in heads)
            and (len(first) >= 0.5 * len(rows))
        ):
            reason = "empty head above a text first column"
    if reason is not None:
        for cell in first:
            cell.role = "row_header"
    return reason


def _style(atoms):
    weight = Counter()
    for a in atoms:
        weight[(a.bold, a.italic, a.font, round(a.size))] += len(a.text.strip())
    return weight.most_common(1)[0][0] if weight else None


def _header_rows(cells, rows, columns, fills, between, ruled, bands, groups, font):
    if len(rows) < 2:
        return 0, "single row"
    by_row = {}
    for cell in cells:
        by_row.setdefault(cell.row, []).append(cell)
    limit = min(3, len(rows) - 1)

    # 1. A fill behind the top rows that the body rows do not share.
    def fill_of(r):
        top, bottom = rows[r]
        middle = (top + bottom) / 2
        found = [f for f in fills if f.bbox.y0 - 0.5 <= middle <= f.bbox.y1 + 0.5
                 and f.bbox.x1 - f.bbox.x0 >= 0.5 * (columns[-1][1] - columns[0][0])]  # fmt: skip
        return found[0].color if found else None

    colours = [fill_of(r) for r in range(len(rows))]
    if colours[0] is not None:
        k = 0
        while k < limit and colours[k] == colours[0]:
            k += 1
        body = colours[k:]
        if k < len(rows) and colours[0] not in body:
            return k, "header fill"
    # 2. Unboxed table: the first full-width rule between rows within the top rows (partial
    # rules under group headings are inside the header).
    if not ruled and between:
        full = [y for y, wide in between if wide] or [y for y, _ in between]
        tops = [rows[r][1] for r in range(limit)]
        for r, bottom in enumerate(tops):
            following = rows[r + 1][0] if r + 1 < len(rows) else bottom
            if any(bottom - 0.6 * font <= y <= following + 0.6 * font for y in full):
                return r + 1, "rule below the header rows"
    # 3. Style: top rows in a style the body rows do not use; group headers that span.
    body_atoms = [a for c in cells if c.row >= limit for a in c.atoms]
    body_style = _style(body_atoms)
    k = 0
    while k < limit:
        atoms = [a for c in by_row.get(k, []) for a in c.atoms]
        style = _style(atoms)
        if style is None or style == body_style:
            break
        k += 1
    if k:
        numeric_body = sum(_numeric(a.text) for a in body_atoms) >= 0.3 * max(1, len(body_atoms))
        if numeric_body or any(c.column_span > 1 for r in range(k) for c in by_row.get(r, [])):
            return k, "top rows in a style the body does not use"
        if k <= 2:
            return k, "top rows in a style the body does not use"
    return 0, "no header evidence"
