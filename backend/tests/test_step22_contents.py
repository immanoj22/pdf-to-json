"""A contents title is front matter wherever its page was placed; a "section" word that holds
the book's chapters is its top level (a part)."""

from book_core.structure import hierarchy


def item(page, text, prominence, keyword=None, attached=False):
    marker = {"kind": "keyword", "role_hint": keyword, "depth": 1, "value": 1} if keyword else None
    return {
        "page": page, "text": text, "attached": attached, "numbering": marker,
        "prominence": prominence, "stream": "main", "toc_level": None, "style_group": None,
        "repeated": 0, "detection_confidence": 0.9, "spine": False, "run_in": None,
    }  # fmt: skip


def assign(items, zones):
    hierarchy.assign(items, {}, zones, {})
    return [(i["text"], i["role"], i["level"]) for i in items]


def test_a_contents_title_in_the_body_is_front_matter_not_a_part():
    items = [item(1, "Contents", (3, 1, 1)), item(2, "Fundamentals", (3, 1, 1), "section"),
             item(3, "Interscalene Block", (2, 1, 1), "chapter"),
             item(4, "Supraclavicular Block", (2, 1, 1), "chapter")]  # fmt: skip
    got = assign(items, dict.fromkeys(range(1, 5), "body"))  # the confirmed parts: all body
    assert got[0] == ("Contents", "front_section_title", 1)
    assert [role for _, role, _ in got[1:]] == ["part", "chapter", "chapter"]


def test_a_section_word_that_holds_chapters_is_a_part_level_role():
    items = [item(1, "Fundamentals", (3, 1, 1), "section"),
             item(2, "Introduction", (2, 1, 1), "chapter"),
             item(3, "Upper Limb Blocks", (3, 1, 1), "section"),
             item(4, "Interscalene Block", (2, 1, 1), "chapter"),
             item(5, "Supraclavicular Block", (2, 1, 1), "chapter")]  # fmt: skip
    got = assign(items, dict.fromkeys(range(1, 6), "body"))
    assert [role for _, role, _ in got] == ["part", "chapter", "part", "chapter", "chapter"]


def test_entries_on_a_contents_page_are_not_headings():
    from book_core.structure.decide import _without_contents_entries

    items = [item(1, "Contents", (3, 1, 1)), item(1, "Upper Limb Blocks", (3, 1, 1)),
             item(2, "Interscalene Block", (2, 1, 1))]  # fmt: skip
    kept = [i["text"] for i in _without_contents_entries(items)]
    assert kept == ["Contents", "Interscalene Block"]
