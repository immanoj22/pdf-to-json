"""Glossary entry order: on a row-synchronised glossary page, read entry by entry.

A bilingual glossary sets each entry in rows across columns: the term and definition in one
language, a page reference, the same entry in the other language. Step 7 reads such rows line
by line, so the languages interleave. The human reference reads term then definition, entry
by entry, the first column's entry first, its page reference attached to it, then the next
column's entry (owner decision, docs/decisions.md, Step 11). This module reorders the lines
of a glossary block accordingly:

- **Columns**: lines grouped by horizontal overlap of their extents in the reading frame (an
  extent wider than most of the block never forms a column of its own).
- **Rows**: entry starts in the first column (a leading term, else a base-indent line) open
  rows; a line belongs to the last row opened at or above it.
- **Synchronised**: at least ``row_sync`` of the entry starts in the other columns share a
  baseline with a first-column entry start; otherwise the order is left as it is.
- New order: row by row, column by column in reading order, lines in block order inside a
  cell. Lines outside the block keep their positions; float anchors keep their lines.
"""

from __future__ import annotations

from statistics import median

from book_core.reading_order.models import (
    SEQUENCE_EDGES,
    OrderDecision,
    OrderEdge,
    PageReadingOrder,
)

ROW = 0.35  # font sizes: same baseline


def _columns(lines):
    """[[line, ...] per column] in reading order, by overlap of inline extents."""
    width = max(line.end for line in lines) - min(line.start for line in lines)
    spans = sorted(
        ((line.start, line.end, line) for line in lines if line.end - line.start < 0.6 * width),
        key=lambda item: item[0],
    )
    columns = []
    for start, end, line in spans:
        if columns and start < columns[-1]["end"] - 0.5 * line.size:
            columns[-1]["end"] = max(columns[-1]["end"], end)
            columns[-1]["lines"].append(line)
        else:
            columns.append({"start": start, "end": end, "lines": [line]})
    return columns


def entry_order(block, config):
    """(new line order, {line id: (row, column)}, evidence) or (None, {}, evidence)."""
    lines = [line for line in block if not line.blank]
    if len(lines) < 4:
        return None, {}, {"reason": "too few lines"}
    columns = _columns(lines)
    if len(columns) < 2:
        return None, {}, {"reason": "one column"}
    column_of = {line.id: index for index, col in enumerate(columns) for line in col["lines"]}
    wide = [line for line in lines if line.id not in column_of]
    first = columns[0]["lines"]
    base = sorted(line.start for line in first)[int(0.1 * (len(first) - 1))]

    def starts(col):
        termed = [line for line in col if line.term_end is not None]
        if termed:
            return termed
        return [line for line in col if line.start - base < 0.5 * line.size]

    row_starts = sorted(line.block for line in starts(first))
    others = [line for col in columns[1:] for line in starts(col["lines"]) if not line.page_ref]
    size = median(line.size for line in lines)
    synced = sum(any(abs(line.block - b) <= ROW * size for b in row_starts) for line in others)
    share = synced / len(others) if others else 0.0
    evidence = {"columns": len(columns), "rows": len(row_starts), "row_sync": round(share, 3),
                "wide_lines": len(wide)}  # fmt: skip
    if not row_starts or share < config["row_sync"]:
        return None, {}, {**evidence, "reason": "columns are not row-synchronised"}

    def row_of(line):
        index = 0
        for i, block_position in enumerate(row_starts):
            if block_position <= line.block + ROW * size:
                index = i
        return index

    position = {line.id: i for i, line in enumerate(block)}
    cells = {}
    for line in block:
        if line.id in column_of:
            cells[line.id] = (row_of(line), column_of[line.id])
        else:  # wide or blank lines stay with the line before them
            previous = cells.get(block[position[line.id] - 1].id) if position[line.id] else None
            cells[line.id] = previous or (row_of(line), 0)
    new = sorted(block, key=lambda line: (*cells[line.id], position[line.id]))
    return new, cells, evidence


def reorder_stream(order, stream_id, block_ids, new_ids, evidence, reasons):
    """The order with ``block_ids`` (in place) replaced by ``new_ids`` in one stream.

    Sequence edges of that stream are rebuilt (an existing edge keeps its kind, a new pair is
    ``next_in_stream``); float anchors keep their line and get its new position.
    """
    stream = next(s for s in order.streams if s.id == stream_id)
    slots = [i for i, lid in enumerate(stream.line_ids) if lid in set(block_ids)]
    line_ids = list(stream.line_ids)
    for slot, lid in zip(slots, new_ids, strict=True):
        line_ids[slot] = lid
    old_edges = {(e.source, e.target): e for e in order.edges if e.kind in SEQUENCE_EDGES}
    pairs = set(zip(stream.line_ids, stream.line_ids[1:], strict=False))
    edges = [e for e in order.edges if not (e.kind in SEQUENCE_EDGES and (e.source, e.target)
                                            in pairs)]  # fmt: skip
    for a, b in zip(line_ids, line_ids[1:], strict=False):
        edge = old_edges.get((a, b))
        edges.append(edge if edge is not None else OrderEdge(
            source=a, target=b, kind="next_in_stream", confidence=0.8,
            reasons=["glossary entry order"],
        ))  # fmt: skip
    streams = []
    main = line_ids if stream.kind == "main" else order.main.line_ids
    for s in order.streams:
        if s.id == stream_id:
            s = s.model_copy(update={"line_ids": line_ids})
        if s.anchor is not None and s.anchor.after_line_id is not None:
            s = s.model_copy(update={"anchor": s.anchor.model_copy(
                update={"position": main.index(s.anchor.after_line_id)})})  # fmt: skip
        streams.append(s)
    decision = OrderDecision(
        kind="row", subject_ids=list(block_ids), choice="entry_by_entry",
        alternatives=["line_by_line_rows"], confidence=0.85, reasons=reasons,
        evidence={k: v for k, v in evidence.items() if not isinstance(v, (list, dict))},
    )  # fmt: skip
    data = order.model_copy(
        update={"streams": streams, "edges": edges, "decisions": [*order.decisions, decision]}
    ).model_dump()
    return PageReadingOrder.model_validate(data), decision
