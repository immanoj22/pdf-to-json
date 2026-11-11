"""Step 21 items 10-13 (synthetic): titles broken over lines, opener numbers, non-headings,
and the same label at different levels."""

from test_structure import Book, decide, headings_by_text

from book_core.structure.decide import flag_level_conflicts


def test_title_continued_in_lowercase_is_one_heading():
    book = Book(2)
    book.unit(1, "GENERAL ANATOMY", size=24, bold=True)
    book.unit(1, "with Case Scenarios and Clinical Applications", size=18, bold=True, gap=1.4)
    book.body(1)
    book.unit(2, "Second title", size=24, bold=True)
    book.body(2)
    found = headings_by_text(decide(book), book)
    joined = "GENERAL ANATOMY with Case Scenarios and Clinical Applications"
    assert joined in found
    assert "with Case Scenarios and Clinical Applications" not in found
    assert found[joined].style_group.endswith(":bold:upper")  # the title's style, not the tail's


def test_open_ended_title_line_joins_the_next_piece():
    book = Book(1)
    book.unit(1, "Assessment of Learning,", size=20, bold=True)
    book.unit(1, "Teaching and Training", size=20, bold=True, gap=1.4)
    book.body(1)
    found = headings_by_text(decide(book), book)
    assert "Assessment of Learning, Teaching and Training" in found


def test_bare_opener_number_joins_its_title():
    book = Book(6)
    for page, number, title in ((1, "1", "Sampling"), (3, "2", "Probability")):
        book.unit(page, "C H A P T E R", size=12)
        book.unit(page, number, size=36, bold=True)
        book.unit(page, title, size=24, bold=True, gap=1.4)
        book.body(page)
    found = headings_by_text(decide(book), book)
    assert "1 Sampling" in found or "C H A P T E R 1 Sampling" in found or any(
        t.endswith("1 Sampling") for t in found)
    assert not any(t in {"1", "2"} for t in found)  # no heading made of the bare number


def test_colon_and_bullet_lead_ins_and_empty_text_are_not_headings():
    book = Book(2)
    book.unit(1, "Skeletal system", size=20, bold=True)
    book.body(1)
    book.unit(1, "Nutrient artery:", size=10, bold=True, gap=3.0)
    book.body(1)
    book.unit(1, "◆Periosteal arteries", size=10, bold=True, gap=3.0)
    book.body(1)
    book.unit(1, " ", size=20, bold=True, gap=3.0)
    book.body(1)
    found = headings_by_text(decide(book), book)
    assert "Skeletal system" in found
    assert "Nutrient artery:" not in found
    assert "◆Periosteal arteries" not in found
    assert " " not in found


def item(text, level, page=1):
    return {"run_in": None, "tokens": len(text.split()), "page": page, "text": text,
            "numbered": False, "level": level, "level_reasons": [], "review_required": False}


def test_same_label_at_different_levels_is_flagged_not_changed():
    items = [item("INTRODUCTION", 2, 1), item("Introduction", 2, 5), item("INTRODUCTION", 3, 9),
             item("Methods", 2, 2), item("Methods", 2, 6)]
    assert flag_level_conflicts(items, {}) == 1
    flagged = [i for i in items if i["review_required"]]
    assert [(i["text"], i["level"]) for i in flagged] == [("INTRODUCTION", 3)]
    assert flagged[0]["level_conflict"] and "levels [2, 3]" in flagged[0]["level_reasons"][0]
    assert [i["level"] for i in items] == [2, 2, 3, 2, 2]  # levels unchanged


def test_level_conflict_tie_flags_all_and_ignores_front_matter():
    items = [item("Summary", 2, 1), item("Summary", 3, 5), item("Preface", 1, 9),
             item("Preface", 2, 10)]
    zone = {9: "front", 10: "front"}
    assert flag_level_conflicts(items, zone) == 2
    assert [i["review_required"] for i in items] == [True, True, False, False]
