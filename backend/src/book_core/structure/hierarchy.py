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
  equal or higher rank (or a new book part), whatever the size of the headings inside it; a
  sectioning word set smaller than an open numbered section is a heading inside it; a
  section or lesson word ranks too when the book shows it enclosing a ranked word (fewer of
  them, the first one opening before the first of the ranked word: "SECTION 2" holding
  chapters); otherwise it stays unranked;
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
    order = book_role_order(items, zone_of_page)
    section = None
    group_level = {}
    for item in items:
        zone = zone_of_page.get(item["page"], "body")
        # Front and rear sections start fresh stacks; body sections share one, so a part or
        # section opener can hold the chapters after it.
        page_section = (zone, None if zone == "body" else sections_of_page.get(item["page"]))
        if page_section != section:
            stack = []
            section = page_section
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
        rank = _keyword_rank(item, order)
        if rank is not None and any(entry[3] and entry[0] > prominence for entry in stack):
            # A sectioning word set smaller than an open numbered section ("PART I" inside a
            # chapter whose title is set larger) is a heading inside it, not a book part: it
            # nests by its prominence and gives no role hint.
            rank = None
            item["keyword_inside"] = True
        decimal_depth = (number_depth if number_depth and number_depth > 1
                         and (item["numbering"] or {}).get("kind") == "decimal" else None)
        if config.get("parted") and decimal_depth:
            # Under unit openers a decimal number sets the level by its depth, however large
            # the heading is set: N.N is the chapter inside the unit, N.N.N a section of it,
            # N.N.N.N one level lower; never a new chapter. It closes only the open headings
            # numbered at its own depth or deeper (and the unnumbered ones set after them).
            while stack and not (stack[-1][2] and stack[-1][2] < decimal_depth):
                if stack[-1][4] is not None:  # a unit/part opener stays open
                    break
                stack.pop()
        while stack and not (config.get("parted") and decimal_depth):
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
        if config.get("parted") and decimal_depth:
            level = min(decimal_depth, level)
            del stack[level - 1 :]
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
    _style_levels(items, zone_of_page)
    _roles(items, zone_of_page)
    _confidence(items)


STYLE_LEVEL_SHARE = 0.75  # share of a style's headings at one level that sets the others
STYLE_LEVEL_MIN = 5  # headings of one style needed before its usual level is trusted


def _style_levels(items, zone_of_page):
    """The same printed heading style is one heading level. Body headings placed by style
    alone (no numbering, contents link or sectioning word) take the level most headings of
    their style group have, when that level holds a clear majority: a chapter opener whose
    title is ranked lower than its first sections does not lift those sections to the
    chapter's level."""
    groups = defaultdict(list)
    for item in items:
        if (item["level_method"] == "style_rank" and not item["attached"]
                and zone_of_page.get(item["page"], "body") == "body"
                and _keyword_rank(item) is None):  # fmt: skip
            groups[item.get("style_group")].append(item)
    for group, members in groups.items():
        if group is None or len(members) < STYLE_LEVEL_MIN:
            continue
        level, count = Counter(m["level"] for m in members).most_common(1)[0]
        if count < STYLE_LEVEL_SHARE * len(members):
            continue
        for m in members:
            if m["level"] == level:
                continue
            before = m["level"]
            m["level"] = level
            if _skips(items):  # never a level that skips going down
                m["level"] = before
                continue
            m["level_reasons"] = [*m["level_reasons"],
                                  f"same printed style as {count} headings at level {level}"]


def _skips(items):
    """Whether a heading level skips when going down (the book structure's own rule)."""
    depth = 0
    for item in items:
        if item["level"] > depth + 1:
            return True
        if not item["attached"]:
            depth = item["level"]
    return False


RANKED = ("part", "unit", "chapter")


def book_role_order(items, zone_of_page):
    """Sectioning roles from outermost to innermost: part, unit, chapter, preceded by a section
    or lesson word the book shows enclosing one of them (fewer occurrences, first opened
    earlier)."""
    seen, first = Counter(), {}
    for index, item in enumerate(items):
        marker = item.get("numbering") or {}
        if marker.get("kind") != "keyword" or item["attached"]:
            continue
        if zone_of_page.get(item["page"], "body") != "body":
            continue
        role = marker.get("role_hint")
        seen[role] += 1
        first.setdefault(role, index)
    order = [role for role in RANKED]
    for role in ("section", "lesson"):
        enclosed = [r for r in RANKED if seen[r] and seen[role]
                    and seen[role] < seen[r] and first[role] < first[r]]  # fmt: skip
        if enclosed:
            order.insert(order.index(enclosed[0]), role)
    return order


def _keyword_rank(item, order=RANKED):
    """Rank of a sectioning word in the book's order ("Part" 0 < "Unit" 1 < "Chapter" 2), or
    None."""
    marker = item.get("numbering") or {}
    hint = marker.get("role_hint") if marker.get("kind") == "keyword" else None
    return order.index(hint) if hint in order else None


def _roles(items, zone_of_page):
    hints = defaultdict(Counter)
    for item in items:
        if (not item["attached"] and zone_of_page.get(item["page"]) == "body"
                and not item.get("keyword_inside")):  # fmt: skip
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
    outer = body_levels[0] if body_levels else None
    for level in body_levels:
        if level in level_role:
            continue
        # A section or lesson word at the outermost body level encloses what follows (a
        # "Section" holding chapters): below it the fallback starts at chapter.
        above = [ROLE_ORDER.index("unit") if lv == outer and level_role[lv] in ("section", "lesson")
                 else ROLE_ORDER.index(level_role[lv]) for lv in level_role if lv < level]  # fmt: skip
        start = max(above, default=ROLE_ORDER.index("unit"))
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
