"""Styled units that are not headings: display titles and labels (whole-book consistency).

Heading detection finds every visually distinct title. Which of them are navigational
headings is a whole-book decision:

- **Display titles.** When the book's own table of contents links its numbered sections
  (at least ``contents_min_links`` links, covering at least ``contents_coverage`` of the
  prominent numbered body headings), the contents define the outline. A body title that is
  not numbered, not linked from the contents, not on a section-opener page and not attached
  (a box or once-per-section feature title) is a display title of its section's running
  text. Books without such contents keep every title as a heading. ``outline`` = "all" in
  the configuration keeps them as headings (a client profile may choose that).
- **Protected titles.** Numbered or contents-linked headings, a title that recurs once per
  section, a title more prominent than every contents-linked heading (a part or unit opener
  title) and any title in a style group whose members are mostly numbered or linked headings
  (at least ``repeated_pages`` of them) stay headings.
- **Labels.** A capitalised title set no larger than the body, without once-per-section
  evidence, contents link or numbering, and not opening a box, is a label of the text
  ("SOURCE: SPEECH"), unless it is a title of the running text set apart by space on both
  sides and not recurring (a section heading at body size). Small labels that form a
  repeated section template (several step labels recurring together once per section) are
  labels too.
- **Recurring titles** are protected only when the book has no contents outline or one of
  their occurrences is linked from the contents; otherwise they are in-section titles.

Both keep their style evidence and unit references; they are not headings and take no level.
"""

from __future__ import annotations

from collections import Counter

from book_core.structure.models import REVIEW_BELOW, StyledText

BOX_STREAMS = frozenset({"sidebar", "callout", "card", "note"})


def contents_outline(items, zone_of, config):
    """(reliable?, evidence) for using the contents as the outline."""
    numbered = [i for i in items if i["numbered"] and not i["attached"]
                and zone_of.get(i["page"]) == "body" and i["prominence"][0] >= 1]  # fmt: skip
    linked = [i for i in numbered if i["toc_level"] is not None]
    all_linked = [i for i in items if i["toc_level"] is not None]
    coverage = len(linked) / len(numbered) if numbered else 0.0
    reliable = (
        config["outline"] == "contents"
        and len(all_linked) >= config["contents_min_links"]
        and coverage >= config["contents_coverage"]
    )
    return reliable, {
        "contents_links": len(all_linked),
        "numbered_body_headings": len(numbered),
        "numbered_linked_share": round(coverage, 3),
        "contents_outline": reliable,
    }


def annotate(items, zone_of, openers, navigation, config):
    """Rule verdict per candidate: ``rule_role`` (None = heading, "label", "display_title"),
    ``rule_why`` and ``protected``. Returns (profile, top contents-linked prominence)."""
    reliable, profile = contents_outline(items, zone_of, config)
    spine_groups = Counter(i["style_group"] for i in items
                           if i["numbered"] or i["toc_level"] is not None)  # fmt: skip
    spine_pages = {(i["style_group"], i["page"]) for i in items
                   if i["numbered"] or i["toc_level"] is not None}  # fmt: skip
    group_sizes = Counter(i["style_group"] for i in items)
    heading_styles = {g for g, n in spine_groups.items()
                      if n >= config["repeated_pages"] and n * 2 >= group_sizes[g]}  # fmt: skip
    linked = [i["prominence"] for i in items if i["toc_level"] is not None]
    top_linked = max(linked) if linked else None
    # Recurring titles whose class (text and style) has a contents-linked member sit at the
    # contents depth; other recurring titles are in-section titles of a contents outline.
    linked_classes = {_recurring_class(i) for i in items if i["toc_level"] is not None}
    for item in items:
        spine = item["numbered"] or item["toc_level"] is not None
        zone = zone_of.get(item["page"], "body")
        recurring = bool(item.get("recurring_title")) and (
            not reliable or _recurring_class(item) in linked_classes
        )
        # "More prominent than any contents-linked heading" marks an opener title (a part or
        # unit title); inside a section's pages it is a display title set large.
        opener_title = (
            top_linked is not None
            and item["prominence"] > top_linked
            and (not reliable or item["page"] in openers or zone != "body")
        )
        protected = bool(
            spine
            or item.get("book_title")
            or item["run_in"] is not None
            or recurring
            or opener_title
            or item["style_group"] in heading_styles
        )
        nearby = any((item["style_group"], item["page"] + d) in spine_pages for d in (-1, 0, 1))
        box_title = item["stream"] in BOX_STREAMS and item["position"] == 0
        role, why = None, None
        divider = (item["numbering"] or {}).get("kind") == "letter"
        if (item["page"] in navigation and not spine and not divider
                and not item.get("book_title") and not item.get("list_title")):  # fmt: skip
            role, why = "label", "styled line of a printed list page"
        elif item.get("template_step") and not spine:
            role, why = "label", "step label of a section template repeated in many sections"
        elif (not protected and not nearby and not item.get("feature") and not box_title
                and item["prominence"][0] <= 0 and item["prominence"][2]
                and item["tokens"] <= 8 and not _isolated_title(item, config)):  # fmt: skip
            role = "label"
            why = "capitalised label no larger than the body, no once-per-section evidence"
        elif (reliable and not protected and not item["attached"] and zone == "body"
              and item["page"] not in openers):  # fmt: skip
            role = "display_title"
            why = "title inside a section: not numbered and not in the table of contents"
        item["rule_role"], item["rule_why"], item["protected"] = role, why, protected
    profile["top_linked_prominence"] = ":".join(map(str, top_linked)) if top_linked else None
    return profile, top_linked


def _recurring_class(item):
    return item["first_unit"]["repeat_key"], item["style_group"]


def _isolated_title(item, config):
    """A capitalised title of the running text set apart on both sides and not a recurring
    label: a section heading set at body size (common in academic books), not a label."""
    first, last = item["first_unit"], item.get("last_unit") or item["first_unit"]
    before, after = first.get("gap_before"), last.get("gap_after")
    return (
        item["stream"] == "main"
        and (item["repeated"] < config["repeated_pages"] or item.get("section_title"))
        and (before is None or before >= config["isolation_fonts"])
        and after is not None
        and after >= config["isolation_fonts"]
    )


def styled_text(item, role, why, source_id):
    confidence = round(min(0.95, 0.5 + 0.3 * item["detection_confidence"]), 4)
    if item.get("classifier_likelihood") is not None:
        confidence = round(min(0.97, 0.5 + abs(0.5 - item["classifier_likelihood"])), 4)
    return StyledText(
        id=source_id(item["id"]), page=item["page"], unit_ids=item["units"], role=role,
        style_group=item["style_group"], confidence=confidence,
        reasons=[why, *item["reasons"][:5]],
        evidence={"score": item["score"], "prominence": ":".join(map(str, item["prominence"])),
                  "classifier_likelihood": item.get("classifier_likelihood")},
        review_required=confidence < REVIEW_BELOW,
    )  # fmt: skip
