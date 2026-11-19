"""A hyphen the PDF draws as a text object of its own goes last in its line (geometry only)."""

from types import SimpleNamespace

import pytest

from book_core.furniture.line_end_hyphens import attach_line_end_hyphens, span_order
from book_core.layout.models import VisualLine


def box(x0, x1, y0=181.0, y1=191.0):
    return SimpleNamespace(x0=x0, x1=x1, y0=y0, y1=y1)


def line(ids, direction=(1.0, 0.0), text_direction=None, size=9.5):
    return VisualLine.model_validate({
        "id": "L", "span_ids": ids, "source_line_ids": ["s"],
        "bbox": {"x0": 60, "y0": 181, "x1": 390, "y1": 191},
        "baseline_start": (60, 189), "baseline_end": (388, 189), "direction": direction,
        "rotation": 0, "writing_mode": "horizontal", "text_direction": text_direction,
        "font_size": size, "visible": True, "inside_content": True,
    })  # fmt: skip


def spans(**by_id):
    return {k: SimpleNamespace(raw_text=t, bbox=b) for k, (t, b) in by_id.items()}


def test_a_hyphen_listed_first_but_printed_at_the_end_goes_last():
    s = spans(h=("-", box(386, 388)), t=("Die obige Darstellung ist als Analysemo", box(60, 386)))
    assert span_order(line(["h", "t"]), s) == ["t", "h"]


def test_a_space_before_the_hyphen_leaves_the_line_as_printed():
    """The join drops the hyphen and the line ends but cannot drop a space before the hyphen
    ("effi " + "-"), which would leave "effi cient": such a line is not reordered."""
    s = spans(h=("-", box(387, 390)), t=("Larger communities and more effi ", box(222, 389.6)))
    assert span_order(line(["h", "t"], size=9.0), s) is None


def test_a_dash_at_the_line_start_is_a_bullet_and_stays_first():
    s = spans(h=("–", box(60, 66)), t=("item text", box(72, 386)))
    assert span_order(line(["h", "t"]), s) is None
    s = spans(h=("-", box(60, 64)), t=("item text", box(70, 386)))
    assert span_order(line(["h", "t"]), s) is None  # a hyphen-minus bullet is just as much a bullet


def test_a_hyphen_far_from_the_text_is_not_a_line_end_hyphen():
    s = spans(h=("-", box(300, 302)), t=("short", box(60, 100)))
    assert span_order(line(["h", "t"]), s) is None


def test_a_hyphen_already_last_or_a_line_of_hyphens_is_left_alone():
    s = spans(t=("word", box(60, 100)), h=("-", box(100, 102)))
    assert span_order(line(["t", "h"]), s) is None
    s = spans(a=("-", box(60, 62)), b=("-", box(70, 72)))
    assert span_order(line(["a", "b"]), s) is None


def test_the_reading_end_of_a_right_to_left_line_is_its_left_side():
    rtl = {"text_direction": "rtl"}
    s = spans(h=("-", box(56, 60)), t=("نص", box(60, 386)))  # printed at the left: the reading end
    assert span_order(line(["h", "t"], **rtl), s) == ["t", "h"]
    s = spans(h=("-", box(386, 390)), t=("نص", box(60, 386)))  # printed at the right: the reading start
    assert span_order(line(["h", "t"], **rtl), s) is None


@pytest.mark.parametrize("mark", ["‐", "‑", "­"])
def test_other_hyphen_characters_count(mark):
    s = spans(h=(mark, box(386, 388)), t=("Analysemo", box(60, 386)))
    assert span_order(line(["h", "t"]), s) == ["t", "h"]


def test_attach_returns_the_same_layout_when_nothing_moves_and_keeps_every_span():
    s = spans(h=("-", box(386, 388)), t=("text", box(60, 386)))
    moved = SimpleNamespace(lines=[line(["h", "t"])], model_copy=lambda update: SimpleNamespace(**update))
    out = attach_line_end_hyphens(moved, s)
    assert [x.span_ids for x in out.lines] == [["t", "h"]]
    same = SimpleNamespace(lines=[line(["t"])])
    assert attach_line_end_hyphens(same, s) is same
