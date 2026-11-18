"""A title the running-head slot swallowed stays content (the two rules in furniture/classify.py).

Books print the full title once on the page where a section opens and a short form on the pages
after it. Rule 1: a slot text printed on one page only, while the slot's other pages repeat
their texts, is that title. Rule 2: the first page of a run (at least four pages, odd and even
pages kept apart when the slot alternates) is its title when the page looks like a section
start: a line as large as the head right under it, or far more white space under the head
than on the run's later pages. Anything else stays a running head."""

from __future__ import annotations

from book_core.furniture.classify import FurnitureConfig

from test_furniture import LATIN, SOURCE, PageBuilder, decide_book, page_features

HEAD_SIZE = 9.0


def book(heads, extra=None, alternate=False, gap_pages=(), config=None, figure_pages=(), printed=None):
    """pages 1..n: {page: running head text or None}; ``extra[page]`` adds a line right under the
    head; a page in ``gap_pages`` starts its body far lower (a picture opens it)."""
    pages = {}
    for number, text in heads.items():
        page = PageBuilder(number)
        top = 300 if number in gap_pages else 55  # the body starts right under the head
        body = [page.line(f"b{i}", 60, top + 14 * i, 550, LATIN[i % 3]) for i in range(30)]
        band = page.band("body", top, top + 450, [(60, 550, "column")])
        page.region("body", "main_text", body, band, 0)
        if text:
            even = number % 2 == 0
            x0, x1 = (60, 220) if (even or not alternate) else (390, 550)
            head = page.line("head", x0, 30, x1, text, size=HEAD_SIZE)
            second = None
            if extra and number in extra:
                second = page.line("sub", x0, 30 + HEAD_SIZE * 1.2, x1 + 100, extra[number], size=HEAD_SIZE)
            if number in figure_pages:  # the opener's big picture swallowed the title lines
                lines = [head] + ([second] if second else [])
                band = page.band("fig", 25, 60, [(x0, x1 + 100, "figure")])
                page.region("fig", "figure", lines, band, 0)
            else:
                page.region("head", "header_footer_candidate", [head])
                if second:
                    page.region("sub", "main_text", [second])
        if printed and number in printed:  # the same words printed elsewhere on the page: (text, size)
            words, size = printed[number]
            other = page.line("printed", 60, 300, 60 + 6 * len(words), words, size=size)
            page.region("printed", "main_text", [other])
        pages[number] = page.build()
    features = {n: page_features(*pages[n]) for n in pages}
    return decide_book(features, {}, SOURCE, config=config)


def roles(decisions, number):
    return {r.line_id.split("-", 1)[1]: r.role for r in decisions.roles[number]}


def runs():
    """Runs of 14, 10, 8 and 8 pages, a one-page title, and a short run of 3."""
    heads = {}
    for p in range(1, 15):
        heads[p] = "On Europe"
    heads[15] = "The Republic of France"  # rule 1: printed once
    for p in range(16, 26):
        heads[p] = "France"
    for p in range(26, 34):
        heads[p] = "Spain"  # opens at 26: a second title line under the head
    for p in range(34, 42):
        heads[p] = "Italy"  # opens at 34: the body starts far lower
    for p in range(42, 45):
        heads[p] = "Short"  # a run of three pages: too short
    for p in range(45, 53):
        heads[p] = "Greece"  # opens at 45 with nothing special: stays a running head
    return heads


def test_the_two_rules_and_what_stays_a_running_head():
    d = book(runs(), extra={26: "of the Iberian Peninsula", 42: "of the short run"}, gap_pages={34})
    assert roles(d, 15)["head"] == "content"  # rule 1
    assert roles(d, 26)["head"] == "content"  # rule 2: a title line right under the head
    assert roles(d, 34)["head"] == "content"  # rule 2: far more white space under the head
    for page in (16, 27, 35, 43, 45, 46, 14):
        assert roles(d, page)["head"] == "running_head", page
    # the run of three pages is too short, the page that only starts a run looks ordinary
    assert roles(d, 42)["head"] == "running_head" and roles(d, 45)["head"] == "running_head"
    # the slot group no longer lists the titles
    group = next(g for g in d.book.groups if g.role == "running_head")
    assert not {f"p{n}-head" for n in (15, 26, 34)} & set(group.line_ids)


def test_a_title_the_layout_grouped_with_the_openers_picture_still_counts():
    d = book(runs(), extra={26: "of the Iberian Peninsula"}, figure_pages={26})
    assert roles(d, 26)["head"] == "content"  # rule 2, though its lines sit in a figure stream
    assert roles(d, 27)["head"] == "running_head"


def test_odd_and_even_pages_are_kept_apart_when_the_slot_alternates():
    heads = {}
    for p in range(1, 25):
        heads[p] = "BOOK TITLE" if p % 2 == 0 else ("Alpha" if p < 13 else "Beta")
    d = book(heads, extra={13: "a second title line"}, alternate=True)
    # the run of "Beta" is on the odd pages 13..23 (six pages); page 13 opens it
    assert roles(d, 13)["head"] == "content"
    for page in (11, 15, 2, 14):
        assert roles(d, page)["head"] == "running_head", page


def test_a_slot_of_all_different_texts_is_left_alone():
    heads = {p: f"Guide word {chr(97 + p % 26)}{p}" for p in range(1, 25)}  # dictionary guide words
    on = book(heads, extra={5: "second line"})
    off = book(heads, extra={5: "second line"}, config=FurnitureConfig(title_min_slot_pages=10**6))
    assert {p: roles(on, p) for p in range(1, 25)} == {p: roles(off, p) for p in range(1, 25)}


def test_the_rules_can_be_switched_off_and_default_to_the_documented_values():
    d = book(runs(), extra={26: "of the Iberian Peninsula"}, config=FurnitureConfig(title_min_slot_pages=10**6))
    assert roles(d, 15)["head"] == "running_head" and roles(d, 26)["head"] == "running_head"
    c = FurnitureConfig()
    assert (c.title_run_pages, c.title_min_recurring_share, c.title_min_slot_pages) == (4, 0.8, 6)


# ------------------------------------------------------------------ the report (lossless and QC)


def furniture(texts, kind="running_head"):
    return [{"id": f"f{n}", "kind": kind, "page": n + 1, "content": {"text": t}} for n, t in enumerate(texts)]


def test_single_furniture_lines_are_listed_so_they_cannot_hide():
    from book_core.assembly.lossless import compare, single_furniture_lines

    heads = ["On Europe"] * 7 + ["The Republic of France"] + ["France"] * 7 + ["Page 12", "Page 13"]
    found = single_furniture_lines({"furniture": furniture(heads)})
    assert found["count"] == 1 and found["examples"][0] == {"page": 8, "kind": "running_head", "text": "The Republic of France"}
    # digits are masked ("Page 12" and "Page 13" are one text); a slot of all different texts reports nothing
    assert single_furniture_lines({"furniture": furniture([f"Guide word {chr(97 + n)}" for n in range(20)])})["count"] == 0
    assert single_furniture_lines({"furniture": furniture(["A", "B", "A"])})["count"] == 0  # too few lines to say
    assert single_furniture_lines({"furniture": furniture(heads, kind="folio")})["count"] == 0  # only heads and feet
    # the Stage 1 lossless result carries it
    result = compare({"content": [], "furniture": furniture(heads), "suppressed": []}, __import__("collections").Counter())
    assert result["furniture_singletons"]["count"] == 1 and result["missing"] == 0


def test_a_head_whose_text_is_already_a_larger_heading_nearby_is_its_running_head():
    # the title of the run that opens at 15 is also printed larger on the page before it (a real
    # heading): the head on page 15 is that heading's running head, not its title
    heads = {p: "On Europe" for p in range(1, 15)}
    heads[15] = "The Republic of France"
    heads.update({p: "France" for p in range(16, 26)})
    near = book(heads, printed={14: ("The Republic of France", 20.0)})
    assert roles(near, 15)["head"] == "running_head"
    # the same words at body size are only body text: the rule still applies
    body = book(heads, printed={14: ("The Republic of France", HEAD_SIZE)})
    assert roles(body, 15)["head"] == "content"
    # a run opener (rule 2) is held back the same way
    runs_ = runs()
    held = book(runs_, extra={26: "of the Iberian Peninsula"}, printed={25: ("Spain", 18.0)})
    assert roles(held, 26)["head"] == "running_head"


def test_a_singleton_with_no_short_form_after_it_is_not_a_title():
    # the text is printed once, but no run of another text follows it in the slot (the unit has
    # no pages of its own after the line): it stays a running head
    heads = {p: "On Europe" for p in range(1, 15)}
    heads[15] = "The Republic of France"
    heads.update({p: None for p in range(16, 22)})
    heads.update({p: ("Italy" if p % 2 else "Unit Ten") for p in range(22, 30)})  # another run follows
    d = book(heads)
    assert roles(d, 15)["head"] == "running_head"
    # one page of the short form is too little to call it a run
    heads[16] = "France"
    assert roles(book(heads), 15)["head"] == "running_head"


def test_the_last_singletons_of_a_slot_are_titles():
    # the book's back matter: titles printed once at the very end, no run after them
    heads = {p: "On Europe" for p in range(1, 15)}
    heads[15] = "Credits"
    heads[16] = "About the Author"
    d = book(heads)
    assert roles(d, 15)["head"] == "content" and roles(d, 16)["head"] == "content"
