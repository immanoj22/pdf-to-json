"""Paragraphs continued across a page break.

The candidate pair is the last text unit of one page's main flow and the first text unit of
the next page's main flow. Furniture, floats and notes live in other streams, so they never
sit between the two halves. A join needs agreement: Step 7 continuation evidence says the text
continues (open or hyphenated end, lowercase or continuing start), both units are running
text of the same kind and style, and the next unit does not start with a first-line indent or
a new hanging entry.
Otherwise the halves stay separate; a 'neutral' case is recorded as a flagged candidate.
"""

from __future__ import annotations

import unicodedata

from book_core.paragraphs.models import REVIEW_BELOW, LineJoin, PageJoin
from book_core.reading_order.continuation import continuation

RUNNING = frozenset({"paragraph", "list_item_candidate"})


def _text(page, layout, line_id):
    line = next(line for line in layout.lines if line.id == line_id)
    raw = "".join(page.store.spans[s].raw_text for s in line.span_ids)
    return unicodedata.normalize("NFKC", raw)


def edge_units(units):
    """(last main-flow text unit, first main-flow text unit) of one page."""
    main = [u for u in units if u.stream_kind == "main" and u.kind in RUNNING | {
        "heading_candidate", "caption", "figure_text", "table_text"}]  # fmt: skip
    return (main[-1] if main else None), (main[0] if main else None)


def page_join(previous, following, vocabulary, segmenter_factory):
    """PageJoin, or (None, candidate record) for two consecutive pages.

    ``previous``/``following``: (page, layout, units). ``segmenter_factory(page, layout)``
    returns a PageSegmenter for hyphen decisions on the following page's text.
    """
    page_a, layout_a, units_a = previous
    page_b, layout_b, units_b = following
    last, _ = edge_units(units_a)
    _, first = edge_units(units_b)
    if last is None or first is None:
        return None, None
    a_id, b_id = last.line_ids[-1], first.line_ids[0]
    a_text, b_text = _text(page_a, layout_a, a_id), _text(page_b, layout_b, b_id)
    region_a = {lid: r.type for r in layout_a.regions for lid in r.line_ids}[a_id]
    region_b = {lid: r.type for r in layout_b.regions for lid in r.line_ids}[b_id]
    cont = continuation(
        a_text, b_text, previous_type=region_a, following_type=region_b, vocabulary=vocabulary
    )
    indented = "first-line indent" in first.boundary.reasons
    entry = any("new entry" in reason for reason in first.boundary.reasons)
    candidate = {
        "from_page": page_a.geometry.page,
        "to_page": page_b.geometry.page,
        "from_unit_id": last.id,
        "to_unit_id": first.id,
        "verdict": cont.verdict,
        "score": cont.score,
        "kinds": f"{last.kind}->{first.kind}",
        "next_indented": indented,
    }
    style_a = segmenter_factory(page_a, layout_a).lines[a_id].style
    style_b = segmenter_factory(page_b, layout_b).lines[b_id].style
    same_style = style_a[:2] == style_b[:2]
    candidate["same_style"] = same_style
    running = last.kind == first.kind and last.kind in RUNNING
    if not (running and same_style and cont.verdict == "continues" and not indented and not entry):
        candidate["joined"] = False
        candidate["review_required"] = running and cont.verdict == "neutral" and not indented
        return None, candidate
    hyphen = None
    if cont.features.get("previous_end") == "hyphen":
        # Decide the break hyphen with the same rule as within a page, on both pages' text.
        segmenter = segmenter_factory(page_a, layout_a)
        hyphen = segmenter.hyphen(segmenter.lines[a_id], b_text)
    confidence = round(min(0.95, 0.55 + 0.5 * cont.score), 4)
    join = LineJoin(
        previous_line_id=a_id,
        next_line_id=b_id,
        kind="page",
        confidence=confidence,
        reasons=["paragraph continues on the next page", *cont.reasons],
        hyphen=hyphen,
        review_required=confidence < REVIEW_BELOW,
    )
    candidate["joined"] = True
    return (
        PageJoin(
            from_page=page_a.geometry.page,
            from_unit_id=last.id,
            to_page=page_b.geometry.page,
            to_unit_id=first.id,
            join=join,
            evidence={"verdict": cont.verdict, "score": cont.score},
        ),
        candidate,
    )
