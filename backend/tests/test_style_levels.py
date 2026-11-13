"""The same printed heading style is one heading level (structure.hierarchy._style_levels)."""

from book_core.structure.hierarchy import _style_levels


def item(page, level, group, method="style_rank", attached=False):
    return {"page": page, "level": level, "level_method": method, "attached": attached,
            "style_group": group, "numbering": None, "level_reasons": []}


def test_sections_lifted_on_a_chapter_opener_take_their_styles_level():
    items = [item(1, 1, "title", "navigation"), item(1, 1, "sec"), item(1, 1, "sec")]
    items += [item(p, 2, "sec") for p in range(2, 10)]
    _style_levels(items, {})
    assert [i["level"] for i in items if i["style_group"] == "sec"] == [2] * 10
    assert items[0]["level"] == 1  # a heading placed by the contents keeps its level


def test_no_clear_majority_or_few_headings_change_nothing():
    split = [item(p, 1 + p % 2, "sec") for p in range(8)]
    few = [item(1, 1, "few"), item(2, 2, "few"), item(3, 2, "few")]
    _style_levels(split + few, {})
    assert [i["level"] for i in split] == [1 + p % 2 for p in range(8)]
    assert [i["level"] for i in few] == [1, 2, 2]


def test_front_matter_and_attached_titles_are_left_alone():
    items = [item(1, 1, "sec"), item(2, 1, "sec", attached=True)]
    items += [item(p, 2, "sec") for p in range(3, 10)]
    _style_levels(items, {1: "front"})
    assert items[0]["level"] == 1 and items[1]["level"] == 1


def test_a_style_level_that_would_skip_going_down_is_not_applied():
    # every chapter: title (1), section (2), then a run-in style at level 3 ...
    items = []
    for p in range(1, 8):
        items += [item(p, 1, "chapter", "navigation"), item(p, 2, "section", "navigation"),
                  item(p, 3, "minor")]
    # ... except one placed straight under a chapter title: level 3 there would skip
    items += [item(9, 1, "chapter", "navigation"), item(9, 2, "minor")]
    _style_levels(items, {})
    assert items[-1]["level"] == 2
