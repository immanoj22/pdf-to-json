"""Heading levels and roles from a whole-book hierarchy.

Every heading has a prominence: its style group's rank (size step relative to the body, then
weight, then capitals; ``structure.styles``) of its most prominent unit. Headings are read in
book order with a stack of open sections:

- a **structural** heading closes every open section that is not more prominent than itself
  and opens one level below the remaining one, so a level never skips going down and equal
  prominence means siblings;
- a table-of-contents level is consistency evidence: headings linked to entries of the same
  contents level and the same style group share one level (the first one decided);
- numbering depth ("1.2.3") nests below its parent number when both are present;
- a section opened by a sectioning word of part, unit or chapter rank closes only at a word of
  equal or higher rank (or a new book part), whatever the size of the headings inside it;
- the numbered or contents-linked headings form the spine: an unnumbered, unlinked heading
  never closes a spine section, however large it is set (a display title inside a lesson);
- each front and rear section of the book starts a fresh stack (its title is level 1), as
  does each body block in its own label series;
- an **attached** title (a sidebar, box or recurring feature title) does not open a section:
  it takes the level of the innermost numbered or contents-linked section that contains it
  (boxes belong to the numbered section, not to the visual subsection they sit beside);
- the book title is level 1 and contains no section.

Roles: attached titles are ``sidebar_title`` (inside a float or box stream) or
``feature_title`` (a recurring label in the running text). Structural headings take the
zone's title role in front and rear matter (level 1), otherwise a role from numbering
evidence (part, unit, chapter, lesson, section) shared by their level, falling back to
chapter, section, subsection by depth below the outermost body level. The book title is the
most prominent heading of the front matter's title page.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from book_core.structure.models import REVIEW_BELOW

FLOAT_STREAMS = frozenset({"sidebar", "callout", "card", "note", "figure", "table", "credit"})
ROLE_ORDER = ("part", "unit", "chapter", "lesson", "section", "subsection")


def assign(items, sections_of_page, zone_of_page, config):
    """Set ``level``, ``level_method``, ``role`` and level evidence on heading ``items``.

    ``items``: dicts in book order with id, page, stream, prominence (tuple), attached (bool),
    numbering (dict or None), toc_level, toc_group (style group), repeated (pages).
    """
    stack = []  # [(prominence, level, numbering depth, spine, keyword rank)]
    section = None
    group_level = {}
    for item in items:
        page_section = sections_of_page.get(item["page"])
        if page_section != section:
            stack = []
            section = page_section
        zone = zone_of_page.get(item["page"], "body")
        if item.get("book_title"):
            item["level"], item["level_method"] = 1, "zone"
            item["level_reasons"] = ["book title: level 1, contains no section"]
            continue
        if item["attached"]:
            spine = [entry for entry in stack if entry[3]]
            depth = (spine or stack)[-1][1] if stack else 1
            item["level"], item["level_method"] = max(1, depth), "attached"
            item["level_reasons"] = [
                "attached title: level of the innermost numbered or contents-linked section"
            ]
            continue
        prominence = item["prominence"]
        spine = bool(item.get("spine"))
        number_depth = (item["numbering"] or {}).get("depth") if item["numbering"] else None
        rank = _keyword_rank(item)
        while stack:
            top = stack[-1]
            nests = number_depth and top[2] and top[2] < number_depth and top[0] == prominence
            if top[4] is not None and (rank is None or rank > top[4]):
                break  # a part/unit/chapter section closes only at an equal or higher word
            if rank is not None and (top[4] is None or rank <= top[4]):
                stack.pop()
            elif spine and not top[3] and not nests:
                stack.pop()  # a numbered section closes the unnumbered ones inside its parent
            elif top[0] <= prominence and not nests and not (top[3] and not spine):
                stack.pop()
            else:
                break
        level = len(stack) + 1
        method, reasons = "style_rank", ["prominence relative to the open sections"]
        if number_depth and number_depth > 1 and stack and stack[-1][2]:
            method, reasons = "numbering", [f"numbering depth {number_depth}"]
        key = (item.get("toc_level"), item.get("style_group"))
        if item.get("toc_level") is not None:
            if key in group_level and group_level[key] <= len(stack) + 1:
                level = group_level[key]
                del stack[level - 1 :]
                method = "navigation"
                reasons = ["same contents level and style as earlier linked headings"]
            else:
                group_level.setdefault(key, level)
        if not stack and zone in {"front", "rear"}:
            method = "zone" if method == "style_rank" else method
            reasons = [*reasons, f"{zone} matter section starts at level 1"]
        item["level"], item["level_method"], item["level_reasons"] = level, method, reasons
        stack.append((prominence, level, number_depth, spine, rank))
    _roles(items, zone_of_page)
    _confidence(items)


def _keyword_rank(item):
    """Rank of a sectioning word ("Part" 0 < "Unit" 1 < "Chapter" 2), or None."""
    marker = item.get("numbering") or {}
    hint = marker.get("role_hint") if marker.get("kind") == "keyword" else None
    return ROLE_ORDER.index(hint) if hint in {"part", "unit", "chapter"} else None


def _roles(items, zone_of_page):
    hints = defaultdict(Counter)
    for item in items:
        if not item["attached"] and zone_of_page.get(item["page"]) == "body":
            hint = (item["numbering"] or {}).get("role_hint")
            if hint:
                hints[item["level"]][hint] += 1
    level_role = {}
    used = set()
    for level in sorted(hints):
        role = hints[level].most_common(1)[0][0]
        level_role[level] = role
        used.add(role)
    body_levels = sorted({i["level"] for i in items if not i["attached"]
                          and zone_of_page.get(i["page"]) == "body"})  # fmt: skip
    for level in body_levels:
        if level in level_role:
            continue
        above = [level_role[lv] for lv in level_role if lv < level]
        start = max((ROLE_ORDER.index(r) for r in above), default=ROLE_ORDER.index("unit"))
        fallback = ("chapter", "section", "subsection")
        candidates = [r for r in ROLE_ORDER[start + 1 :] if r in fallback and r not in used]
        role = candidates[0] if candidates else "subsection"
        level_role[level] = role
        used.add(role)
    for item in items:
        zone = zone_of_page.get(item["page"], "body")
        if item["attached"]:
            item["role"] = "sidebar_title" if item["stream"] in FLOAT_STREAMS else "feature_title"
        elif item.get("book_title"):
            item["role"] = "book_title"
        elif zone in {"front", "rear"}:
            item["role"] = f"{zone}_section_title" if item["level"] == 1 else "subsection"
        else:
            item["role"] = level_role.get(item["level"], "subsection")


def _confidence(items):
    for item in items:
        base = item["detection_confidence"]
        penalty = 0.0
        if item["level_method"] == "style_rank" and item["level"] > 3:
            penalty += 0.1  # deep style-only levels are weaker evidence
        item["confidence"] = round(max(0.05, base - penalty), 4)
        item["review_required"] = item["confidence"] < REVIEW_BELOW
