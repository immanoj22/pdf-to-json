"""Table drafts become records: cells over line ids and span ranges, and their neighbours.

- A cell keeps the lists-stage units lying wholly inside it (list items, paragraphs) as
  its content structure (``unit_ids``).
- A line whose text lies in one cell is a whole line of that cell; a line whose spans fall
  in several cells is held through span ranges (a span split at a column boundary gives two
  ranges). Whitespace-only spans go with the span before them (or after, at a line start);
  a line without text goes to the cell around its centre. Every table line is held once.
- Display equation units inside a cell are read in that cell. A figure inside the table
  made only of the drawings that draw the table's rules and fills is a table piece (it is
  absorbed, not a figure); another figure inside a cell is read in that cell.
- A cell's content is listed in reading order (the lists-stage order of its lines; display
  equations and figures where they sit among them): whole units as paragraphs or list items,
  the other lines and span ranges as text.
- Header references: a cell is labelled by the column headers above it whose columns it
  shares (spanning group headers included), the row header of its row (when the table has a
  stub column) and the nearest section row above it.
- Figures overlapping a rejected graphic organizer are noted as organizer pieces.
- The table is read where its first line was read (``TableAnchor``).
- Continuation: the last table of a page and the first of the next page, in the same frame,
  near the content edges, with matching column proportions, are marked as one table
  continued (never joined here).
"""

from book_core.extraction.fingerprints import stable_id
from book_core.layout.frames import from_frame, to_frame
from book_core.model.common import BBox, Provenance, SpanRef
from book_core.tables.detect import area, covers, shared
from book_core.tables.models import (
    CellContent,
    Continuation,
    FigureNote,
    RejectedRegion,
    TableAnchor,
    TableCell,
    TableRecord,
)

REVIEW_CONFIDENCE = 0.75
POSSIBLE = "possible table, review: evidence too weak to take its text (lines stay in their units)"
EDGE_SHARE = 0.2  # share of the content height near the bottom / top edge for continuation
COLUMN_TOLERANCE = 0.06  # difference of column width shares that still match


def _box(frame_box, rotation):
    return from_frame(frame_box, rotation) if rotation else frame_box


def _anchor(line_ids, order):
    best = None
    for stream in order.streams:
        for position, lid in enumerate(stream.line_ids):
            if lid in line_ids:
                if best is None or (stream.kind == "main" and best[0].kind != "main"):
                    best = (stream, position)
                break
    if best is None:
        raise ValueError("Table lines are not in the page's reading order")
    stream, position = best
    return TableAnchor(
        stream_id=stream.id,
        after_line_id=stream.line_ids[position - 1] if position else None,
        position=position - 1,
    )


def _drawing_ids(ids, evidence):
    members = getattr(evidence, "members", {}) or {}
    out = set()
    for oid in ids:
        out |= set(members.get(oid, [])) or {oid}
    return out


LIST_KINDS = frozenset({"list_item", "list_item_candidate"})


def _positions(order):
    """{line id: (stream index, position)} of the page's reading order."""
    found = {}
    for k, stream in enumerate(order.streams):
        for i, lid in enumerate(stream.line_ids):
            found.setdefault(lid, (k, i))
    return found


def _content(whole, refs, units, equations, figures, evidence, positions, rotation):
    """CellContent items of one cell in reading order (see the module). ``units``: {unit id:
    its line ids} of the units lying wholly in the cell; ``equations`` and ``figures``:
    [(id, page box)]."""
    unit_of = {lid: u for u, lids in units.items() for lid in lids}
    line_of = {id(r): evidence.spans[r.span_id].line_id for r in refs}
    lines = set(whole) | set(line_of.values())
    ordered = sorted(lines, key=lambda lid: positions.get(lid, (len(positions), 0)))
    drafts = []  # [kind, unit id, line ids, span refs]
    for lid in ordered:
        unit = unit_of.get(lid)
        if unit is not None:
            if not (drafts and drafts[-1][1] == unit):
                kind = "list_item" if evidence.line(lid).unit_kind in LIST_KINDS else "paragraph"
                drafts.append([kind, unit, list(units[unit]), []])
            continue
        if not drafts or drafts[-1][0] != "text":
            drafts.append(["text", None, [], []])
        if lid in whole:
            drafts[-1][2].append(lid)
        drafts[-1][3] += [r for r in refs if line_of[id(r)] == lid]

    def centre(box):
        box = to_frame(box, rotation) if rotation else box
        return (box.y0 + box.y1) / 2

    boxes = {line.id: line.bbox for line in evidence.lines}
    items = []  # (frame centre, CellContent) in reading order
    for kind, unit, line_ids, span_refs in drafts:
        ids = line_ids or [line_of[id(r)] for r in span_refs]
        items.append((
            min(centre(boxes[i]) for i in ids),
            CellContent(kind=kind, unit_id=unit, line_ids=line_ids, span_refs=span_refs),
        ))  # fmt: skip
    # Equations and figures go after the last item that starts above their centre.
    extra = [(centre(box), CellContent(kind="equation", unit_id=uid)) for uid, box in equations]
    extra += [(centre(box), CellContent(kind="figure", figure_id=fid)) for fid, box in figures]
    for y, item in sorted(extra, key=lambda e: e[0]):
        index = max((k + 1 for k, (yy, _) in enumerate(items) if yy <= y), default=0)
        items.insert(index, (y, item))
    return [item for _, item in items]


def header_references(cells, header_rows, stub):
    """{cell index: [header cell indexes]}: column headers above sharing its columns (group
    headers first), the row header of its row, the nearest section row above it."""

    def columns(cell):
        return set(range(cell.column, cell.column + cell.column_span))

    def rows(cell):
        return set(range(cell.row, cell.row + cell.row_span))

    heads = [i for i, c in enumerate(cells) if c.role == "column_header" and not c.empty]
    sections = [i for i, c in enumerate(cells) if c.role == "section"]
    stubs = [i for i, c in enumerate(cells) if c.role == "row_header"] if stub else []
    out = {}
    for index, cell in enumerate(cells):
        found = [
            h for h in heads
            if h != index and cells[h].row < cell.row and columns(cells[h]) & columns(cell)
        ]  # fmt: skip
        found.sort(key=lambda h: (cells[h].row, cells[h].column))
        if cell.role in {"data", "row_header"}:
            if cell.role == "data":
                found += [h for h in stubs if rows(cells[h]) & rows(cell)
                          and cells[h].column < cell.column]  # fmt: skip
            above = [h for h in sections if cells[h].row < cell.row]
            if above:
                found.append(max(above, key=lambda h: cells[h].row))
        out[index] = found
    return out


def records(drafts, rejected, evidence, order, digest, number, label=None, version=None):
    """(tables, possible tables, rejected regions, figure notes) of one page. Only tables
    with strong evidence own their text; possible tables list the lines they would hold.
    ``label``: the page's printed label and its source (``furniture``)."""
    tables, possible, notes = [], [], []
    positions = _positions(order)
    page_label, label_source = label or (None, "none")
    unit_lines = {}
    for line in evidence.lines:
        if line.unit_id is not None:
            unit_lines.setdefault(line.unit_id, set()).add(line.id)
    for draft in drafts:
        line_ids = sorted({line.id for line in draft.lines})
        table_id = stable_id("table-record", digest, number, *line_ids)
        grid, rotation = draft.grid, int(draft.rotation) % 360
        frame_cells = []
        for cell in grid.cells:
            top = grid.rows[cell.row][0]
            bottom = grid.rows[cell.row + cell.row_span - 1][1]
            left = grid.columns[cell.column][0]
            right = grid.columns[cell.column + cell.column_span - 1][1]
            frame_cells.append(BBox(x0=left, y0=top, x1=right, y1=bottom))
        where = {}  # span id -> [(start, end, cell index)]
        for index, cell in enumerate(grid.cells):
            for atom in cell.atoms:
                where.setdefault(atom.span_id, []).append((atom.start, atom.end, index))
        whole = {i: [] for i in range(len(grid.cells))}
        refs = {i: [] for i in range(len(grid.cells))}
        for line in draft.lines:
            placed = [(sid, where.get(sid)) for sid in line.span_ids]
            cells = {i for _, found in placed if found for _, _, i in found}
            split = any(found and (len(found) > 1 or found[0][0] is not None)
                        for _, found in placed)  # fmt: skip
            if not cells:
                centre = to_frame(line.bbox, rotation) if rotation else line.bbox
                cx, cy = (centre.x0 + centre.x1) / 2, (centre.y0 + centre.y1) / 2
                index = min(
                    range(len(frame_cells)),
                    key=lambda i: (
                        not (frame_cells[i].x0 <= cx <= frame_cells[i].x1
                             and frame_cells[i].y0 <= cy <= frame_cells[i].y1),
                        abs((frame_cells[i].x0 + frame_cells[i].x1) / 2 - cx)
                        + abs((frame_cells[i].y0 + frame_cells[i].y1) / 2 - cy),
                    ),
                )  # fmt: skip
                whole[index].append(line.id)
            elif len(cells) == 1 and not split:
                whole[next(iter(cells))].append(line.id)
            else:
                previous = None
                pending = []
                for sid, found in placed:
                    if not found:
                        if previous is None:
                            pending.append(sid)
                        else:
                            refs[previous].append(SpanRef(span_id=sid))
                        continue
                    for start, end, index in sorted(found, key=lambda f: f[0] or 0):
                        for waiting in pending:
                            refs[index].append(SpanRef(span_id=waiting))
                        pending = []
                        if start is None:
                            refs[index].append(SpanRef(span_id=sid))
                        else:
                            refs[index].append(SpanRef(span_id=sid, start=start, end=end))
                        previous = index
        equations = {i: [] for i in range(len(grid.cells))}
        for row in evidence.equations:
            if row["unit_id"] is None or not draft.bbox.contains_center(row["bbox"]):
                continue
            box = to_frame(row["bbox"], rotation) if rotation else row["bbox"]
            for i, cb in enumerate(frame_cells):
                if cb.contains_center(box):
                    equations[i].append((row["unit_id"], row["bbox"]))
                    break
        drawing_ids = {r.object_id for r in draft.rules} | {f.object_id for f in draft.fills}
        absorbed, in_cells = [], {i: [] for i in range(len(grid.cells))}
        # A possible table owns nothing: no figure is absorbed or read in its cells.
        for figure in evidence.figures if draft.strong else []:
            fb = figure["bbox"]
            if not area(fb) or shared(fb, draft.bbox) < 0.9 * area(fb):
                continue
            objects = _drawing_ids(figure["object_ids"], evidence)
            kinds = {evidence.objects.get(o) for o in objects}
            if objects and kinds <= {"drawing"} and objects <= drawing_ids:
                absorbed.append(figure["id"])
                notes.append(
                    FigureNote(figure_id=figure["id"], kind="table_piece", table_id=table_id,
                               reasons=["only drawings that draw the table's rules and fills"])
                )  # fmt: skip
                continue
            box = to_frame(fb, rotation) if rotation else fb
            for i, cb in enumerate(frame_cells):
                if cb.contains_center(box):
                    in_cells[i].append((figure["id"], fb))
                    notes.append(
                        FigureNote(figure_id=figure["id"], kind="in_table_cell",
                                   table_id=table_id, reasons=["figure inside a table cell"])
                    )  # fmt: skip
                    break
        cells = []
        for i, cell in enumerate(grid.cells):
            inside = {
                u: sorted(unit_lines[u], key=lambda lid: positions.get(lid, (len(positions), 0)))
                for u in {evidence.line(lid).unit_id for lid in whole[i]} - {None}
                if unit_lines[u] <= set(whole[i])
            }
            cells.append(
                TableCell(
                    id=stable_id(table_id, "cell", cell.row, cell.column),
                    row=cell.row,
                    column=cell.column,
                    row_span=cell.row_span,
                    column_span=cell.column_span,
                    header=cell.header,
                    role=cell.role,
                    bbox=_box(frame_cells[i], rotation),
                    line_ids=whole[i],
                    unit_ids=sorted(inside),
                    span_refs=refs[i],
                    equation_unit_ids=[uid for uid, _ in equations[i]],
                    figure_ids=[fid for fid, _ in in_cells[i]],
                    content=_content(
                        whole[i],
                        refs[i],
                        inside,
                        equations[i],
                        in_cells[i],
                        evidence,
                        positions,
                        rotation,
                    ),
                )  # fmt: skip
            )
        stub = grid.evidence.get("stub")
        references = header_references(cells, grid.header_rows, stub)
        cells = [
            c.model_copy(update={"header_cell_ids": [cells[h].id for h in references[k]]})
            for k, c in enumerate(cells)
        ]
        flags = list(grid.flags)
        if not draft.strong:
            flags.insert(0, POSSIBLE)
        if draft.confidence < REVIEW_CONFIDENCE:
            flags.append("table evidence from two families only; review")
        if rotation:
            flags.append(f"rotated table read in its {rotation} degree frame")
        (tables if draft.strong else possible).append(
            TableRecord(
                id=table_id,
                owns_text=draft.strong,
                page=number,
                page_label=page_label,
                label_source=label_source,
                bbox=draft.bbox,
                rotation=rotation,
                rows=[tuple(r) for r in grid.rows],
                columns=[tuple(c) for c in grid.columns],
                header_rows=grid.header_rows,
                row_header_columns=1 if stub else 0,
                cells=cells,
                line_ids=[line.id for line in draft.lines],
                source_unit_ids=sorted({line.unit_id for line in draft.lines if line.unit_id}),
                structure_method=grid.method,
                evidence={k: round(v, 4) for k, v in sorted(draft.sources.items())},
                families=draft.families,
                structure_evidence={
                    k: v if not isinstance(v, dict) else str(v) for k, v in grid.evidence.items()
                },  # fmt: skip
                absorbed_figure_ids=absorbed,
                anchor=_anchor(set(line_ids), order),
                confidence=draft.confidence,
                reasons=draft.reasons,
                review_flags=flags,
                provenance=Provenance(
                    source_sha256=digest,
                    engine="book_core.tables",
                    engine_version=version,
                    method="derived",
                ),
            )  # fmt: skip
        )
    refused = []
    for item in rejected:
        figures = [f["id"] for f in evidence.figures if covers(f["bbox"], item.bbox, 0.5)]
        refused.append(
            RejectedRegion(
                bbox=item.bbox,
                kind=item.kind,
                evidence={k: round(v, 4) for k, v in sorted(item.sources.items())},
                reasons=item.reasons,
                figure_ids=figures,
            )
        )
        if item.kind == "graphic_organizer":
            for fid in figures:
                notes.append(
                    FigureNote(figure_id=fid, kind="graphic_organizer_piece",
                               reasons=["part of a graphic organizer, not a table or figure"])
                )  # fmt: skip
    return tables, possible, refused, notes


def _shares(table):
    width = table.columns[-1][1] - table.columns[0][0]
    return [(c1 - c0) / width for c0, c1 in table.columns] if width > 0 else []


def continuation(last, first, content_last, content_first):
    """(confidence, reasons) that ``first`` (next page) continues ``last``, or None."""
    if last.rotation != first.rotation or len(last.columns) != len(first.columns):
        return None
    a, b = _shares(last), _shares(first)
    if not a or any(abs(x - y) > COLUMN_TOLERANCE for x, y in zip(a, b, strict=True)):
        return None
    if last.rotation:
        return 0.6, ["same rotated frame and column proportions on consecutive pages"]
    near_bottom = last.bbox.y1 >= content_last.y1 - EDGE_SHARE * (content_last.y1 - content_last.y0)
    near_top = first.bbox.y0 <= content_first.y0 + EDGE_SHARE * (
        content_first.y1 - content_first.y0
    )
    if not (near_bottom and near_top):
        return None
    return 0.8, ["ends near the page bottom, the next begins near the top, same columns"]


def link(pages, contents):
    """({page: records with continuations marked}, count); records are frozen, so linked
    records are replaced by updated copies."""
    pages = {n: list(records) for n, records in pages.items()}
    count = 0
    for number in sorted(pages):
        if not pages.get(number) or not pages.get(number + 1):
            continue
        last = max(pages[number], key=lambda t: t.bbox.y1 if not t.rotation else t.bbox.x1)
        first = min(pages[number + 1], key=lambda t: t.bbox.y0 if not t.rotation else t.bbox.x0)
        found = continuation(last, first, contents[number], contents[number + 1])
        if found is None:
            continue
        confidence, reasons = found
        to = Continuation(table_id=first.id, page=number + 1, confidence=confidence,
                          reasons=reasons)  # fmt: skip
        back = Continuation(table_id=last.id, page=number, confidence=confidence, reasons=reasons)
        review = ["uncertain continuation from the previous page"] if confidence < 0.75 else []
        pages[number] = [
            t.model_copy(update={"continues_to": to}) if t.id == last.id else t
            for t in pages[number]
        ]
        pages[number + 1] = [
            t.model_copy(update={"continues_from": back,
                                 "review_flags": [*t.review_flags, *review]})
            if t.id == first.id else t
            for t in pages[number + 1]
        ]  # fmt: skip
        count += 1
    return pages, count
