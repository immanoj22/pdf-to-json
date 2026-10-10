"""Float anchors moved from the Step 7 line centre to a paragraph boundary.

A Step 7 float is anchored after a main-flow line. When that line lies inside a main-flow
unit, the anchor moves to the unit's nearest boundary (before its first line or after its
last line, by line count; ties go to the end, the reference convention of reading a float
after the paragraph it interrupts). Anchors never split a unit. The original anchor is kept
as evidence (AnchorMove) and the order's anchor and anchored_after edge are rewritten.
"""

from __future__ import annotations

from book_core.paragraphs.models import AnchorMove
from book_core.reading_order.models import PAGE_START, Anchor, PageReadingOrder

RULES = ("nearest", "end")


def move_anchors(order, units, rule="nearest", min_join_confidence=0.0, max_lines=None):
    """(new order, moves). ``rule``: nearest boundary, or always the end of the unit.

    An anchor moves only across joins of at least ``min_join_confidence``: a weak join may
    hide a paragraph boundary, and moving across it would carry the float into another
    paragraph. Such anchors stay at the Step 7 position, as do anchors farther than
    ``max_lines`` lines from the boundary (a long stretch is likelier to hide one).
    """
    if rule not in RULES:
        raise ValueError(f"Unknown anchor rule {rule}")
    main = order.main.line_ids
    index = {lid: i for i, lid in enumerate(main)}
    unit_of = {lid: u for u in units if u.stream_kind == "main" for lid in u.line_ids}
    streams, moves = [], []
    edges = [e for e in order.edges if e.kind != "anchored_after"]
    for stream in order.streams:
        anchor = stream.anchor
        if anchor is None or anchor.after_line_id is None:
            streams.append(stream)
            if anchor is not None:
                edges.append(_edge(order, stream, None))
            continue
        unit = unit_of.get(anchor.after_line_id)
        target = anchor.after_line_id
        if unit is not None and len(unit.line_ids) > 1:
            lines = [lid for lid in unit.line_ids if lid in index]
            first, last = index[lines[0]], index[lines[-1]]
            here = index[anchor.after_line_id]
            if here != last:
                before = here - first + 1  # lines to step back to the unit start
                after = last - here  # lines to step forward to the unit end
                if rule == "end" or after <= before:
                    target = main[last]
                    crossed = main[here : last + 1]
                else:
                    target = main[first - 1] if first > 0 else None
                    crossed = main[first : here + 1]
                strength = {(j.previous_line_id, j.next_line_id): j.confidence for j in unit.joins}
                weakest = min(
                    (strength.get(pair, 1.0) for pair in zip(crossed, crossed[1:], strict=False)),
                    default=1.0,
                )
                too_far = max_lines is not None and len(crossed) - 1 > max_lines
                if weakest < min_join_confidence or too_far:
                    target = anchor.after_line_id
        if target != anchor.after_line_id:
            position = index[target] if target is not None else -1
            moves.append(
                AnchorMove(
                    stream_id=stream.id,
                    original_after_line_id=anchor.after_line_id,
                    original_position=anchor.position,
                    after_line_id=target,
                    position=position,
                    unit_id=unit.id,
                    rule=rule,
                    reasons=[
                        "Step 7 anchor fell inside a paragraph unit",
                        "moved to the unit end"
                        if target == unit.line_ids[-1]
                        else "moved to the unit start",
                    ],
                )
            )
            anchor = Anchor(
                after_line_id=target,
                position=position,
                order=anchor.order,
                mode=anchor.mode if target is not None else "page_start",
                confidence=anchor.confidence,
                reasons=[*anchor.reasons, "moved to a paragraph boundary"],
                review_required=anchor.review_required,
            )
            stream = stream.model_copy(update={"anchor": anchor})
        streams.append(stream)
        edges.append(_edge(order, stream, stream.anchor.after_line_id))
    # Floats sharing an anchor keep a dense 0..n order in their original sequence.
    counts = {}
    final = []
    for stream in streams:
        if stream.anchor is not None:
            key = stream.anchor.position
            anchor = stream.anchor.model_copy(update={"order": counts.get(key, 0)})
            counts[key] = counts.get(key, 0) + 1
            stream = stream.model_copy(update={"anchor": anchor})
        final.append(stream)
    data = order.model_copy(update={"streams": final, "edges": edges}).model_dump()
    return PageReadingOrder.model_validate(data), moves


def _edge(order, stream, target):
    original = next(
        e for e in order.edges if e.kind == "anchored_after" and e.source == f"stream:{stream.id}"
    )
    return original.model_copy(update={"target": target or PAGE_START})
