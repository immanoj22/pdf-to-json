"""A small piece (a script) joins the line of its base only when it sits near the base's
baseline: a producer with very tall font boxes made every size-7 piece "compatible" with any
text line whose tall box it overlapped, which fused fourteen prose lines into one."""

from __future__ import annotations

from book_core.layout.lines import Fragment, compatible


def fragment(baseline, size, x0, x1, text="x"):
    return Fragment(
        span_ids=["s"], source_line_ids=["l"], direction=(1.0, 0.0), writing_mode="horizontal",
        visible=True, along=[x0, x1], normal=[baseline - 28, baseline + 28],  # a tall font box
        baselines=[(baseline, 1)], sizes=[(size, 1)], lead=text, text=text, wordy=True,
    )  # fmt: skip


def test_a_script_beside_its_base_joins_it():
    base = fragment(408, 10, 187, 195, "M")
    script = fragment(403, 7, 195, 200, "n")  # raised by half a size
    assert compatible(base, script)


def test_a_small_piece_a_line_away_does_not_join_prose():
    prose = fragment(376, 10, 117, 378, "solution as solvated ions")
    script = fragment(403, 7, 218, 222, "n")  # a line below, boxes overlap because they are tall
    assert not compatible(prose, script)
    assert not compatible(script, prose)
