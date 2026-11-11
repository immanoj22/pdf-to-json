"""Book parts: front matter, body and the back-matter parts, as page ranges.

The converter guesses the parts from its zones and sections (``prefill``); a person confirms
or corrects every one of them, and the confirmed ranges are authoritative (``zone_plan``).

A part is a range ``{"first": n, "last": m}`` of physical pages (1-based, inclusive) or
``None`` (explicitly absent). Every part key must be present. The parts must not overlap,
must follow the book's order (front, body, then the back-matter parts) and must cover every
page of the book without gaps: a page in no part would be dropped from the book.

Back-matter parts (bibliography, glossary, index) are parsed as that kind of page: the
confirmed range is the evidence that the page is a reference list, glossary or index.
"""

from __future__ import annotations

FRONT = "front"
BODY = "body"
BACK = ("bibliography", "glossary", "appendix", "index")
PARTS = (FRONT, BODY, *BACK)
# Parts the structure stage parses as a printed list of that kind (NavigationKind).
NAVIGATION = {"bibliography": "bibliography", "glossary": "glossary", "index": "index"}


def _range(value):
    """(first, last) of a part value, or None when it is absent or malformed."""
    if isinstance(value, dict):
        first, last = value.get("first"), value.get("last")
        if isinstance(first, int) and isinstance(last, int):
            return first, last
    return None


def validate(parts, pages):
    """Problems in ``parts`` for a book of ``pages`` pages: [{"part", "message"}]; empty when
    the parts can be used."""
    problems = []

    def add(part, message):
        problems.append({"part": part, "message": message})

    if not isinstance(parts, dict):
        return [{"part": None, "message": "The book parts are missing."}]
    for part in PARTS:
        if part not in parts:
            add(part, "Say where this part is, or that the book has none.")
    for part in parts:
        if part not in PARTS:
            add(part, "This is not a book part.")
    ranges = {}
    for part in PARTS:
        if part not in parts:
            continue
        value = parts[part]
        if value is None:
            if part == BODY:
                add(part, "A book has a body: give its page range.")
            continue
        found = _range(value)
        if found is None:
            add(part, "Give the first and last page, or say there is none.")
            continue
        first, last = found
        if not 1 <= first <= last <= pages:
            add(part, f"Pages must run from 1 to {pages}, first no later than last.")
            continue
        ranges[part] = found
    if problems:
        return problems
    ordered = sorted(ranges.items(), key=lambda item: item[1])
    for (a, (_, a_last)), (b, (b_first, _)) in zip(ordered, ordered[1:], strict=False):
        if b_first <= a_last:
            add(b, f"Pages {b_first}-{min(a_last, ranges[b][1])} are also in {a}.")
        elif b_first > a_last + 1:
            add(b, f"Pages {a_last + 1}-{b_first - 1} are in no part (between {a} and {b}).")
    if ordered and ordered[0][1][0] > 1:
        add(ordered[0][0], f"Pages 1-{ordered[0][1][0] - 1} are in no part.")
    if ordered and ordered[-1][1][1] < pages:
        add(ordered[-1][0], f"Pages {ordered[-1][1][1] + 1}-{pages} are in no part.")
    if FRONT in ranges and BODY in ranges and ranges[FRONT][0] > ranges[BODY][0]:
        add(FRONT, "Front matter comes before the body.")
    if BODY in ranges:
        for part in BACK:
            if part in ranges and ranges[part][0] < ranges[BODY][0]:
                add(part, "Back matter comes after the body.")
    return problems


def prefill(page_zones, sections):
    """The converter's guess: parts from its page zones and section kinds.

    ``page_zones``: {page: zone}; ``sections``: [(first, last, kind)] of the rear sections
    (kinds as the structure stage names them). A rear page of a kind that is no part name
    goes to the appendix; two separate runs of one kind keep the longer (validation then
    shows the uncovered pages for the person to settle).
    """
    pages = sorted(page_zones)
    parts = dict.fromkeys(PARTS)

    def span(wanted):
        pages_of = [page for page in pages if page_zones[page] == wanted]
        return {"first": pages_of[0], "last": pages_of[-1]} if pages_of else None

    parts[FRONT], parts[BODY] = span("front"), span("body")
    rear = {}
    for first, last, kind in sections:
        part = kind if kind in BACK else "appendix"
        rear.setdefault(part, []).append((first, last))
    for part, found in rear.items():
        first, last = max(found, key=lambda r: (r[1] - r[0], -r[0]))
        parts[part] = {"first": first, "last": last}
    return parts


def zone_plan(parts, pages):
    """{page: (zone, kind)} the confirmed parts give: zone front, body or rear; kind is the
    back-matter part name for rear pages, else None."""
    plan = {}
    for part in PARTS:
        found = _range(parts.get(part))
        if found is None:
            continue
        zone = {FRONT: "front", BODY: "body"}.get(part, "rear")
        for page in range(found[0], found[1] + 1):
            if 1 <= page <= pages:
                plan[page] = (zone, None if zone != "rear" else part)
    return plan


def navigation_plan(parts):
    """{page: navigation kind} for the ranges parsed as reference lists, glossaries or
    indexes."""
    plan = {}
    for part, kind in NAVIGATION.items():
        found = _range((parts or {}).get(part))
        if found is not None:
            plan.update(dict.fromkeys(range(found[0], found[1] + 1), kind))
    return plan
