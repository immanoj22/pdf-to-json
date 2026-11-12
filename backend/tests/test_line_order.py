"""Word order against the PDF's line order: a weave of two columns is caught."""

from book_core.evaluation.line_order import check, descents, sequence

NATIVE = {1: [
    "left one", "left two", "left three",       # the left column, native positions 0-2
    "right one", "right two", "right three",    # the right column, positions 3-5
]}  # fmt: skip


def units(*texts):
    return [(f"u{i}", 1, text) for i, text in enumerate(texts)]


def test_a_unit_read_down_one_column_passes():
    assert not check(NATIVE, units("left one\nleft two\nleft three", "right one\nright two"))


def test_a_unit_that_leaves_one_column_for_the_next_passes():
    # one forward run into the next column; the reading order may leave the native order once
    assert not check(NATIVE, units("right three\nleft one"))


def test_two_columns_woven_into_one_unit_are_caught():
    woven = "right one\nleft one\nright two\nleft two\nright three"
    found = check(NATIVE, units(woven))
    assert [f["unit"] for f in found] == ["u0"] and found[0]["native_order"] == [3, 0, 4, 1, 5]


def test_lines_the_pdf_does_not_hold_are_skipped_and_one_line_units_pass():
    assert sequence("nothing like it\nleft one", {"left one": [0]}) == [0]
    assert descents([3, 0, 4, 1, 5]) == 2
    assert not check(NATIVE, units("right one"))
