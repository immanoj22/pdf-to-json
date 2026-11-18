"""One page: table regions decided from combined evidence, each with its grid.

``analyze`` returns drafts (accepted tables with their grids, and rejected candidates with
the reason) for the stage to turn into records. See ``tables.detect`` for the evidence
families and look-alike tests and ``tables.grid`` for the structure.
"""

from dataclasses import dataclass, field

from book_core.figures.page import TITLED
from book_core.layout.evidence import PARAGRAPH_TOKENS, question_texts, token_count
from book_core.tables.detect import (
    STRIPES,
    candidates,
    content_rules,
    covers,
    frame_rotation,
    grow,
    organizer,
    region_lines,
    shared,
    stripes,
    text_cells,
    timeline,
    union,
)
from book_core.tables.evidence import ENTRY_KINDS, body_style
from book_core.tables.grid import WORD_GAP, atoms_of, columns_from_text, structure

MARGIN = 0.3  # font sizes around a region for its lines
STRIPE_MARGIN = 0.5  # font sizes: lines this far outside a stripe set's sides still belong to it
PARAGRAPH_SHARE = 0.5  # aligned regions mostly made of running text lines are not tables
ENTRY_SHARE = 0.5
FIGURE_SHARE = 0.6  # raster figures covering this share of a region make it a figure panel
LABEL_SHARE = 0.5  # or this share of its lines being figure text (labels) ...
LABELLED_SHARE = 0.3  # ... over raster figures covering at least this share
FREEFORM_MIN = 8  # free-form drawings (curves, slanted strokes) inside a region ...
FREEFORM_SHARE = 0.3  # ... covering this share of it make it a drawing panel
OWNING_MODELS = 2  # detectors that must agree for a table to own its text
LIST_SHARE = 0.9  # regions made of list items only are lists in columns, not tables
NAVIGATION = frozenset({"table_of_contents", "index", "glossary", "bibliography", "other_list"})


@dataclass
class TableDraft:
    bbox: object
    rotation: float
    lines: list
    grid: object
    sources: dict
    families: list[str]
    confidence: float
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    rules: list = field(default_factory=list)
    fills: list = field(default_factory=list)
    strong: bool = True  # strong evidence: the table owns its text; else a possible table


@dataclass
class Rejected:
    bbox: object
    kind: str
    sources: dict
    reasons: list[str]


def _inside(items, box, key):
    return [i for i in items if covers(key(i), box, 0.9) or box.contains_center(key(i))]


def _rule_box(rule):
    from book_core.model.common import BBox

    if rule.axis == "h":
        return BBox(x0=rule.start, y0=rule.at - 0.5, x1=rule.end, y1=rule.at + 0.5)
    return BBox(x0=rule.at - 0.5, y0=rule.start, x1=rule.at + 0.5, y1=rule.end)


def _figure_panel(evidence, box, lines):
    """A panel around a figure (a map with its title and questions in ruled bands): raster
    figures cover most of the region, or most of its lines are figure text (labels)."""
    from book_core.tables.detect import area

    def raster(figure):
        return any(evidence.objects.get(o) == "image" for o in figure["object_ids"])

    covered = sum(shared(f["bbox"], box) for f in evidence.figures if raster(f))
    # A vector drawing (a map's outlines, a diagram) fills the region with free-form strokes.
    strokes = [b for b in getattr(evidence, "freeform", []) if box.contains_center(b)]
    if len(strokes) >= FREEFORM_MIN and sum(map(area, strokes)) >= FREEFORM_SHARE * area(box):
        return True
    labels = sum(line.unit_kind == "figure_text" for line in lines)
    # Labels count only over an image: some layouts place real tables in figure regions.
    return covered >= FIGURE_SHARE * area(box) or (
        labels >= LABEL_SHARE * len(lines) and covered >= LABELLED_SHARE * area(box)
    )


def _running_text(evidence, line, body):
    """A line of running text: in the page's body style with several words."""
    spans = [evidence.spans[s] for s in line.span_ids]
    text = "".join(s.text for s in spans)
    styled = sum(len(s.text.strip()) for s in spans if (s.font, round(s.size)) == body)
    return token_count(text) >= PARAGRAPH_TOKENS and styled >= 0.6 * len(text.strip())


def _captioned(evidence, lines, models, separators, bands):
    """A captioned table: detectors agree (two or more), the text stands in aligned columns,
    and the region opens with a numbered, titled caption line ("TABLE 2: Troubleshooting
    ..."; any label word). Its first column of short labels is the table's stub, not
    labels beside running text."""
    if len(models) < 2 or not separators or bands < 2 or not lines:
        return False
    top = min(line.bbox.y0 for line in lines)
    first = [line for line in lines if line.bbox.y0 <= top + 1.0]
    text = " ".join("".join(evidence.spans[s].text for s in line.span_ids) for line in first)
    return bool(TITLED.match(text))


def _bulleted(evidence, line):
    """A list-item line opened by a marker that is not a number (bullets, dashes)."""
    if line.unit_kind != "list_item" or not line.span_ids:
        return False
    first = evidence.spans[line.span_ids[0]].text.strip()
    return bool(first) and not any(
        ch.isdigit() or ch.isalpha() and ch.isascii() for ch in first[:2]
    )


def _labelled_text(evidence, lines, body, separators, rotation, atoms):
    """Unruled label column beside running text in the body style (dialogue, glosses): the
    last column holds body-style text of several words in most bands, and no column is
    numeric."""
    if not separators or body is None:
        return False
    last = separators[-1]
    tail = [a for a in atoms if a.box.x0 >= last]
    if not tail:
        return False
    from book_core.layout.evidence import NUMERIC_CELL

    if sum(bool(NUMERIC_CELL.match(a.text.strip())) for a in atoms) >= 0.2 * len(atoms):
        return False
    body_like = [a for a in tail if (a.font, round(a.size)) == body]
    words = sum(token_count(a.text) for a in body_like)
    tail_lines = {a.line_id for a in tail}
    return (
        len(body_like) >= 0.6 * len(tail)
        and words >= PARAGRAPH_TOKENS * max(1, len(tail_lines)) * 0.8
    )


def _column_gaps(evidence, box, bands, font):
    """The gaps between the columns of a striped table: x ranges at least a word space wide
    that no text span of the lines inside the shaded bands touches."""
    spans = []
    for line in evidence.lines:
        if line.blank or line.furniture or not any(n.bbox.contains_center(line.bbox) for n in bands):
            continue
        for sid in line.span_ids:
            span = evidence.spans[sid]
            if span.text.strip():
                spans.append((span.bbox.x0, span.bbox.x1))
    gaps, end = [], None
    for x0, x1 in sorted(spans):
        if end is not None and x0 - end >= WORD_GAP * font:
            gaps.append((end, x0))
        end = x1 if end is None else max(end, x1)
    return [g for g in gaps if box.x0 < g[0] and g[1] < box.x1]


def _straddles(evidence, line, gaps):
    """A span of the line covers a whole column gap: running text, a caption or a note, not
    the cell of one column."""
    for sid in line.span_ids:
        span = evidence.spans[sid]
        if span.text.strip() and any(span.bbox.x0 <= a and b <= span.bbox.x1 for a, b in gaps):
            return True
    return False


def _striped_extent(evidence, bands, font):
    """The box of a striped table: the shaded bands and the rows of text above and below them
    that belong to the same columns. Rows are added upward and downward while the next line
    (in the bands' column extent) is no further away than the widest gap between two bands
    (the height of an unshaded row) and stays within one column (a span covering a column gap
    is a caption, a note or running text and ends it)."""
    box = union([n.bbox for n in bands])
    gaps = _column_gaps(evidence, box, bands, font)
    if not gaps:
        return box
    spacing = [b.bbox.y0 - a.bbox.y1 for a, b in zip(bands, bands[1:])]
    reach = max(max(spacing, default=0.0), 1.5 * font)
    margin = STRIPE_MARGIN * font
    pool = [
        line for line in evidence.lines
        if not line.blank and not line.furniture
        and box.x0 - margin <= (line.bbox.x0 + line.bbox.x1) / 2 <= box.x1 + margin  # fmt: skip
    ]
    for direction in (-1, 1):
        edge = box.y0 if direction < 0 else box.y1
        while True:
            beyond = [
                line for line in pool
                if ((line.bbox.y0 + line.bbox.y1) / 2 <= edge + 1.0 if direction < 0
                    else (line.bbox.y0 + line.bbox.y1) / 2 >= edge - 1.0)
                and abs((line.bbox.y1 if direction < 0 else line.bbox.y0) - edge) <= reach
                and not (box.y0 <= line.bbox.y0 and line.bbox.y1 <= box.y1)  # fmt: skip
            ]
            if not beyond:
                break
            near = min(beyond, key=lambda l: abs((l.bbox.y1 if direction < 0 else l.bbox.y0) - edge))
            row = [
                l for l in beyond
                if abs((l.bbox.y1 if direction < 0 else l.bbox.y0)
                       - (near.bbox.y1 if direction < 0 else near.bbox.y0)) <= font
            ]  # the lines of this unshaded row (the same band of text)
            if any(_straddles(evidence, l, gaps) for l in row):
                break
            box = union([box, *[l.bbox for l in row]])
            edge = min(l.bbox.y0 for l in row) if direction < 0 else max(l.bbox.y1 for l in row)
    return box


def analyze(evidence):
    """(tables, rejected) of one page."""
    font = evidence.font
    tables, rejected = [], []
    for candidate in candidates(evidence):
        sources = dict(candidate.sources)
        box = candidate.bbox
        lines = region_lines(evidence, box, MARGIN * font)
        if not lines:
            rejected.append(Rejected(box, "no_text", sources, ["no content lines inside"]))
            continue
        rotation = frame_rotation(lines)
        if rotation is None:
            rejected.append(Rejected(box, "mixed_rotation", sources, ["lines in several frames"]))
            continue
        shaded = stripes(candidate.networks, font) if not rotation else []
        if shaded:  # alternate shaded rows: the table is the bands and the rows around them
            box = _striped_extent(evidence, shaded, font)
            lines = region_lines(evidence, box, MARGIN * font)
        elif not any(n.kind != "stack" for n in candidate.networks) and not candidate.layout:
            # Without a closed grid the text gives the extent (model boxes may run wide).
            box = union([line.bbox for line in lines] + [n.bbox for n in candidate.networks])
            lines = region_lines(evidence, box, MARGIN * font)
        texts = ["".join(evidence.spans[sid].text for sid in line.span_ids) for line in lines]
        if question_texts(texts):
            # A numbered stem with lettered options in a grid is a question, not a table.
            rejected.append(Rejected(box, "multi_column_text", sources,
                                     ["a numbered stem with lettered options (a question)"]))
            continue
        atoms = atoms_of(evidence, lines, rotation)
        frame = box if not rotation else None
        from book_core.layout.frames import to_frame

        frame = frame or to_frame(box, rotation)
        left = min([a.box.x0 for a in atoms] + [frame.x0])
        right = max([a.box.x1 for a in atoms] + [frame.x1])
        separators, bands = columns_from_text(atoms, left, right, font)
        families = []
        nets = candidate.networks
        # A rule network is table evidence when its own cells hold text in at least two
        # rows and two columns (a frame or a decorative band around text is not).
        grid_text = any(n.kind == "grid" and min(text_cells(n, lines, font)) >= 2 for n in nets)
        grid_rules = grid_text or (
            "layout_ruled" in sources and any(n.kind == "grid" for n in nets)
        )
        stack_rules = any(n.kind == "stack" for n in nets)
        frame_rules = any(n.kind == "frame" for n in nets)
        # Alternate shaded rows are ruled-row evidence when the text stands in aligned columns.
        striped = bool(shaded) and bool(separators) and bands >= STRIPES
        if grid_rules or stack_rules or striped:
            families.append("rules")
        # Aligned text: columns of text gaps, a Step 4 aligned region, or text set in at least
        # two rows and two columns of a ruled grid's own cells.
        if (separators and bands >= 2) or "layout_aligned" in sources or grid_text:
            families.append("alignment")
        models = sorted(s[len("model_") :] for s in sources if s.startswith("model_"))
        # Beside aligned text alone (no rules), one detector is too weak: two must agree.
        if len(models) >= (1 if "rules" in families else 2):
            families.append("models")
        body = body_style(evidence)
        paragraph = sum(1 for line in lines if _running_text(evidence, line, body))
        entries = sum(line.unit_kind in ENTRY_KINDS for line in lines)
        labelled = _labelled_text(evidence, lines, body, separators, rotation, atoms)
        navigation = getattr(evidence, "navigation", None)
        reason = None
        if organizer(nets, font) and not grid_rules and not striped:
            reason = ("graphic_organizer", "separate boxes that share no border")
        elif _figure_panel(evidence, box, lines):
            reason = ("figure_panel", "a figure fills the ruled panel; its labels are not cells")
        elif timeline(nets, font):
            reason = ("timeline", "one axis with short ticks")
        elif not grid_rules and paragraph >= PARAGRAPH_SHARE * len(lines):
            reason = ("multi_column_text", "mostly running text lines without a ruled grid")
        elif not grid_rules and not stack_rules and navigation in NAVIGATION:
            reason = ("index_or_contents", f"aligned text on a printed {navigation} page")
        elif not grid_rules and not stack_rules and labelled and not _captioned(
                evidence, lines, models, separators, bands):  # fmt: skip
            reason = ("multi_column_text", "labels beside running body text (no rules)")
        elif sum(_bulleted(evidence, line) for line in lines) >= LIST_SHARE * len(lines):
            reason = ("multi_column_text", "list items in columns (no table cells)")
        elif not grid_rules and entries >= ENTRY_SHARE * len(lines):
            reason = ("index_or_contents", "aligned entries of an index, contents or glossary")
        elif len(families) < 2:
            reason = (
                "single_source",
                f"one evidence family only ({', '.join(families) or 'none'}"
                f"{'; a frame around text' if frame_rules else ''})",
            )
        if reason is not None:
            rejected.append(Rejected(box, reason[0], sources, [reason[1]]))
            continue
        rules = [r for r in content_rules(evidence) if covers(_rule_box(r), grow(box, font), 0.5)]
        fills = [f for f in evidence.fills if covers(f.bbox, grow(box, font), 0.8)]
        grid = structure(evidence, box, rotation, lines, rules, fills)
        if len(grid.rows) < 2 or len(grid.columns) < 2:
            rejected.append(
                Rejected(
                    box,
                    "not_a_grid",
                    sources,
                    [f"{len(grid.rows)} row(s) x {len(grid.columns)} column(s)"],
                )  # fmt: skip
            )
            continue
        confidence = min(0.95, 0.45 + 0.15 * len(families) + 0.05 * max(0, len(models) - 1))
        # Strong evidence (the table takes ownership of its text): two learned detectors agree
        # on the region and its geometry is tabular (a ruled grid holding text in its cells,
        # the rules of an unboxed table, or text aligned in columns). Anything weaker is a
        # possible table, recorded for review; its lines stay in their units. (Measured: every
        # reference-matched table has model support; ruled boxes without it are mostly panels,
        # organizers and callouts.)
        text_aligned = bool(separators) and bands >= 2
        navigation = getattr(evidence, "navigation", None)
        geometry = grid_text or stack_rules or text_aligned
        if navigation in NAVIGATION:
            # Printed navigation (contents, index, glossary) may be ruled like a table; its
            # entries keep their units: at most a possible table.
            strength = None
        elif geometry and len(models) >= OWNING_MODELS:
            strength = f"tabular geometry and {len(models)} detectors agree"
        else:
            strength = None
        tables.append(
            TableDraft(
                bbox=box,
                rotation=rotation,
                lines=lines,
                grid=grid,
                sources=sources,
                families=families,
                confidence=round(confidence, 3),
                reasons=[f"evidence: {', '.join(families)}"]
                + ([f"owns its text: {strength}"] if strength else []),
                rules=rules,
                fills=fills,
                strong=strength is not None,
            )
        )
    # Two accepted regions sharing lines: keep the one with more evidence (then larger).
    tables.sort(key=lambda t: (not t.strong, -len(t.families), -len(t.lines)))
    kept = []
    for table in tables:
        ids = {line.id for line in table.lines}
        if any(ids & {line.id for line in k.lines} for k in kept):
            overlap = next(k for k in kept if ids & {line.id for line in k.lines})
            if shared(table.bbox, overlap.bbox) > 0:
                reason = ["shares lines with a better-supported table"]
                rejected.append(Rejected(table.bbox, "overlaps_table", table.sources, reason))
                continue
        kept.append(table)
    return kept, rejected
