"""The unified review list: every item that needs a person, from every stage, in one place.

Sources: each published unit's review flags (structure, headings, OCR words and pages,
tables, MathML, figures, alt-text slots, captions and credits, footnotes, characters,
styling and language), inline math spans under review, continuity (uncertain joins, close
calls not joined, withdrawn joins), hidden text dropped from content, page labels.

Each item names the unit (when there is one), the page, the kind, the reason, the severity
(``must_check`` before ``needs_review``), a suggested action and, when the client profile
writes crops, the crop image of the region. Items are sorted for a reviewer: severity, then
page, then reading order.
"""

from __future__ import annotations

from collections import Counter

from book_core.assembly import schema as S
from book_core.extraction.fingerprints import stable_id

ACTIONS = {
    "ocr_word": "Compare the flagged words with the page image and correct the text.",
    "ocr_line": "Compare the OCR line with the page image and correct the text.",
    "ocr_page": "Check the whole page against the scan; OCR quality is low there.",
    "table": "Check the table's grid, header cells and cell text against the page.",
    "mathml": "Check the MathML against the page; correct it or keep the image fallback.",
    "figure": "Check the figure's extent and its caption and credit links.",
    "alt_text": "Write a description of the image (or check the prefilled one).",
    "caption": "Link the caption to its figure or table, or confirm it stands alone.",
    "credit": "Link the credit to its picture or quotation, or confirm it stands alone.",
    "footnote": "Check the note and the marker it belongs to.",
    "join": "Confirm whether the text continues across the break.",
    "hidden_text": "Confirm the dropped text is not visible on the page.",
    "structure": "Check where the unit starts and ends and what kind it is.",
    "heading": "Check whether this is a heading and its level.",
    "character": "Check the character against the page image.",
    "language": "Confirm the language of the text.",
    "style": "Check the bold and italic marking against the page.",
    "furniture": "Confirm the line is a running head, folio or page mark.",
    "page_label": "Confirm the printed page number of the page.",
    "names": "Check the parsed personal names.",
    "order": "Check where the box is read in the text.",
}
SEVERITY = {"must_check": 0, "needs_review": 1}


def _crop(profile, severity):
    mode = profile.review.crops
    return mode == "all" or (mode == "must_check" and severity == "must_check")


def review_list(content, ctx):
    rows, seen = [], set()
    order = {}
    units = list(S.iter_units(content))
    for unit in units:
        order[unit.id] = unit.order
        for severity, kind, reason in ctx.flag_rows.get(unit.id, []):
            rows.append((unit.id, unit.pages[0], kind, reason, severity,
                         unit.boxes[0] if unit.boxes else None))  # fmt: skip
        if isinstance(unit, S.BoxNode) and unit.review_status != "ok" and unit.flags:
            rows.append((unit.id, unit.pages[0], "order", unit.flags[0].split(": ", 1)[-1],
                         "needs_review", unit.boxes[0] if unit.boxes else None))  # fmt: skip
        if isinstance(unit, S.Figure):
            for text in unit.captions:
                if text.review_status != "ok":
                    rows.append(
                        (
                            unit.id,
                            unit.pages[0],
                            "caption",
                            "the caption's link to the figure is uncertain",
                            text.review_status,
                            unit.boxes[0] if unit.boxes else None,
                        )
                    )
        content_of = getattr(unit, "content", None)
        if isinstance(content_of, S.TextContent):
            for span in content_of.spans:
                if span.kind == "math" and span.review_status != "ok":
                    rows.append((unit.id, unit.pages[0], "mathml",
                                 "inline equation reading is uncertain", span.review_status,
                                 unit.boxes[0] if unit.boxes else None))  # fmt: skip
                elif span.kind == "language" and span.review_status != "ok":
                    rows.append(
                        (
                            unit.id,
                            unit.pages[0],
                            "language",
                            f"a passage read as language {span.language}",
                            span.review_status,
                            unit.boxes[0] if unit.boxes else None,
                        )
                    )
            for join in content_of.joins:
                if join.review_status != "ok":
                    rows.append(
                        (
                            unit.id,
                            unit.pages[0],
                            "structure",
                            "a hyphen or split-word decision is uncertain",
                            join.review_status,
                            unit.boxes[0] if unit.boxes else None,
                        )
                    )
    for furniture in ctx.furniture:
        if furniture.review_status != "ok":
            rows.append((furniture.id, furniture.page, "furniture", "furniture decision "
                         "below confidence", furniture.review_status,
                         furniture.boxes[0] if furniture.boxes else None))  # fmt: skip
    rows.extend(ctx.review)
    items = []
    for unit, page, kind, reason, severity, box in rows:
        key = (unit, page, kind, reason)
        if key in seen:
            continue
        seen.add(key)
        item_id = stable_id(unit or "", page, kind, reason)[:16]
        items.append(
            S.ReviewItem(
                id=item_id,
                unit=unit,
                page=page,
                kind=kind,
                reason=reason,
                severity=severity,
                action=ACTIONS.get(kind, "Check the item against the page."),
                crop=f"review/{item_id}.png" if _crop(ctx.profile, severity) else None,
                box=box,
            )
        )
    items.sort(key=lambda i: (SEVERITY[i.severity], i.page, order.get(i.unit, -1), i.kind,
                              i.id))  # fmt: skip
    counts = Counter(f"{i.severity}:{i.kind}" for i in items)
    return S.Review(counts=dict(sorted(counts.items())), items=items)
