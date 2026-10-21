"""Table titles and notes, linked by position, the book's own numbering and style.

Page pass (``candidates``): for each table that owns its text, the units of the final unit
view next to it in its reading frame (above and below, overlapping its columns, the nearest
first and each further one close to the previous), and the table's own top and bottom rows
when they are one cell spanning the table. A candidate keeps evidence only (never text): its
side and rank, the casefolded word opening it before a number ("Table 3.2" -> "table"), the
word opening it before a full stop or colon ("Note." -> "note"), a footnote marker opening
it (a symbol, or a small raised span) and whether the table uses that marker, its unit kind.

Book pass (``link``):

- **Table labels** are learned from the book: words opening the nearest unit above or below
  (or the top row) of at least ``MIN_VOTES`` tables before a number, that the figure stage
  does not use for figure captions. The **title side** is the side most of them take.
- A **title** is the nearest unit on the title side opening with a table label and a number;
  else one on the other side (flagged). A unit is the title of one table only.
- **Note labels** are learned likewise: words opening, before "." or ":", units below at
  least ``MIN_VOTES`` tables. **Notes** are the units below the table (after its title when
  the title is below), each close to the previous, that open with a note label or with a
  footnote marker the table uses; the first other unit ends them.
- Title and note rows inside the table region are taken out of the grid on the same
  evidence (the table keeps owning their lines).
- Anything else next to a table that looks like a title (a caption unit, a unit set apart in
  a style the table's neighbours do not use) or a note (a marker the table does not use)
  stays unlinked with the reason, for review: a wrong link is worse than none. A unit linked
  to an exported figure as its caption or credit is never linked to a table; text a figure
  region merely contains (internal text) does not block a numbered title, which is then
  flagged. The figures a table absorbs as its pieces are not exported and claim nothing.

Distances are in font sizes of the table's text. No word list, font or coordinate is fixed.
"""

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from statistics import median

import regex

from book_core.layout.frames import to_frame
from book_core.tables.models import TableText, UnlinkedText
from book_core.tables.records import header_references

GAP = 2.5  # font sizes between the table edge and its nearest title or note
STACK_GAP = 1.5  # font sizes between stacked notes (or a title and the notes after it)
OVERLAP = 0.5  # share of the narrower of unit and table their column extents must share
RANKS = 4  # units considered on each side
MIN_VOTES = 2  # tables a label must open a neighbour of before it is the book's label
TITLE_LINES = 8  # longer units are not titles
# A label word before a number, the number optionally after an appendix letter ("C2").
NUMBERED = regex.compile(r"^\s*(\p{L}+)\.?\s*(?:\p{Lu}\.?\s*)?\p{N}")
# A note label opens the unit before "." or ":" and text follows it ("Note. Values are ...");
# a word alone with dots ("Contd...") marks a continued table, not a note.
NOTE_WORD = regex.compile(r"^\s*(\p{L}{2,15})\s*[.:]\s*[^\s.]")
MARKERS = frozenset("*†‡§¶#")
SKIP_KINDS = frozenset({"running_head", "running_foot", "folio", "production_mark", "artifact",
                        "invisible", "index_entry", "contents_entry", "definition_entry",
                        "bibliography_entry"})  # fmt: skip
CAPTION_KINDS = frozenset({"caption", "caption_candidate"})
NUMBERED_TITLE = "nearest unit opening with the book's table label and a number"
INSIDE_TITLE = "numbered title row inside the table region"
OTHER_SIDE = "title on the other side of the table than the book's numbered table titles"
UNNUMBERED = (
    "caption next to the table without the book's table label and a number; not linked "
    "(geometry alone is not enough evidence); review"
)
NO_NUMBERING = (
    "caption next to the table in a book without table numbering; not linked (geometry "
    "alone is not enough evidence); review"
)
INSIDE_FIGURE = "the title is also text inside a figure region; review the figure"
FIGURE_CLAIM = (
    "numbered table title is a figure's caption or credit; not linked to the table; review"
)
TAKEN = "numbered title nearer to another table; not linked here; review"
UNLEARNED_NOTE = (
    "opens with a word and a full stop or colon that opens no other table's notes in this "
    "book; not linked; review"
)
FOREIGN_MARKER = "opens with a footnote marker the table does not use; not linked; review"


@dataclass
class Candidate:
    table_id: str
    side: str  # above, below, top_row, bottom_row
    rank: int
    gap: float  # font sizes to the table (rank 0) or to the previous candidate
    unit_id: str | None
    line_ids: list
    kind: str
    lines: int
    label: str | None = None  # word before a number
    note_label: str | None = None  # word before "." or ":"
    marker: str | None = None
    marker_in_table: bool = False
    row: int | None = None  # grid row of an inside candidate


@dataclass
class PageCandidates:
    candidates: list[Candidate] = field(default_factory=list)
    figure_units: set = field(default_factory=set)


def _opening(evidence, line_id, size=48):
    text = "".join(evidence.spans[s].text for s in evidence.line(line_id).span_ids)
    return unicodedata.normalize("NFKC", text)[:size]


def _symbol(ch):
    return ch in MARKERS or unicodedata.category(ch).startswith("S")


def _raised(evidence, line, span):
    """A small raised span: set at most 0.85 of the line's size and ending above its foot."""
    sizes = [evidence.spans[s].size for s in line.span_ids if evidence.spans[s].text.strip()]
    size = median(sizes) if sizes else span.size
    return span.size <= 0.85 * size and span.bbox.y1 < line.bbox.y1 - 0.15 * size


def _marker(evidence, line_id):
    """The footnote marker opening a line: a symbol, or a short small raised span."""
    line = evidence.line(line_id)
    spans = [evidence.spans[s] for s in line.span_ids if evidence.spans[s].text.strip()]
    if not spans:
        return None
    first = spans[0].text.strip()
    if _symbol(first[0]):
        return first[0]
    if len(first) <= 2 and len(spans) > 1 and _raised(evidence, line, spans[0]):
        return first
    return None


def table_markers(evidence, table):
    """Footnote markers the table's text uses: symbols, and short raised spans."""
    found = set()
    for lid in table.line_ids:
        line = evidence.line(lid)
        for sid in line.span_ids:
            span = evidence.spans[sid]
            text = span.text.strip()
            found |= {ch for ch in text if _symbol(ch)}
            if text and len(text) <= 2 and _raised(evidence, line, span):
                found.add(text)
    return found


def _features(evidence, line_ids):
    opening = _opening(evidence, line_ids[0])
    numbered = NUMBERED.match(opening)
    word = NOTE_WORD.match(opening)
    return (
        numbered.group(1).casefold() if numbered else None,
        word.group(1).casefold() if word else None,
        _marker(evidence, line_ids[0]),
    )


def _union(boxes):
    return type(boxes[0])(
        x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
    )  # fmt: skip


def candidates(evidence, tables, units):
    """Candidates of one page's text-owning tables; ``units``: the final unit view."""
    out = []
    usable = [
        u for u in units
        if u.kind not in SKIP_KINDS and len(u.line_ids) <= TITLE_LINES
        and not any(evidence.line(lid).furniture for lid in u.line_ids)
    ]  # fmt: skip
    for table in tables:
        rotation = table.rotation

        def frame(box, rotation=rotation):
            return to_frame(box, rotation) if rotation else box

        sizes = [evidence.line(lid).font_size for lid in table.line_ids]
        font = median([s for s in sizes if s > 0] or [evidence.font])
        tb = frame(table.bbox)
        markers = table_markers(evidence, table)
        boxes = {u.id: frame(_union([evidence.line(lid).bbox for lid in u.line_ids]))
                 for u in usable}  # fmt: skip
        for side in ("above", "below"):
            near = []
            for unit in usable:
                ub = boxes[unit.id]
                width = min(ub.x1 - ub.x0, tb.x1 - tb.x0)
                if width <= 0 or min(ub.x1, tb.x1) - max(ub.x0, tb.x0) < OVERLAP * width:
                    continue
                if side == "above" and ub.y1 <= tb.y0 + 0.5 * font:
                    near.append((tb.y0 - ub.y1, unit))
                elif side == "below" and ub.y0 >= tb.y1 - 0.5 * font:
                    near.append((ub.y0 - tb.y1, unit))
            near.sort(key=lambda n: n[0])
            edge = None
            for rank, (distance, unit) in enumerate(near[:RANKS]):
                ub = boxes[unit.id]
                gap = distance if edge is None else (
                    (edge - ub.y1) if side == "above" else (ub.y0 - edge)
                )  # fmt: skip
                if gap / font > (GAP if edge is None else STACK_GAP):
                    break
                edge = ub.y0 if side == "above" else ub.y1
                label, word, marker = _features(evidence, unit.line_ids)
                out.append(Candidate(
                    table_id=table.id, side=side, rank=rank, gap=round(gap / font, 3),
                    unit_id=unit.id, line_ids=list(unit.line_ids), kind=unit.kind,
                    lines=len(unit.line_ids), label=label, note_label=word, marker=marker,
                    marker_in_table=marker is not None and marker in markers,
                ))  # fmt: skip
        columns = len(table.columns)
        if columns < 2 or len(table.rows) < 3:
            continue
        last = len(table.rows) - 1
        for side, rows in (("top_row", [0]), ("bottom_row", range(last, last - 3, -1))):
            for rank, row in enumerate(rows):
                found = [c for c in table.cells if c.row == row]
                if len(found) != 1 or found[0].column_span != columns or found[0].row_span != 1:
                    break
                cell = found[0]
                lines = list(cell.line_ids) + [
                    evidence.spans[r.span_id].line_id for r in cell.span_refs
                ]
                lines = list(dict.fromkeys(lines))
                if not lines:
                    break
                label, word, marker = _features(evidence, lines)
                out.append(Candidate(
                    table_id=table.id, side=side, rank=rank, gap=0.0, unit_id=None,
                    line_ids=lines, kind="table_row", lines=len(lines), label=label,
                    note_label=word, marker=marker,
                    marker_in_table=marker is not None and marker in markers, row=row,
                ))  # fmt: skip
    return out


def learn(candidates_by_page, figure_labels):
    """(table labels, title side, note labels) learned from every page's candidates."""
    labels, sides, notes = Counter(), Counter(), Counter()
    for found in candidates_by_page.values():
        by_table = {}
        for c in found:
            by_table.setdefault(c.table_id, []).append(c)
        for rows in by_table.values():
            seen = set()
            for c in rows:
                if c.rank == 0 and c.label and c.label not in figure_labels:
                    seen.add(c.label)
                    sides[(c.label, "below" if c.side == "below" else "above")] += 1
            labels.update(seen)
            words = {c.note_label for c in rows if c.side in {"below", "bottom_row"}
                     and c.note_label and not c.label}  # fmt: skip
            notes.update(words)
    table_labels = {w for w, n in labels.items() if n >= MIN_VOTES}
    above = sum(n for (w, s), n in sides.items() if w in table_labels and s == "above")
    below = sum(n for (w, s), n in sides.items() if w in table_labels and s == "below")
    side = None if not table_labels else ("above" if above >= below else "below")
    note_labels = {w for w, n in notes.items() if n >= MIN_VOTES and w not in table_labels}
    return table_labels, side, note_labels


def figure_claims(evidence, tables):
    """{unit id: "caption" | "internal"}: units the page's exported figures link (captions
    and credits; text inside their regions), without the figures the tables absorb."""
    pieces = {f for t in tables for f in t.absorbed_figure_ids}
    claims = {}
    for figure in evidence.figures:
        if figure["id"] in pieces:
            continue
        for unit in figure.get("internal_unit_ids", []):
            claims.setdefault(unit, "internal")
        for unit in figure.get("unit_ids", []):
            claims[unit] = "caption"
    return claims


def _validated(table, update):
    """The record with ``update`` applied, validated again (``model_copy`` does not)."""
    return type(table).model_validate(table.model_copy(update=update).model_dump())


def _unlinked(role, candidate, reason):
    return UnlinkedText(
        role=role, unit_id=candidate.unit_id, line_ids=candidate.line_ids, reason=reason
    )


def _title_side(candidate):
    return "below" if candidate.side == "below" else "above"


def _without_rows(table, rows):
    """The table record without the given rows (each one cell spanning the table)."""
    rows = set(rows)
    kept = [r for r in range(len(table.rows)) if r not in rows]
    new = {old: k for k, old in enumerate(kept)}
    cells = [
        c.model_copy(update={"row": new[c.row], "header_cell_ids": []})
        for c in table.cells if c.row not in rows
    ]  # fmt: skip
    header_rows = sum(1 for r in range(table.header_rows) if r not in rows)
    references = header_references(cells, header_rows, table.row_header_columns)
    cells = [
        c.model_copy(update={"header_cell_ids": [cells[h].id for h in references[k]]})
        for k, c in enumerate(cells)
    ]
    return {
        "rows": [table.rows[r] for r in kept],
        "cells": cells,
        "header_rows": header_rows,
    }


def link(pages, candidates_by_page, figure_units, figure_labels):
    """({page: table records with titles, notes and unlinked candidates}, statistics).

    ``pages``: {page: text-owning table records}; ``candidates_by_page``: {page: [Candidate]};
    ``figure_units``: {page: {unit id: "caption" | "internal"}} (``figure_claims``);
    ``figure_labels``: the figure stage's learned caption labels."""
    table_labels, side, note_labels = learn(candidates_by_page, set(figure_labels))
    stats = Counter()
    out = {}
    for number, tables in pages.items():
        found = candidates_by_page.get(number, [])
        claimed = figure_units.get(number, {})
        by_table = {t.id: [c for c in found if c.table_id == t.id] for t in tables}
        # Titles: the nearest numbered unit on the title side, else on the other side.
        options = []
        for table in tables:
            for c in by_table[table.id]:
                if (
                    c.side in {"above", "below", "top_row"}
                    and c.rank == 0
                    and (c.label in table_labels)
                ):
                    options.append((_title_side(c) != side, c.gap, table.id, c))
        options.sort(key=lambda o: (o[0], o[1], o[2]))
        titles, used, unlinked = {}, set(), {t.id: [] for t in tables}
        for other, _, table_id, c in options:
            key = c.unit_id or ("row", table_id, c.row)
            if table_id in titles:
                continue
            if key in used:
                unlinked[table_id].append(_unlinked("title", c, TAKEN))
                continue
            if claimed.get(c.unit_id) == "caption":
                unlinked[table_id].append(_unlinked("title", c, FIGURE_CLAIM))
                stats["figure_claims"] += 1
                continue
            used.add(key)
            titles[table_id] = (c, other)
        updated = []
        for table in tables:
            rows = by_table[table.id]
            update, flags, remove = {}, [], []
            title = titles.get(table.id)
            if title is not None:
                c, other = title
                rule = INSIDE_TITLE if c.unit_id is None else NUMBERED_TITLE
                update["title"] = TableText(role="title", unit_id=c.unit_id,
                                            line_ids=c.line_ids, rule=rule, numbered=True,
                                            confidence=0.75 if other else 0.9)  # fmt: skip
                if other:
                    flags.append(OTHER_SIDE)
                if claimed.get(c.unit_id) == "internal":
                    flags.append(INSIDE_FIGURE)
                    stats["titles_inside_figure_regions"] += 1
                if c.unit_id is None:
                    remove.append(c.row)
                stats["titles_inside" if c.unit_id is None else "titles"] += 1
            # Notes: below the table (after a title below it), each close to the previous.
            title_unit = title[0].unit_id if title else None
            notes = []
            # Bottom rows from the lowest upward, while they are notes.
            inside = sorted((c for c in rows if c.side == "bottom_row"), key=lambda c: -c.row)
            below = sorted((c for c in rows if c.side == "below"), key=lambda c: c.rank)
            noted_inside = []
            for c in inside:
                if (c.note_label in note_labels or c.marker_in_table) and not c.label:
                    noted_inside.append(c)
                else:
                    break
            for c in sorted(noted_inside, key=lambda c: c.row):
                notes.append(TableText(role="note", unit_id=None, line_ids=c.line_ids,
                                       rule="note row inside the table region",
                                       confidence=0.8))  # fmt: skip
                remove.append(c.row)
            for c in below:
                if c.unit_id == title_unit:
                    continue
                if c.unit_id in claimed or c.unit_id in used:
                    break  # a figure's text (or another table's) ends the notes
                if c.label:
                    break  # a numbered unit (another table's or figure's title) ends the notes
                if c.note_label in note_labels:
                    rule, confidence = "unit below opening with the book's note label", 0.85
                elif c.marker_in_table:
                    rule, confidence = "unit below opening with a footnote marker of the table", 0.8
                else:
                    if c.rank == 0 or notes:
                        if c.marker is not None:
                            unlinked[table.id].append(_unlinked("note", c, FOREIGN_MARKER))
                        elif c.note_label is not None:
                            unlinked[table.id].append(_unlinked("note", c, UNLEARNED_NOTE))
                    break
                notes.append(TableText(role="note", unit_id=c.unit_id, line_ids=c.line_ids,
                                       rule=rule, confidence=confidence))  # fmt: skip
                used.add(c.unit_id)
            if notes:
                update["notes"] = notes
                stats["notes"] += len(notes)
            # Title-like neighbours left unlinked.
            if title is None:
                for c in rows:
                    if c.rank != 0 or c.unit_id is None or c.unit_id in used:
                        continue
                    if c.kind in CAPTION_KINDS and not (c.label and c.label in figure_labels):
                        reason = UNNUMBERED if table_labels else NO_NUMBERING
                        unlinked[table.id].append(_unlinked("title", c, reason))
            if remove and len(table.rows) - len(set(remove)) >= 2:
                update.update(_without_rows(table, remove))
            elif remove:
                # Too few rows would remain: the rows stay cells; inside links are dropped.
                if update.get("title") and update["title"].unit_id is None:
                    update.pop("title")
                    stats["titles_inside"] -= 1
                update["notes"] = [n for n in update.get("notes", []) if n.unit_id is not None]
            if unlinked[table.id]:
                update["unlinked_texts"] = unlinked[table.id]
                stats["unlinked"] += len(unlinked[table.id])
            if flags:
                update["review_flags"] = [*table.review_flags, *flags]
            if update:
                table = _validated(table, update)
            updated.append(table)
        out[number] = updated
    return out, {
        "table_labels": sorted(table_labels),
        "title_side": side,
        "note_labels": sorted(note_labels),
        **dict(stats),
    }
