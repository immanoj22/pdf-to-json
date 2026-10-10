"""One page's paragraphs: units, inline runs, languages and anchors at paragraph boundaries."""

from __future__ import annotations

from book_core.model.common import Provenance
from book_core.paragraphs.anchors import move_anchors
from book_core.paragraphs.inline import language_runs, style_runs
from book_core.paragraphs.models import TEXT_KINDS, PageParagraphs
from book_core.paragraphs.segment import PageSegmenter

PARAGRAPHS_VERSION = "paragraphs-1"


def build_page(
    page,
    layout,
    furniture,
    profile,
    vocabulary=None,
    navigation=None,
    detector=None,
    anchor_rule="keep",
    resolved_device="cpu",
):
    """PageParagraphs for one page from its Step 4 layout and Step 8 page furniture."""
    segmenter = PageSegmenter(
        page, layout, furniture, profile, vocabulary, profile.get("compounds"), navigation
    )
    units = segmenter.units()
    lines = {line.id: line for line in layout.lines}
    enriched = []
    for unit in units:
        if unit.kind not in TEXT_KINDS:
            enriched.append(unit)
            continue
        members = [lines[lid] for lid in unit.line_ids]
        language, confidence, runs = language_runs(page.store, members, detector)
        enriched.append(
            unit.model_copy(
                update={
                    "style_runs": style_runs(page.store, members),
                    "language": language,
                    "language_confidence": round(confidence, 6),
                    "language_runs": runs,
                }
            )
        )
    # Paragraph-boundary anchors are always computed; "keep" records them as proposals and
    # leaves the Step 7/8 anchors in the order (the reading-order gate decides the default).
    proposal = "nearest" if anchor_rule == "keep" else anchor_rule
    moved, moves = move_anchors(furniture.order, enriched, proposal)
    if anchor_rule == "keep":
        order = furniture.order
        moves = [move.model_copy(update={"applied": False}) for move in moves]
    else:
        order = moved
    return PageParagraphs(
        source_sha256=layout.source_sha256,
        page=layout.page,
        paragraphs_version=PARAGRAPHS_VERSION,
        units=enriched,
        order=order,
        anchor_moves=moves,
        provenance=Provenance(
            source_sha256=layout.source_sha256,
            engine="book_core.paragraphs",
            engine_version=PARAGRAPHS_VERSION,
            method="derived",
            resolved_device=resolved_device,
            notes=[f"float anchors: {anchor_rule} paragraph boundary"],
        ),
    )
