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


def test_an_untitled_front_page_continues_the_section_above():
    book = Book(10)
    book.unit(1, "A Treatise on Rivers", size=26, bold=True)
    book.body(1, count=1)
    book.unit(2, "FOREWORD", size=20, bold=True)
    book.body(2)
    book.body(3)  # the foreword goes on: no title on this page
    book.unit(4, "PREFACE", size=20, bold=True)
    book.body(4)
    book.body(5)  # and so does the preface
    for page, title in ((6, "Chapter 1"), (8, "Chapter 2")):
        book.unit(page, title, size=20, bold=True)
        book.body(page)
        book.unit(page + 1, f"{title[-1]}.1 Background", size=14, bold=True)
    decided = decide(book)
    kinds = {z.page: z.section_kind for z in decided["page_zones"]}
    assert kinds[2] == kinds[3] == "preface" and kinds[4] == kinds[5] == "preface"


def _bibliography_book(first_numbers, running_head=True):
    book = Book(9)
    chapters(book)
    # pages 7-9: a list of numbered references that goes on across two pages
    book.unit(7, "REFERENCES", size=18, bold=True)
    for number in first_numbers[0]:
        book.unit(7, f"{number}. Smith J, Jones K. A study of rivers and boats. Hist Rev 2019.")
    for number in first_numbers[1]:
        book.unit(8, f"{number}. Lee A, Chan B. Trade on the water. J Hist 2020;5:11-9.")
    if running_head:
        book.pages[7]["running_heads"] = ["Bibliography"]
    return book


def _kinds(decided):
    return {n.page: n.kind for n in decided["navigation_pages"]}


def test_bibliography_pages_come_from_a_running_head_and_continued_numbering():
    book = _bibliography_book(([1, 2, 3], [4, 5, 6]))
    kinds = _kinds(decide(book))
    assert kinds.get(7) == "bibliography" and kinds.get(8) == "bibliography"


def test_numbering_that_continues_makes_the_next_page_the_same_bibliography():
    book = _bibliography_book(([10, 11, 12], [13, 14, 15]), running_head=False)
    kinds = _kinds(decide(book))
    assert kinds.get(7) == "bibliography" and kinds.get(8) == "bibliography"


def test_numbers_that_do_not_continue_are_not_the_same_list():
    book = _bibliography_book(([1, 2, 3], [1, 2, 3]), running_head=False)
    kinds = _kinds(decide(book))
    assert kinds.get(7) == "bibliography" and 8 not in kinds


def test_a_page_of_numbers_without_a_bibliography_title_is_not_one():
    book = Book(9)
    chapters(book)
    for number in (1, 2, 3):
        book.unit(7, f"{number}. Smith J, Jones K. A study of rivers and boats. Hist Rev 2019.")
    assert 7 not in _kinds(decide(book))


def test_a_front_page_opening_with_a_dedication_phrase_is_a_dedication():
    book = Book(10)
    book.unit(1, "A Treatise on Rivers", size=26, bold=True)
    book.body(1, count=1)
    for page in (2, 3):
        book.body(page)  # prelims
    book.unit(4, "DEDICATED TO the people of the river towns", size=10)  # set like the text
    book.body(4, count=1)
    for page, title in ((5, "Chapter 1"), (7, "Chapter 2")):
        book.unit(page, title, size=20, bold=True)
        book.body(page)
        book.unit(page + 1, f"{title[-1]}.1 Background", size=14, bold=True)
    kinds = {z.page: z.section_kind for z in decide(book)["page_zones"]}
    assert kinds[4] == "dedication"
