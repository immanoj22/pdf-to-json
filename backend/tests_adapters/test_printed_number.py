"""The printed opener number of a part or chapter heading is its label, never title text."""

from book_adapters.engine.outline import printed_value, split_printed_number
from book_adapters.engine.text import TextRef


def ref(text):
    return TextRef("u", {"text": text, "spans": []}, 0)


def test_number_above_or_below_the_title_is_split_off():
    title, number = split_printed_number(ref("1\nKnobology and Image Optimization"))
    assert title.plain() == "Knobology and Image Optimization" and printed_value(number) == 1
    title, number = split_printed_number(ref("Interscalene Block\n2"))
    assert title.plain() == "Interscalene Block" and printed_value(number) == 2
    title, number = split_printed_number(ref("Part One\nIV"))
    assert title.plain() == "Part One" and printed_value(number) == 4


def test_a_title_with_a_number_inside_a_line_stays_whole():
    for text in ("Chapter 2 Basics", "Covid 19", "Type 2\nDiabetes Care", "Knobology"):
        title, number = split_printed_number(ref(text))
        assert number is None and title.plain() == " ".join(text.split())
