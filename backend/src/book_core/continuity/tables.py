"""Tables continued on the next page: one logical table over its per-page records.

The tables stage marks the last table of a page and the first of the next as continued
when they share their frame and column proportions near the page edges. Here each such pair
becomes a break of a table chain:

- **Column map**: the continuation's columns map one to one onto the first part's (the
  tables stage requires the same count and proportions); when the first part has header
  rows, the continuation's header-row cells must agree with them where both have text.
- **Repeated header rows**: the continuation's leading rows whose cell texts (NFKC,
  casefolded, spaces collapsed) equal the first part's header rows, row by row (its first
  row when it has no header rows), repeat the header. They stay in the record and are
  named, so the logical table does not repeat them.
- **Continuation marks**: a one-line unit of at most ``MARK_WORDS`` words directly below
  the first part (after it in the main flow) or directly above the continuation, that is
  neither table's title or note ("Contd...", "(continued)"); and a continuation title that
  repeats the first part's title label and number.

A last table near the page bottom and a first table near the next page's top in the same
frame whose column counts differ is not joined: it is kept as a candidate for review.
"""

from __future__ import annotations

import unicodedata

import regex

from book_core.continuity.models import Candidate, ContinuationMark, PageBreak
from book_core.tables.records import EDGE_SHARE

MARK_WORDS = 2
_SPACE = regex.compile(r"\s+")
_WORD = regex.compile(r"\w+")


def _norm(text):
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip().casefold()


def row_texts(table, store, lines):
    """{row: [normalised cell text per cell of the row, in column order]}."""
    rows = {}
    for cell in sorted(table.cells, key=lambda c: (c.row, c.column)):
        parts = []
        for lid in cell.line_ids:
            line = lines.get(lid)
            if line is not None:
                parts.append("".join(store.spans[s].raw_text for s in line.span_ids))
        for ref in cell.span_refs:
            text = store.spans[ref.span_id].raw_text
            parts.append(text if ref.start is None else text[ref.start : ref.end])
        rows.setdefault(cell.row, []).append(_norm(" ".join(parts)))
    return rows


def repeated_rows(first, rows_first, rows_next):
    """Leading rows of the continuation repeating the first part's header rows (its first
    row when the first part has no header rows: a repeated first row is a header)."""
    count = first.header_rows or 1
    for r in range(count):
        a, b = rows_first.get(r), rows_next.get(r)
        if not a or not b or a != b or not any(a):
            return 0
    return count


def _near(table, content, side):
    height = content.y1 - content.y0
    if side == "bottom":
        return table.bbox.y1 >= content.y1 - EDGE_SHARE * height
    return table.bbox.y0 <= content.y0 + EDGE_SHARE * height


def _unit_text(store, lines, unit):
    return " ".join(
        "".join(store.spans[s].raw_text for s in lines[lid].span_ids)
        for lid in unit.line_ids
        if lid in lines
    )


def marks(table, number, units, order, store, lines, side):
    """Continuation marks next to ``table``: below it (``side`` "below") or above it."""
    taken = {t.unit_id for t in [table.title, *table.notes] if t is not None}
    main = [lid for s in order.streams if s.kind == "main" for lid in s.line_ids]
    unit_of = {lid: u for u in units for lid in u.line_ids}
    sequence = []
    for lid in main:
        unit = unit_of.get(lid)
        key = table.id if lid in set(table.line_ids) else (unit.id if unit else None)
        if key is not None and (not sequence or sequence[-1][0] != key):
            sequence.append((key, unit if key != table.id else None))
    ids = [k for k, _ in sequence]
    if table.id not in ids:
        return []
    at = ids.index(table.id)
    near = sequence[at + 1 : at + 2] if side == "below" else sequence[max(0, at - 1) : at]
    out = []
    for _, unit in near:
        if unit is None or unit.id in taken or len(unit.line_ids) != 1:
            continue
        words = _WORD.findall(unicodedata.normalize("NFKC", _unit_text(store, lines, unit)))
        if 0 < len(words) <= MARK_WORDS:
            out.append(ContinuationMark(
                page=number, unit_id=unit.id, line_ids=list(unit.line_ids), position=side,
                reasons=[f"a short line directly {side} the continued table"],
            ))  # fmt: skip
    return out


def title_mark(first, following, number, store_a, lines_a, store_b, lines_b, units_b):
    """The continuation's title, when it repeats the first part's title label and number."""
    if first.title is None or following.title is None or following.title.unit_id is None:
        return []
    a = _WORD.findall(_norm(" ".join(
        "".join(store_a.spans[s].raw_text for s in lines_a[lid].span_ids)
        for lid in first.title.line_ids if lid in lines_a)))  # fmt: skip
    b = _WORD.findall(_norm(" ".join(
        "".join(store_b.spans[s].raw_text for s in lines_b[lid].span_ids)
        for lid in following.title.line_ids if lid in lines_b)))  # fmt: skip
    if len(a) >= 2 and a[:2] == b[:2] and following.title.numbered:
        return [ContinuationMark(page=number, unit_id=following.title.unit_id,
                                 line_ids=list(following.title.line_ids), position="title",
                                 reasons=["the continuation's title repeats the table's label "
                                          "and number"])]  # fmt: skip
    return []


def table_break(first, following, a, b, label):
    """PageBreak between two continued table records; ``a``/``b``: (page, store, lines,
    final units, order) of the two pages."""
    number_a, store_a, lines_a, units_a, order_a = a
    number_b, store_b, lines_b, units_b, order_b = b
    rows_a = row_texts(first, store_a, lines_a)
    rows_b = row_texts(following, store_b, lines_b)
    repeated = repeated_rows(first, rows_a, rows_b)
    found = marks(first, number_a, units_a, order_a, store_a, lines_a, "below")
    found += marks(following, number_b, units_b, order_b, store_b, lines_b, "above")
    found += title_mark(first, following, number_b, store_a, lines_a, store_b, lines_b, units_b)
    reasons = list(following.continues_from.reasons)
    if repeated:
        reasons.append(f"{repeated} header row(s) repeated at the top of the continuation")
    if found:
        reasons.append("continuation marked next to the table")
    last_line = max(first.line_ids, key=lambda lid: lines_a[lid].bbox.y1 if lid in lines_a
                    else 0)  # fmt: skip
    first_line = min(following.line_ids, key=lambda lid: lines_b[lid].bbox.y0 if lid in lines_b
                     else 0)  # fmt: skip
    confidence = following.continues_from.confidence
    return PageBreak(
        from_page=number_a, from_id=first.id, from_line_id=last_line,
        to_page=number_b, to_id=following.id, to_line_id=first_line,
        page_label=label[0], label_source=label[1],
        repeated_header_rows=repeated,
        column_map=list(range(len(following.columns))),
        marks=found, source="tables", confidence=confidence, reasons=reasons,
        review_required=confidence < 0.75,
    )  # fmt: skip


def mismatch(last, first, content_a, content_b, number_a):
    """A candidate for a pair at the page edges whose columns do not map (review)."""
    if last.continues_to is not None or first.continues_from is not None:
        return None
    if last.rotation != first.rotation or len(last.columns) == len(first.columns):
        return None
    if last.rotation == 0 and not (_near(last, content_a, "bottom")
                                   and _near(first, content_b, "top")):  # fmt: skip
        return None
    return Candidate(
        kind="table", from_page=number_a, from_id=last.id, to_page=number_a + 1,
        to_id=first.id,
        reasons=[f"tables at the page break in one frame, column counts differ "
                 f"({len(last.columns)} -> {len(first.columns)}): kept separate; review"],
        review_required=True,
    )  # fmt: skip
