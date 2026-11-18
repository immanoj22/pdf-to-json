"""Display equations found from how the page is set (additive evidence, not wired in yet).

Some producers set an equation as many one-glyph text lines with font metrics so tall that the
line boxes overlap the prose above and below. The visual band of a line is therefore taken from
its **baseline** and font size, never from its box. A display equation is a group of lines that

- share the band of no prose line (a prose line holds several words),
- are not text of a figure, table, footnote, credit, furniture or other non-text layout region,
- carry maths (a relation or operator character, a Greek letter, or lines the equation stage
  already read as maths) and make up at least ``MIN_ATOMS`` characters,
- are set apart: centred in the column of the prose lines above and below, or indented from
  its left edge by ``INDENT`` text sizes.

A group whose right edge carries an equation label (``(5.5)``, ``(A.3)``, ``(12)``) set at the
column's right edge is a **numbered** display equation; the label is not part of the equation.
All distances are relative to the text size and to the prose lines around the group; the
column is read from those lines, never assumed."""

from __future__ import annotations

import statistics
import unicodedata
from dataclasses import dataclass, field

import regex

LABEL = regex.compile(r"^\(\s*[\p{L}]?\d+(?:[.\-–][\p{L}\d]+)*[\p{Ll}]?\s*\)$")
PROSE_WORDS = 4  # a line with this many words (two letters or more) is prose
MIN_ATOMS = 3
ASCENT, DESCENT = 0.8, 0.25  # band of a line around its baseline, in text sizes
BAND_GAP = 0.15  # lines whose bands come this close (sizes) are one row
CENTRED = 0.2  # centre within this share of the column width of the column centre
INDENT = 2.0  # or left edge this many sizes in from the column's left edge
LABEL_EDGE = 0.15  # a label ends within this share of the column width of the right edge
NOT_EQUATION_REGIONS = frozenset(
    {"figure", "table_candidate", "header_footer_candidate", "page_number_candidate",
     "footnote_candidate", "credit_candidate", "artifact_candidate"}
)  # a caption-like region may hold an equation the layout mistook for a caption
RELATIONS = frozenset("=≈≠≤≥<>∝∼≡→←⇌↔")


@dataclass
class Row:
    line_id: str
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float


@dataclass
class Candidate:
    line_ids: list[str]
    box: tuple[float, float, float, float]
    numbered: bool
    label: str | None
    text: str
    reasons: list[str] = field(default_factory=list)


def _band(line):
    y = (line.baseline_start[1] + line.baseline_end[1]) / 2
    size = line.font_size
    return y - ASCENT * size, y + DESCENT * size


def _is_prose(text: str) -> bool:
    words = [w for w in regex.findall(r"\p{L}{2,}", text)]
    return len(words) >= PROSE_WORDS


def _mathy(text: str) -> bool:
    for ch in text:
        if ch in RELATIONS or unicodedata.category(ch) == "Sm":
            return True
        if "GREEK" in unicodedata.name(ch, ""):
            return True
    return False


def display_candidates(store, lines, region_type, math_lines=frozenset()):
    """Candidates of one page. ``lines``: layout lines inside the content; ``region_type``:
    {line id: layout region type}; ``math_lines``: ids of lines the equation stage read as
    maths."""
    rows, prose = [], []
    for line in lines:
        if line.blank or not line.horizontal or not line.visible:
            continue
        text = "".join(store.spans[s].raw_text for s in line.span_ids).strip()
        if not text:
            continue
        top, bottom = _band(line)
        row = Row(line.id, text, line.bbox.x0, line.bbox.x1, top, bottom, line.font_size)
        (prose if _is_prose(text) else rows).append(row)
    if not rows or not prose:
        return []
    size = statistics.median(r.size for r in prose)
    eligible = [r for r in rows if region_type.get(r.line_id, "main_text") not in NOT_EQUATION_REGIONS]
    # rows that share a band with prose are inline pieces of that prose
    free = [
        r
        for r in eligible
        if not any(min(r.bottom, p.bottom) - max(r.top, p.top) > 0.3 * size for p in prose)
        # prose line boxes of this book are tall; the band test above uses baselines only
    ]
    free.sort(key=lambda r: (r.top, r.x0))
    groups: list[list[Row]] = []
    for r in free:
        for g in groups:
            if r.top <= max(x.bottom for x in g) + BAND_GAP * size and r.bottom >= min(x.top for x in g) - BAND_GAP * size:
                g.append(r)
                break
        else:
            groups.append([r])
    merged = True
    while merged:  # bands that grew together
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                if min(x.top for x in b) <= max(x.bottom for x in a) + BAND_GAP * size and max(
                    x.bottom for x in b
                ) >= min(x.top for x in a) - BAND_GAP * size:
                    groups[i] = a + b
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    out = []
    for g in groups:
        label = next(
            (r for r in sorted(g, key=lambda r: -r.x1) if LABEL.match(r.text.replace(" ", ""))), None
        )
        body = [r for r in g if r is not label]
        if not body:
            continue
        text = " ".join(r.text for r in sorted(body, key=lambda r: (r.x0, r.top)))
        atoms = sum(len(r.text.replace(" ", "")) for r in body)
        top = min(r.top for r in body)
        bottom = max(r.bottom for r in body)
        x0, x1 = min(r.x0 for r in body), max(r.x1 for r in body)
        pieces = sum(r.line_id in math_lines for r in body)
        if atoms < MIN_ATOMS or not (_mathy(text) or pieces >= 2):
            continue
        # the column: the nearest prose line above and below that share horizontal extent
        near = [
            p
            for p in prose
            if min(p.x1, x1) - max(p.x0, x0) > 0
            and (p.bottom <= top or p.top >= bottom)
        ]
        above = [p for p in near if p.bottom <= top]
        below = [p for p in near if p.top >= bottom]
        column = [max(above, key=lambda p: p.bottom)] if above else []
        column += [min(below, key=lambda p: p.top)] if below else []
        if not column:
            continue
        col0 = min(p.x0 for p in column)
        col1 = max(p.x1 for p in column)
        width = max(col1 - col0, 1.0)
        centre_ok = abs((x0 + x1) / 2 - (col0 + col1) / 2) <= CENTRED * width
        indent_ok = x0 - col0 >= INDENT * size
        if not (centre_ok or indent_ok):
            continue
        numbered = label is not None and label.x1 >= col1 - LABEL_EDGE * width
        reasons = ["no prose in its band", "centred" if centre_ok else "indented"]
        if numbered:
            reasons.append("equation label at the right edge")
        out.append(
            Candidate(
                line_ids=[r.line_id for r in g],
                box=(x0, top, x1, bottom),
                numbered=numbered,
                label=label.text if numbered else None,
                text=text,
                reasons=reasons,
            )
        )
    return out
