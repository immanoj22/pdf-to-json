"""Table gold from reference XML: tables, grids with spans, header rows, titles and notes.

The vocabulary (element and attribute names) is evaluation data in
``reference_dialects/table_dialects.json``; this module holds none. A reference table becomes
a grid: rows in document order (several groups stack), cells placed in the first free
column unless the cell names its column, spans from the span attributes or a start/end
column name pair. Leading head rows, and leading rows made only of header cells, are header
rows. Foot rows are notes when the vocabulary says so.

Each cell, title and note is located on the PDF through reference tokens already aligned
to retained PDF tokens ``[page, ordinal]``: for books 1-4 the derived gold units (a unit's
table cell path), for the math book the reference alignment of its token stream. Nothing is
copied from the PDF; the gold stays ``human_approved: false``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PROFILE = Path(__file__).resolve().parents[3] / "reference_dialects" / "table_dialects.json"
TABLE_GOLD_VERSION = "table-gold-1"


def profile_data(path: Path = PROFILE) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def vocabulary(dialect: str, data: dict | None = None) -> dict:
    data = data or profile_data()
    return {**data["common"], **data["dialects"].get(dialect, {})}


@dataclass
class Node:
    name: str
    path: str
    attributes: dict[str, str]
    children: list[Node] = field(default_factory=list)
    parent: Node | None = None

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def xml_tree(root) -> Node:
    """Nodes of an ElementTree with the reference reader's paths (``/name[n]`` per name)."""

    def build(element, path, parent):
        node = Node(
            _local(element.tag),
            path,
            {_local(k): v for k, v in element.attrib.items()},
            parent=parent,
        )
        counts: dict[str, int] = {}
        for child in element:
            if not isinstance(child.tag, str):
                continue
            name = _local(child.tag)
            counts[name] = counts.get(name, 0) + 1
            node.children.append(build(child, f"{path}/{name}[{counts[name]}]", node))
        return node

    return build(root, f"/{_local(root.tag)}[1]", None)


def element_tree(elements) -> Node:
    """Nodes of a reader's element tuple (index, name, path, parent, attributes)."""
    nodes = [Node(e.name, e.path, dict(e.attributes)) for e in elements]
    root = None
    for element, node in zip(elements, nodes, strict=True):
        if element.parent is None:
            root = root or node
        else:
            node.parent = nodes[element.parent]
            nodes[element.parent].children.append(node)
    return root


@dataclass
class GoldCell:
    row: int
    column: int
    row_span: int
    column_span: int
    header: bool
    part: str  # head / body
    path: str
    tokens: list[list[int]] = field(default_factory=list)
    reference_tokens: int = 0  # reference tokens of the cell (aligned or not)
    math: int = 0  # equation slots inside the cell (the math book)


@dataclass
class GoldTable:
    index: int
    path: str
    rows: int
    columns: int
    header_rows: int
    cells: list[GoldCell]
    title_paths: list[str]
    note_paths: list[str]
    nested: bool = False
    title_tokens: list[list[int]] = field(default_factory=list)
    note_tokens: list[list[int]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _inside(node: Node, names, stop: Node) -> bool:
    parent = node.parent
    while parent is not None and parent is not stop:
        if parent.name in names:
            return True
        parent = parent.parent
    return False


def _part(node: Node, vocab, stop: Node) -> str:
    parent = node.parent
    while parent is not None and parent is not stop:
        if parent.name in vocab["head"]:
            return "head"
        if parent.name in vocab["foot"]:
            return "foot"
        parent = parent.parent
    return "body"


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _grid(table: Node, vocab) -> tuple[list[GoldCell], list[str], int, list[str]]:
    """Cells of one table (several groups stack), note paths of foot rows, columns, problems."""
    containers = set(vocab["containers"])
    cell_names = set(vocab["cells"])
    groups = [c for c in table.children if c.name in vocab["groups"]] or [table]
    cells, notes, problems = [], [], []
    offset, width = 0, 0
    for group in groups:
        names = {}
        specs = [c for c in group.children if c.name in vocab["column_specs"]]
        for position, spec in enumerate(specs, start=1):
            number = _int(spec.attributes.get(vocab["column_spec_number"]), position)
            name = spec.attributes.get(vocab["column_spec_name"])
            if name is not None:
                names[name] = number - 1
        declared = _int(group.attributes.get(vocab["column_count"]), 0)
        rows = [
            n
            for n in group.descendants()
            if n.name in vocab["rows"]
            and not _inside(n, containers, table)
            and not _inside(n, cell_names, table)
        ]
        occupied: set[tuple[int, int]] = set()
        index = 0
        for row in rows:
            part = _part(row, vocab, table)
            if part == "foot" and vocab.get("foot_rows_are_notes"):
                notes.append(row.path)
                continue
            column = 0
            for cell in (c for c in row.children if c.name in cell_names):
                attributes = cell.attributes
                start = None
                if vocab["span_start_name"] in attributes:
                    start = names.get(attributes[vocab["span_start_name"]])
                elif vocab["cell_column_name"] in attributes:
                    start = names.get(attributes[vocab["cell_column_name"]])
                if start is None:
                    while (index, column) in occupied:
                        column += 1
                    start = column
                span = _int(attributes.get(vocab["column_span"]), 1)
                if vocab["span_end_name"] in attributes:
                    end = names.get(attributes[vocab["span_end_name"]])
                    if end is not None and end >= start:
                        span = end - start + 1
                down = _int(attributes.get(vocab["row_span"]), 0) or (
                    _int(attributes.get(vocab["more_rows"]), 0) + 1
                )
                span, down = max(1, span), max(1, down)
                taken = [(index + r, start + c) for r in range(down) for c in range(span)]
                if any(t in occupied for t in taken):
                    problems.append(f"overlapping cell {cell.path}")
                occupied.update(taken)
                cells.append(
                    GoldCell(
                        row=offset + index,
                        column=start,
                        row_span=down,
                        column_span=span,
                        header=part == "head" or cell.name in vocab["header_cells"],
                        part=part,
                        path=cell.path,
                    )
                )
                column = start + span
            index += 1
        height = max([index] + [c.row - offset + c.row_span for c in cells if c.row >= offset])
        width = max(width, declared, *(c.column + c.column_span for c in cells))
        offset += height
    return cells, notes, width, problems


def read_tables(root: Node, vocab) -> list[GoldTable]:
    """Every reference table in document order, with its grid, titles and notes."""
    containers = set(vocab["containers"])
    tables = []
    for node in (n for n in [root, *root.descendants()] if n.name in containers):
        cells, foot_notes, columns, problems = _grid(node, vocab)
        rows = max((c.row + c.row_span for c in cells), default=0)
        by_row = defaultdict(list)
        for cell in cells:
            by_row[cell.row].append(cell)
        header_rows = 0
        for r in range(rows):
            if by_row[r] and all(c.header for c in by_row[r]):
                header_rows += 1
            else:
                break
        for cell in cells:  # a header cell spanning down extends the header block
            if cell.header and cell.row < header_rows:
                header_rows = max(header_rows, cell.row + cell.row_span)
        inner = {n.path for n in node.descendants() if n.name in set(vocab["cells"])}
        titles, notes = [], list(foot_notes)
        for child in node.descendants():
            if _inside(child, set(vocab["cells"]), node) or child.path in inner:
                continue
            if child.name in vocab["titles"] and not _inside(child, set(vocab["titles"]), node):
                titles.append(child.path)
            elif child.name in vocab["notes"] and not _inside(child, set(vocab["notes"]), node):
                notes.append(child.path)
        tables.append(
            GoldTable(
                index=len(tables),
                path=node.path,
                rows=rows,
                columns=columns,
                header_rows=header_rows,
                cells=cells,
                title_paths=titles,
                note_paths=notes,
                nested=_inside(node, containers, None),
                problems=problems,
            )
        )
    return tables


def _under(path: str, prefixes) -> str | None:
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None


def attach_units(tables: list[GoldTable], units) -> None:
    """Locate cells, titles and notes through derived-gold units (their ``pdf`` runs)."""
    cell_of = {c.path: c for t in tables for c in t.cells}
    titles = {p: t for t in tables for p in t.title_paths}
    notes = {p: t for t in tables for p in t.note_paths}
    for unit in units:
        tokens = [[page, o] for page, first, n in unit["pdf"] for o in range(first, first + n)]
        membership = unit.get("table") or {}
        cell = membership.get("cell")
        if cell in cell_of:
            cell_of[cell].reference_tokens += unit.get("xml_tokens", 0)
            cell_of[cell].tokens.extend(tokens)
        elif (title := _under(unit["path"], titles)) is not None:
            titles[title].title_tokens.extend(tokens)
        elif (note := _under(unit["path"], notes)) is not None:
            notes[note].note_tokens.extend(tokens)
        elif cell is not None and (note := _under(cell, notes)) is not None:
            notes[note].note_tokens.extend(tokens)


def attach_alignment(tables: list[GoldTable], document, alignment, slots=()) -> None:
    """Locate cells, titles and notes through a reference alignment (math book): each
    reference token's primary link ``(page index, ordinal)``; equation slots count per cell."""
    elements = document.elements
    targets = {}
    for t in tables:
        for c in t.cells:
            targets[c.path] = ("cell", c)
        for p in t.title_paths:
            targets[p] = ("title", t)
        for p in t.note_paths:
            targets[p] = ("note", t)
    owner_of = {}

    def owner(index):
        if index in owner_of:
            return owner_of[index]
        found, chain = None, index
        while chain is not None:
            if elements[chain].path in targets:
                found = targets[elements[chain].path]
                break
            chain = elements[chain].parent
        owner_of[index] = found
        return found

    for token in document.tokens:
        found = owner(token.element)
        if found is None:
            continue
        kind, target = found
        if kind == "cell":
            target.reference_tokens += 1
        page = alignment.xml_page[token.index]
        if page < 0:
            continue
        ref = [alignment.pages[page], alignment.xml_ordinal[token.index]]
        if kind == "cell":
            target.tokens.append(ref)
        elif kind == "title":
            target.title_tokens.append(ref)
        else:
            target.note_tokens.append(ref)
    cells = {c.path: c for t in tables for c in t.cells}
    for slot in slots:
        prefix = _under(slot.path, cells)
        if prefix is not None:
            cells[prefix].math += 1


STRAY_SHARE = 0.05  # a page holding fewer of a table's cell tokens is an alignment stray
STRAY_TOKENS = 2


def table_pages(counts: dict[int, int]) -> list[int]:
    """The run of consecutive pages around the page holding most cell tokens; other pages
    are kept only when they hold more than a stray share (alignment errors place single
    numbers or words of a cell far away)."""
    if not counts:
        return []
    total = sum(counts.values())
    main = max(sorted(counts), key=lambda p: counts[p])
    floor = max(STRAY_TOKENS, STRAY_SHARE * total)
    pages = [main]
    for step in (-1, 1):
        page = main + step
        while counts.get(page, 0) > floor or (counts.get(page, 0) and counts[page] >= 0.2 * total):
            pages.append(page)
            page += step
    return sorted(pages)


def _keep(refs, pages, margin=0):
    allowed = {p + d for p in pages for d in range(-margin, margin + 1)}
    kept = [r for r in refs if r[0] in allowed]
    return kept, len(refs) - len(kept)


def gold_rows(tables: list[GoldTable]) -> list[dict]:
    rows = []
    for t in tables:
        counts: dict[int, int] = defaultdict(int)
        for c in t.cells:
            for page, _ in c.tokens:
                counts[page] += 1
        pages_kept = table_pages(counts)
        stray = 0
        for c in t.cells:
            c.tokens, dropped = _keep(c.tokens, pages_kept)
            stray += dropped
        # A title may sit on the page before the table; notes on its last page or after.
        t.title_tokens, dropped_title = _keep(t.title_tokens, pages_kept, margin=1)
        t.note_tokens, dropped_notes = _keep(t.note_tokens, pages_kept, margin=1)
        stray += dropped_title + dropped_notes
        cell_tokens = [ref for c in t.cells for ref in c.tokens]
        pages = sorted({p for p, _ in cell_tokens + t.title_tokens + t.note_tokens})
        nonempty = [c for c in t.cells if c.tokens or c.math]
        rows.append(
            {
                "table": t.index,
                "path": t.path,
                "nested": t.nested,
                "rows": t.rows,
                "columns": t.columns,
                "header_rows": t.header_rows,
                "spanning_cells": sum(c.row_span > 1 or c.column_span > 1 for c in t.cells),
                "pages": pages,
                "located": bool(cell_tokens),
                "cells": [
                    {
                        "row": c.row,
                        "column": c.column,
                        "row_span": c.row_span,
                        "column_span": c.column_span,
                        "header": c.header,
                        "part": c.part,
                        "path": c.path,
                        "tokens": sorted(c.tokens),
                        "reference_tokens": c.reference_tokens,
                        "math": c.math,
                    }
                    for c in t.cells
                ],
                "title": {"paths": t.title_paths, "tokens": sorted(t.title_tokens)},
                "notes": {"paths": t.note_paths, "tokens": sorted(t.note_tokens)},
                "located_cells": sum(bool(c.tokens) for c in t.cells),
                "nonempty_cells": len(nonempty),
                "problems": t.problems,
                "stray_tokens": stray,
            }
        )
    return rows


def coverage(rows: list[dict]) -> dict:
    located = [r for r in rows if r["located"]]
    return {
        "tables": len(rows),
        "nested_tables": sum(r["nested"] for r in rows),
        "located_tables": len(located),
        "multi_page_tables": sum(len(r["pages"]) > 1 for r in located),
        "rows": sum(r["rows"] for r in rows),
        "cells": sum(len(r["cells"]) for r in rows),
        "cells_with_tokens": sum(r["located_cells"] for r in rows),
        "cells_with_math_only": sum(
            1 for r in rows for c in r["cells"] if c["math"] and not c["tokens"]
        ),
        "spanning_cells": sum(r["spanning_cells"] for r in rows),
        "tables_with_header_rows": sum(r["header_rows"] > 0 for r in rows),
        "tables_with_title": sum(bool(r["title"]["paths"]) for r in rows),
        "titles_located": sum(bool(r["title"]["tokens"]) for r in rows),
        "tables_with_notes": sum(bool(r["notes"]["paths"]) for r in rows),
        "notes_located": sum(bool(r["notes"]["tokens"]) for r in rows),
        "reference_cell_tokens": sum(c["reference_tokens"] for r in rows for c in r["cells"]),
        "aligned_cell_tokens": sum(len(c["tokens"]) for r in rows for c in r["cells"]),
        "fully_located_tables": sum(
            r["located"] and all(c["tokens"] for c in r["cells"] if c["reference_tokens"])
            for r in rows
        ),
        "tables_with_markup_problems": sum(bool(r["problems"]) for r in rows),
        "stray_tokens_dropped": sum(r["stray_tokens"] for r in rows),
    }
