"""Step 21: confirmed book parts: validation, the converter's guess, and authoritative zones."""

from test_structure import Book, chapters, decide

from book_core.structure import parts as P

FULL = {
    "front": {"first": 1, "last": 2},
    "body": {"first": 3, "last": 8},
    "bibliography": {"first": 9, "last": 10},
    "glossary": None,
    "appendix": None,
    "index": None,
}


def messages(parts, pages=10):
    return [(p["part"], p["message"]) for p in P.validate(parts, pages)]


def test_complete_parts_are_valid():
    assert P.validate(FULL, 10) == []


def test_every_part_must_be_a_range_or_explicitly_none():
    missing = {k: v for k, v in FULL.items() if k != "index"}
    assert [m[0] for m in messages(missing)] == ["index"]
    assert [m[0] for m in messages({**FULL, "body": None})] == ["body"]
    assert [m[0] for m in messages({**FULL, "glossary": {"first": 3}})] == ["glossary"]


def test_parts_must_not_overlap_or_leave_gaps():
    overlap = {**FULL, "bibliography": {"first": 8, "last": 10}}
    assert any("also in body" in m for _, m in messages(overlap))
    gap = {**FULL, "bibliography": {"first": 10, "last": 10}}
    assert any("in no part" in m for _, m in messages(gap))
    short = {**FULL, "bibliography": {"first": 9, "last": 9}}
    assert any("10-10 are in no part" in m for _, m in messages(short))
    late = {**FULL, "front": {"first": 2, "last": 2}}
    assert any("1-1 are in no part" in m for _, m in messages(late))


def test_back_matter_follows_the_body():
    swapped = {**FULL, "front": None, "body": {"first": 5, "last": 10},
               "bibliography": {"first": 1, "last": 4}}  # fmt: skip
    assert any("after the body" in m for _, m in messages(swapped))


def test_prefill_follows_zones_and_rear_kinds():
    zones = dict.fromkeys(range(1, 3), "front") | dict.fromkeys(range(3, 9), "body")
    zones |= dict.fromkeys(range(9, 11), "rear")
    guess = P.prefill(zones, [(9, 10, "bibliography")])
    assert guess == FULL
    other = P.prefill(zones, [(9, 10, "rear_other")])
    assert other["appendix"] == {"first": 9, "last": 10} and other["bibliography"] is None


def test_plans_name_zones_and_navigation_kinds():
    plan = P.zone_plan(FULL, 10)
    assert plan[1] == ("front", None) and plan[5] == ("body", None)
    assert plan[9] == ("rear", "bibliography")
    assert P.navigation_plan(FULL) == {9: "bibliography", 10: "bibliography"}


def test_confirmed_parts_are_authoritative_for_zones_and_kinds():
    book = Book(10)
    chapters(book)
    book.unit(7, "References", size=14, bold=True)
    book.body(7)
    book.body(8)
    guessed = decide(book)
    parts = {**FULL, "body": {"first": 3, "last": 6}, "bibliography": {"first": 7, "last": 10}}
    decided = decide(book, book_parts=parts)
    zone = {z.page: (z.zone, z.section_kind) for z in decided["page_zones"]}
    assert zone[2][0] == "front" and zone[6][0] == "body"
    assert all(zone[n] == ("rear", "bibliography") for n in range(7, 11))
    assert {z.page: z.zone for z in guessed["page_zones"]} != {n: z[0] for n, z in zone.items()}
    kinds = {n.page: n.kind for n in decided["navigation_pages"]}
    assert all(kinds[n] == "bibliography" for n in range(7, 11))


def test_no_parts_leave_the_decision_unchanged():
    book = Book(6)
    chapters(book)
    assert decide(book)["page_zones"] == decide(book, book_parts=None)["page_zones"]
