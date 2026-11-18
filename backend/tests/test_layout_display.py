"""Display equations found from the page layout (``equations.layout_display``).

Pieces of an equation set as separate one-glyph lines, in a font whose line boxes are several
times taller than its text, are one display when no prose shares their band, they carry maths
and they are set apart. A label "(5.5)" at the right edge makes it numbered."""

from __future__ import annotations

from types import SimpleNamespace

from book_core.equations.layout_display import display_candidates

SIZE = 10.0


def line(i, text, x0, x1, baseline, tall=False, size=SIZE):
    height = 5.5 * size if tall else 1.3 * size
    return SimpleNamespace(
        id=f"L{i}", span_ids=[f"S{i}"], blank=False, visible=True, horizontal=True, font_size=size,
        baseline_start=(x0, baseline), baseline_end=(x1, baseline),
        bbox=SimpleNamespace(x0=x0, x1=x1, y0=baseline - height / 2, y1=baseline + height / 2),
        text=text,
    )  # fmt: skip


def page(rows):
    lines = [line(i, *row) for i, row in enumerate(rows)]
    store = SimpleNamespace(spans={f"S{i}": SimpleNamespace(raw_text=l.text) for i, l in enumerate(lines)})
    return store, lines


PROSE = "The electrical properties of the double layer resemble those of a plate"


def book(equation, label="(5.5)", extra=()):
    rows = [(PROSE, 90, 380, 100, True), (PROSE, 90, 380, 113, True)]
    rows += equation
    if label:
        rows.append((label, 357, 378, 133, True))
    rows += [(PROSE, 90, 380, 160, True), (PROSE, 90, 380, 173, True)]
    rows += list(extra)
    return page(rows)


FRACTION = [("C", 210, 216, 133), ("=", 219, 224, 133), ("A", 238, 244, 127), ("d", 233, 238, 139)]


def found(store, lines, **kw):
    return display_candidates(store, lines, {}, **kw)


def test_one_glyph_lines_between_prose_lines_with_a_label_are_a_numbered_equation():
    store, lines = book(FRACTION)
    (cand,) = found(store, lines)
    assert cand.numbered and cand.label == "(5.5)"
    assert len(cand.line_ids) == 5 and cand.label_line == "L6"
    assert cand.box[1] < 133 < cand.box[3] and cand.box[2] < 250  # the label is not in the box


def test_the_same_pieces_without_a_label_are_an_unnumbered_equation_when_read_as_maths():
    store, lines = book(FRACTION, label=None)
    assert found(store, lines) == []  # nothing marks them as maths for the unnumbered kind
    (cand,) = found(store, lines, math_lines={"L2"})
    assert not cand.numbered and cand.label is None


def test_pieces_inside_a_prose_band_and_prose_with_words_are_not_equations():
    inline = [("x", 150, 156, 100), ("=", 160, 166, 100)]  # share the first prose line's band
    store, lines = book(inline, label=None)
    assert found(store, lines, math_lines={"L2", "L3"}) == []
    sentence = [("where x = 3 is the value we get here", 200, 300, 133)]
    store, lines = book(sentence, label=None)
    assert found(store, lines, math_lines={"L2"}) == []  # prose line, not an equation


def test_a_display_found_by_drawn_evidence_is_not_repeated_and_lists_are_not_equations():
    store, lines = book(FRACTION)
    assert found(store, lines, taken=[(200, 120, 250, 145)]) == []
    entry = [("1.", 100, 110, 133), ("Smith, J. (2020) Nature 1, pp. 10", 120, 300, 133)]
    store, lines = book(entry, label=None)
    assert found(store, lines, math_lines={"L2", "L3"}) == []
