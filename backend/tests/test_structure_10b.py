"""Step 10b heading rules (synthetic): weight mix, reference lists, isolated and italic titles,
chapter labels and subtitles, section templates."""

from test_structure import Book, decide, headings_by_text

from book_core.structure.navigation import page_statistics


def styled(decided, book):
    units = {u["unit"]: u for p in book.pages for u in p["units"]}
    return {" ".join(units[u]["text"] for u in s.unit_ids): s for s in decided["styled"]}


def test_line_only_partly_bold_is_not_a_standalone_title():
    book = Book(1)
    lead = book.unit(1, "Make a poster Think about the rules", size=10, bold=True)
    lead["bold"] = 0.55  # a bold lead running into regular text on one line
    book.body(1)
    whole = book.unit(1, "Make a timeline", size=10, bold=True, gap=3.0)
    whole["caps"] = 0.1
    book.body(1)
    found = headings_by_text(decide(book), book)
    assert "Make a poster Think about the rules" not in found
    assert "Make a timeline" in found


def reference_page(book, page, dated=True):
    names = ["Abbott", "Baker", "Chen", "Diaz", "Evans", "Fischer", "Garcia", "Hughes", "Ito"]
    for name in names:
        year = " (2005)." if dated else ","
        book.unit(page, f"{name}, J.{year} Studies of river towns, 12, 33-41 and more notes")


def test_reference_lists_are_bibliographies_not_indexes():
    book = Book(4)
    book.unit(1, "Chapter 1", size=20, bold=True)
    book.body(1)
    book.unit(2, "REFERENCES", size=10, bold=True, gap=3.0)
    reference_page(book, 2)
    reference_page(book, 3)
    book.unit(4, "Chapter 2", size=20, bold=True)
    book.body(4)
    evidence = book.evidence()
    stats = page_statistics(evidence["pages"][2], 4)
    assert stats["dated"] >= 0.8 and stats["locators"] > 0.35  # comma before numbers
    decided = decide(book)
    kinds = {n.page: n.kind for n in decided["navigation_pages"]}
    assert kinds == {2: "bibliography", 3: "bibliography"}
    found = headings_by_text(decided, book)
    assert "REFERENCES" in found
    assert not any(text.startswith("Abbott") for text in found)
    # A reference list inside the body stays body matter of its chapter.
    assert {z.page: z.zone for z in decided["page_zones"]}[3] == "body"


def test_isolated_capitalised_title_at_body_size_is_a_heading_not_a_label():
    book = Book(3)
    for page, title in ((1, "WHAT IS RESILIENCE"), (2, "ROLE OF SCHOOLS"), (3, "COMMUNITY")):
        book.unit(page, title, size=10, bold=True, gap=3.0)
        book.body(page)
    tight = Book(1)
    tight.unit(1, "SOURCE SPEECH", size=10, bold=True, gap=1.0)
    tight.body(1)
    assert {"WHAT IS RESILIENCE", "ROLE OF SCHOOLS"} <= set(headings_by_text(decide(book), book))
    decided = decide(tight)
    assert "SOURCE SPEECH" not in headings_by_text(decided, tight)
    assert styled(decided, tight)["SOURCE SPEECH"].role == "label"


def test_isolated_italic_line_is_a_title_an_italic_phrase_is_not():
    book = Book(1)
    book.unit(1, "Main findings", size=13, bold=True)
    book.body(1)
    title = book.unit(1, "Family Conflict", size=10, gap=2.4)
    title["italic"] = 1.0
    book.body(1)
    phrase = book.unit(1, "a phrase in italic", size=10, gap=1.0)
    phrase["italic"] = 1.0
    book.body(1)
    found = headings_by_text(decide(book), book)
    assert "Family Conflict" in found and found["Family Conflict"].level == 2
    assert "a phrase in italic" not in found


def test_chapter_label_title_and_subtitle_form_one_heading():
    book = Book(2)
    for page in (1, 2):
        book.unit(page, f"Chapter {page}", size=14, bold=True)
        book.unit(page, "Changing Lives" if page == 1 else "Immigrant Children", size=18,
                  bold=True, gap=2.0)  # fmt: skip
        book.unit(page, "Theoretical Advances" if page == 1 else "Making a New Life", size=16,
                  bold=True, gap=1.7)  # fmt: skip
        book.body(page, 1)  # few units per page: identical filler would read as a glossary
        book.unit(page, "Neglected Populations", size=10, bold=True, gap=3.0)["caps"] = 0.1
        book.body(page, 1)
    found = headings_by_text(decide(book), book)
    title = found["Chapter 1 Changing Lives Theoretical Advances"]
    assert title.level == 1
    assert found["Chapter 2 Immigrant Children Making a New Life"].level == 1
    assert found["Neglected Populations"].level == 2


def test_section_template_step_labels_are_labels():
    book = Book(12)
    steps = ("ASK QUESTIONS", "USE TOOLS", "SHARE RESULTS")
    for section in range(4):
        first = section * 3 + 1
        book.unit(first, f"{section + 1:02d} Lesson on the valley", size=20, bold=True)
        book.body(first)
        for offset, step in enumerate(steps):
            book.unit(first + offset, step, size=8, bold=True, gap=2.5)
            book.body(first + offset)
    decided = decide(book)
    found = headings_by_text(decided, book)
    assert "01 Lesson on the valley" in found
    assert not any(step in found for step in steps)
    labels = [s for s in decided["styled"] if s.role == "label"]
    assert len(labels) == 12
    assert any("section template" in reason for reason in labels[0].reasons)
