"""Figures of one page from the layout and the final units and reading order.

One figure per layout figure region: the layout already groups raster images, vector
artwork and figure panels within a page-relative gap into one block and merges overlapping
blocks (a composite is one figure); separate blocks stay separate figures. The figure's
float stream holds, in reading order, its captions, embedded labels and credits; each unit
of that stream is linked to the figure by the region its lines belong to. Captions that the
reading order could not attach stay text and are listed as unlinked with a reason.

A figure without a stream of its own (no text, or read inside a callout) is anchored where
its container is read: the callout stream holding the region's scope, or the main-flow line
whose block-axis centre last precedes the figure's centre in the same scope.
"""

import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import regex

from book_core.figures.models import FigureAnchor, Link, UnlinkedCaption
from book_core.model.common import BBox

CAPTION, CREDIT, INTERNAL = "caption", "credit", "internal"
ROLE_OF_REGION = {
    "caption_candidate": CAPTION,
    "credit_candidate": CREDIT,
    "figure": INTERNAL,
    "unknown": CREDIT,  # rotated unknown text the reading order attached; stays under review
}
RULES = {
    CAPTION: "caption region attached to the figure by the reading order",
    CREDIT: "credit region within the credit reach of the figure edge",
    INTERNAL: "text inside the figure region (embedded label)",
}
CAPTION_GAP = 2.0  # font sizes; the reading-order caption rule's gap
CAPTION_BOX_LINES = 8  # the layout's caption-candidate line limit
CAPTION_BOX_WITHIN = 0.9  # share of the box's own extent inside the figure's span
CAPTION_BOX = "caption box (callout) adjacent to the figure; read where the box is read"
PAGE_CREDIT_ONE = "credit line on a page with one figure; no figure within credit reach"
PAGE_CREDIT_MANY = (
    "page-level credit line; no figure within credit reach; linked to every figure of the "
    "page; review"
)
REVIEWED_UNKNOWN = "unknown rotated text beside the figure; attached for review, role unknown"


@dataclass
class Draft:
    region: object
    block: object | None
    stream: object | None
    anchor: FigureAnchor | None = None
    captions: list = field(default_factory=list)
    credits: list = field(default_factory=list)
    internal: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)


def _block_of(region, blocks):
    ids = set(region.object_ids)
    for block in blocks:
        if block.kind == "figure" and (set(block.object_ids) == ids or block.bbox == region.bbox):
            return block
    return None


def _link(unit, role, region_of, confidence):
    regions = Counter(region_of[lid].type for lid in unit.line_ids)
    review = "unknown" in regions or unit.review_required
    rule = REVIEWED_UNKNOWN if role == CREDIT and "unknown" in regions else RULES[role]
    return Link(
        unit_id=unit.id,
        line_ids=list(unit.line_ids),
        rule=rule,
        confidence=0.55 if review else confidence,
        review_required=review,
    )


def link_page(layout, built):
    """(drafts in reading order, unlinked captions). ``built``: the page's final units/order."""
    region_of = {lid: r for r in layout.regions for lid in r.line_ids}
    figures = [r for r in layout.regions if r.type == "figure"]
    stream_of_region = {rid: s for s in built.order.streams for rid in s.region_ids}
    stream_of_line = {lid: s for s in built.order.streams for lid in s.line_ids}
    main = built.order.main.line_ids
    drafts = {}
    for region in figures:
        stream = stream_of_region.get(region.id)
        if stream is not None and stream.kind != "figure":
            stream = None
        drafts[region.id] = Draft(region, _block_of(region, layout.blocks), stream)
    # The order's typed edges name the figure region each attached line belongs to.
    figure_of_line = {}
    for edge in built.order.edges:
        if edge.kind in {"caption_of", "belongs_to_figure"} and edge.target.startswith("region:"):
            target = edge.target.removeprefix("region:")
            if target in drafts:
                figure_of_line[edge.source] = target
    unlinked = []
    for unit in built.units:
        stream = stream_of_line[unit.line_ids[0]]
        targets = Counter(figure_of_line.get(lid) for lid in unit.line_ids)
        target, _ = targets.most_common(1)[0]
        if target is None and len(targets) > 1:
            target = next(t for t in targets if t is not None)
        if target is None:
            if unit.kind == "caption":
                unlinked.append(
                    UnlinkedCaption(
                        unit_id=unit.id,
                        line_ids=list(unit.line_ids),
                        reason="caption candidate not attached to a figure or table; read in "
                        f"the {stream.kind} stream; review",
                    )
                )
            continue
        draft = drafts[target]
        roles = Counter(ROLE_OF_REGION.get(region_of[lid].type) for lid in unit.line_ids)
        role, _ = roles.most_common(1)[0]
        if role is None:
            role = CAPTION if unit.kind == "caption" else INTERNAL
        link = _link(unit, role, region_of, 0.8 if role != CREDIT else 0.75)
        if len(roles) > 1 or len(targets) > 1:
            link = link.model_copy(update={"review_required": True})
            draft.flags.append(f"unit {unit.id[:12]} mixes figure roles or figures")
        {CAPTION: draft.captions, CREDIT: draft.credits, INTERNAL: draft.internal}[role].append(
            link
        )
    _caption_boxes(drafts, unlinked, layout, built)
    _page_credits(drafts, layout, built, region_of)
    ordered = []
    for draft in drafts.values():
        draft.anchor, reason = _anchor(draft, built.order, main, layout, stream_of_line)
        draft.reasons.append(reason)
        ordered.append(draft)
    ordered.sort(key=lambda d: (d.anchor.position, d.anchor.order, _native(d, layout)))
    for index, draft in enumerate(ordered, 1):
        draft.anchor = draft.anchor.model_copy(update={"reading_index": index})
    return ordered, unlinked


def _native(draft, layout):
    return next(i for i, r in enumerate(layout.regions) if r.id == draft.region.id)


def _anchor(draft, order, main, layout, stream_of_line):
    stream = draft.stream
    if stream is not None and stream.anchor is not None:
        a = stream.anchor
        return (
            FigureAnchor(
                stream_id=stream.id,
                after_line_id=a.after_line_id,
                position=a.position,
                order=a.order,
                reading_index=1,
            ),
            "anchored where its float stream is read",
        )
    region = draft.region
    container = next(
        (
            s
            for s in order.streams
            if s.anchor is not None and s.kind in {"callout", "sidebar"}
            and _inside_stream(region, s, layout)
        ),
        None,
    )  # fmt: skip
    if container is not None:
        a = container.anchor
        return (
            FigureAnchor(
                stream_id=container.id,
                after_line_id=a.after_line_id,
                position=a.position,
                order=a.order,
                reading_index=1,
            ),
            "read inside its container's stream",
        )
    lines = {line.id: line for line in layout.lines}
    scope_of = {lid: r.scope_id for r in layout.regions for lid in r.line_ids}
    centre = (region.bbox.y0 + region.bbox.y1) / 2
    before = [
        i
        for i, lid in enumerate(main)
        if (lines[lid].bbox.y0 + lines[lid].bbox.y1) / 2 <= centre
        and scope_of[lid] == region.scope_id
    ]
    position = before[-1] if before else -1
    return (
        FigureAnchor(
            stream_id=order.main.id,
            after_line_id=main[position] if position >= 0 else None,
            position=position,
            order=0,
            reading_index=1,
        ),
        "no float stream; anchored after the main-flow line before the figure centre",
    )


def _inside_stream(region, stream, layout):
    boxes = [r.bbox for r in layout.regions if r.id in stream.region_ids]
    cx = (region.bbox.x0 + region.bbox.x1) / 2
    cy = (region.bbox.y0 + region.bbox.y1) / 2
    return any(b.x0 <= cx <= b.x1 and b.y0 <= cy <= b.y1 for b in boxes)


def _linked(drafts):
    return {
        link.unit_id for d in drafts.values() for link in (*d.captions, *d.credits, *d.internal)
    }


def _gap_and_share(a, b):
    """Gap between two boxes and their shared extent across the gap (share of the smaller)."""
    dx = max(b.x0 - a.x1, a.x0 - b.x1, 0.0)
    dy = max(b.y0 - a.y1, a.y0 - b.y1, 0.0)
    if dy >= dx:
        width = min(a.x1 - a.x0, b.x1 - b.x0)
        share = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) / width if width > 0 else 0.0
    else:
        height = min(a.y1 - a.y0, b.y1 - b.y0)
        share = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0)) / height if height > 0 else 0.0
    return max(dx, dy), share


def _within_span(box, figure):
    """Share of the box's own extent, across the gap, that lies inside the figure's span.

    A caption box sits under, over or beside its figure; a page-wide band (a running-head
    strip, a competency or table header) reaches far beyond the figure and is not one.
    """
    dx = max(figure.x0 - box.x1, box.x0 - figure.x1, 0.0)
    dy = max(figure.y0 - box.y1, box.y0 - figure.y1, 0.0)
    if dy >= dx:
        extent, inside = box.x1 - box.x0, min(box.x1, figure.x1) - max(box.x0, figure.x0)
    else:
        extent, inside = box.y1 - box.y0, min(box.y1, figure.y1) - max(box.y0, figure.y0)
    return max(0.0, inside) / extent if extent > 0 else 0.0


def _caption_boxes(drafts, unlinked, layout, built):
    """A short callout of caption or paragraph text next to a figure, within its span, is its
    caption box."""
    if not drafts:
        return
    linked = _linked(drafts)
    regions = {r.id: r for r in layout.regions}
    lines = {line.id: line for line in layout.lines}
    for stream in built.order.streams:
        if stream.kind not in {"callout", "sidebar"} or not stream.line_ids:
            continue
        box = next((regions[r] for r in stream.region_ids if regions[r].type in
                    {"callout", "sidebar"}), None)  # fmt: skip
        units = [u for u in built.units if u.line_ids[0] in set(stream.line_ids)]
        if (
            box is None
            or not units
            or any(u.id in linked or u.kind not in {"paragraph", "caption"} for u in units)
            or len(stream.line_ids) > CAPTION_BOX_LINES
        ):
            continue
        sizes = sorted(lines[lid].font_size for lid in stream.line_ids)
        font = sizes[len(sizes) // 2] or 1.0
        best = None
        for draft in drafts.values():
            gap, _ = _gap_and_share(box.bbox, draft.region.bbox)
            within = _within_span(box.bbox, draft.region.bbox)
            if (
                gap <= CAPTION_GAP * font
                and within >= CAPTION_BOX_WITHIN
                and (best is None or gap < best[0])
            ):
                best = (gap, draft)
        if best is None:
            continue
        for unit in units:
            best[1].captions.append(
                Link(unit_id=unit.id, line_ids=list(unit.line_ids), rule=CAPTION_BOX,
                     confidence=0.65)
            )  # fmt: skip
        ids = {u.id for u in units}
        unlinked[:] = [c for c in unlinked if c.unit_id not in ids]


def _page_credits(drafts, layout, built, region_of):
    """Credit lines the reading order kept apart (no figure within reach) still credit the
    page's figures: the only figure, or every figure of the page under review."""
    if not drafts:
        return
    linked = _linked(drafts)
    for unit in built.units:
        if unit.id in linked:
            continue
        if not all(region_of[lid].type == "credit_candidate" for lid in unit.line_ids):
            continue
        many = len(drafts) > 1
        for draft in drafts.values():
            draft.credits.append(
                Link(unit_id=unit.id, line_ids=list(unit.line_ids),
                     rule=PAGE_CREDIT_MANY if many else PAGE_CREDIT_ONE,
                     confidence=0.5 if many else 0.6, review_required=many)
            )  # fmt: skip


# The label opens the text: "(Fig. 2)" inside a sentence is a cross-reference, not a caption.
NUMBERED = regex.compile(r"^\s*(\p{L}+)\.?\s*\p{N}")
NUMBERED_CAPTION = "starts with the book's caption label and a number; nearest figure on the page"
NOT_CAPTIONS = {"heading_candidate", "running_head", "running_foot", "folio", "production_mark",
                "artifact", "invisible", "table_text", "contents_entry", "index_entry"}  # fmt: skip


def opening(store, layout, unit, size=48):
    """NFKC text at the start of a unit (evidence only; never stored as content)."""
    lines = {line.id: line for line in layout.lines}
    text = "".join(store.spans[s].raw_text for s in lines[unit.line_ids[0]].span_ids)
    return unicodedata.normalize("NFKC", text)[:size]


def caption_label(text):
    """The word before a number at the start of a text ("Fig. 3.2" -> "fig"), casefolded."""
    match = NUMBERED.match(text)
    return match.group(1).casefold() if match else None


def label_votes(drafts, store, layout, built):
    """Leading label words of the captions the reading order linked on this page."""
    units = {u.id: u for u in built.units}
    votes = Counter()
    for draft in drafts:
        for link in draft.captions:
            if link.rule == RULES[CAPTION]:
                label = caption_label(opening(store, layout, units[link.unit_id]))
                votes[label] += 1
    return votes


def numbered_candidates(drafts, store, layout, built):
    """Short unlinked text units of a page with figures: (unit, label word, box)."""
    if not drafts:
        return []
    linked = _linked({d.region.id: d for d in drafts})
    lines = {line.id: line for line in layout.lines}
    found = []
    for unit in built.units:
        if unit.id in linked or unit.kind in NOT_CAPTIONS:
            continue
        if len(unit.line_ids) > CAPTION_BOX_LINES:
            continue
        label = caption_label(opening(store, layout, unit))
        if label is None:
            continue
        boxes = [lines[lid].bbox for lid in unit.line_ids]
        box = BBox(
            x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
            x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
        )  # fmt: skip
        found.append((unit, label, box))
    return found


def link_numbered(drafts, unlinked, candidates, labels):
    """Link candidates opening with one of the book's caption labels to the nearest figure."""
    for unit, label, box in candidates:
        if label not in labels:
            continue
        draft = min(drafts, key=lambda d: _gap_and_share(box, d.region.bbox)[0])
        draft.captions.append(
            Link(unit_id=unit.id, line_ids=list(unit.line_ids), rule=NUMBERED_CAPTION,
                 confidence=0.7)
        )  # fmt: skip
        unlinked[:] = [c for c in unlinked if c.unit_id != unit.id]


UNSUPPORTED = (
    "caption candidate attached by the reading order in a book without caption numbering; "
    "not linked (geometry alone is not enough evidence); review"
)
UNNUMBERED = (
    "the book numbers its captions and this caption candidate does not open with the book's "
    "caption label and a number; not linked; review"
)


def caption_openings(drafts, store, layout, built):
    """{caption unit id: its leading label word or None} for the page's caption links."""
    units = {u.id: u for u in built.units}
    return {
        link.unit_id: caption_label(opening(store, layout, units[link.unit_id]))
        for draft in drafts
        for link in draft.captions
    }


def require_numbers(drafts, unlinked, openings, labels):
    """Caption links need evidence that holds across books (measured link precision):

    - a caption the reading order attached is linked only when the book numbers its captions
      and the caption opens with the book's label; in other books it stays unlinked;
    - a caption box is linked in a book without numbering; in a numbering book it needs the
      label as well;
    - a numbered caption always carries its label.
    Unlinked captions stay text and are listed with the reason, for review.
    """
    for draft in drafts:
        kept = []
        for link in draft.captions:
            numbered = openings.get(link.unit_id) in labels
            if link.rule == NUMBERED_CAPTION or numbered:
                kept.append(link)
                continue
            if link.rule == CAPTION_BOX and not labels:
                kept.append(link)
                continue
            reason = UNNUMBERED if labels else UNSUPPORTED
            unlinked.append(
                UnlinkedCaption(unit_id=link.unit_id, line_ids=link.line_ids, reason=reason)
            )
        draft.captions = kept


UNDECIDED_CREDIT = (
    "credit or source line; whether it credits a picture or quoted text is not decidable from "
    "layout; not linked; the figures its rule proposes are recorded; review"
)


def page_credits(drafts, record_id):
    """Move every credit link into page-level credit records with proposed figures.

    Measured on book 1 (Step 12): credit lines mix picture credits with citations for quoted
    text, so a figure-level link would be wrong too often; the proposal keeps the evidence.
    ``record_id(draft)`` gives the figure record id of a draft.
    """
    from book_core.figures.models import PageCredit

    proposals, rules, lines, confidence = {}, {}, {}, {}
    for draft in drafts:
        for link in draft.credits:
            proposals.setdefault(link.unit_id, []).append(record_id(draft))
            rules.setdefault(link.unit_id, link.rule)
            lines[link.unit_id] = link.line_ids
            confidence[link.unit_id] = min(confidence.get(link.unit_id, 1.0), link.confidence)
        draft.credits = []
    return [
        PageCredit(
            unit_id=unit,
            line_ids=lines[unit],
            proposed_figure_ids=sorted(set(proposals[unit])),
            rule=rules[unit],
            confidence=confidence[unit],
            reason=UNDECIDED_CREDIT,
        )
        for unit in proposals
    ]
