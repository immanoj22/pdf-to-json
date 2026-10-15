"""Step 13b: equation ownership, figure conversion and region boundaries."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_equations import _equation_book, _page

from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.equations import detect, ownership
from book_core.equations.models import EquationRegion, GlyphOwnership, PageEquations
from book_core.model.common import BBox

SIZE = 10.0


def _box(x0, y0, x1, y1):
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def _obj(oid, box, ops=("c", "c", "c", "c"), clip=None, kind="drawing", fill=(0, 0, 0)):
    return SimpleNamespace(
        id=oid,
        kind=kind,
        bbox=_box(*box),
        fill=list(fill) if fill is not None else None,
        stroke=None,
        path_items=[SimpleNamespace(operator=o, coordinates=list(box)) for o in ops],
        clip_ids=[clip] if clip else [],
    )


def _clusters(glyphs, bars=(), dots=(), parts=(), text_boxes=(), clips=None):
    signatures = {g.id: "shape" for g in glyphs}
    found = detect.vector_clusters(
        list(glyphs), list(bars), signatures, frozenset({"shape"}), SIZE,
        list(text_boxes), list(dots), clips or {}, list(parts),
    )  # fmt: skip
    return sorted(sorted(o.id for o in cluster) for cluster in found)


# Boundaries -----------------------------------------------------------------------------


def test_a_minus_bar_joins_the_operands_beside_it():
    a, b = _obj("a", (0, 0, 6, 8)), _obj("b", (18, 0, 24, 8))
    minus = _obj("m", (9, 3.7, 15, 4.3), ops=("re",))
    assert _clusters([a, b]) == [["a"], ["b"]]  # wider than the join gap alone
    assert _clusters([a, b], bars=[minus]) == [["a", "b", "m"]]


def test_inline_expressions_on_neighbouring_lines_stay_apart():
    upper, lower = _obj("u", (0, 0, 6, 8)), _obj("l", (0, 12, 6, 20))
    text = [_box(20, 0, 80, 8), _box(20, 12, 80, 20)]
    assert _clusters([upper, lower]) == [["l", "u"]]  # display glyphs stack at this gap
    assert _clusters([upper, lower], text_boxes=text) == [["l"], ["u"]]


def test_a_fraction_bar_takes_only_its_nearest_rows():
    numerator, denominator = _obj("n", (0, 0, 6, 6)), _obj("d", (0, 8.5, 6, 14.5))
    bar = _obj("bar", (0, 7, 20, 7.5), ops=("re",))
    further = _obj("f", (12, 17, 18, 23))  # under the bar, but a row further down
    assert _clusters([numerator, denominator, further], bars=[bar]) == [
        ["bar", "d", "n"],
        ["f"],
    ]


def test_drawing_groups_separate_neighbours_and_join_wide_spacing():
    clips = {
        "c1": SimpleNamespace(bbox=_box(-1, -1, 7, 9)),
        "c2": SimpleNamespace(bbox=_box(7.5, -1, 41, 9)),
    }
    a = _obj("a", (0, 0, 6, 8), clip="c1")
    a2 = _obj("a2", (0, 0, 2, 2), clip="c1")
    b = _obj("b", (8, 0, 14, 8), clip="c2")
    c = _obj("c", (34, 0, 40, 8), clip="c2")  # far from b, drawn in the same group
    assert _clusters([a, a2, b, c]) == [["a", "a2", "b"], ["c"]]
    assert _clusters([a, a2, b, c], clips=clips) == [["a", "a2"], ["b", "c"]]


def test_a_clip_holding_text_is_not_a_drawing_group():
    clips = {"page": SimpleNamespace(bbox=_box(-1, -1, 41, 9))}
    a, c = _obj("a", (0, 0, 6, 8), clip="page"), _obj("c", (34, 0, 40, 8), clip="page")
    text = [_box(15, 0, 25, 8)]
    assert _clusters([a, c], text_boxes=text, clips=clips) == [["a"], ["c"]]


def test_dots_and_parts_join_a_cluster_but_never_start_one():
    a, b = _obj("a", (0, 0, 6, 8)), _obj("b", (9, 0, 15, 8))
    dot = _obj("dot", (6.5, 7, 7.5, 8))
    lonely_dot = _obj("far", (60, 7, 61, 8))
    radical = _obj("r", (15.1, -4, 25, 9), ops=("l", "l", "l", "c"))
    lonely_part = _obj("p", (80, 0, 90, 12), ops=("l", "l", "l", "c"))
    found = _clusters([a, b], dots=[dot, lonely_dot], parts=[radical, lonely_part])
    assert found == [["a", "b", "dot", "r"]]


def test_display_rows_join_within_the_book_line_pitch():
    def draft(y0, y1):
        return {
            "box": _box(0, y0, 30, y1),
            "objects": [f"o{y0}"],
            "ranges": [],
            "rules": [],
            "signals": {"glyphs": 1},
            "groups": frozenset(),
            "inline": False,
        }

    rows = [draft(0, 10), draft(16, 26), draft(60, 70)]
    detect._join_rows(rows, [], SIZE, pitch=12.0)
    assert [r["objects"] for r in rows] == [["o0", "o16"], ["o60"]]
    assert "display_rows" in rows[0]["rules"]
    blocked = [draft(0, 10), draft(16, 26)]
    detect._join_rows(blocked, [_box(0, 11, 30, 15)], SIZE, pitch=12.0)  # text between
    assert len(blocked) == 2


# Ownership ------------------------------------------------------------------------------


def _line(lid, spans, box):
    return SimpleNamespace(
        id=lid,
        span_ids=spans,
        bbox=_box(*box),
        direction=(1.0, 0.0),
        text_direction=None,
        blank=False,
    )


def test_inline_drawn_objects_are_read_at_their_place_in_the_line():
    store = SimpleNamespace(
        spans={
            "s1": SimpleNamespace(id="s1", raw_text="The value", bbox=_box(0, 0, 45, 10)),
            "s2": SimpleNamespace(id="s2", raw_text="is small.", bbox=_box(70, 0, 115, 10)),
        }
    )
    line = _line("L", ["s1", "s2"], (0, 0, 115, 10))
    place = ownership.inline_place(line, store, {}, _box(50, 0, 65, 10))
    assert (place.span_id, place.offset) == ("s2", 0)
    end = ownership.inline_place(line, store, {}, _box(120, 0, 130, 10))
    assert (end.span_id, end.offset) == ("s2", len("is small."))


def test_a_display_equation_is_anchored_in_its_own_column():
    lines = [
        _line("a1", ["x"], (0, 0, 200, 10)),
        _line("a2", ["x"], (0, 40, 200, 50)),
        _line("b1", ["x"], (300, 15, 500, 25)),  # another column, between them
    ]
    layout = SimpleNamespace(lines=lines)
    order = SimpleNamespace(
        streams=[
            SimpleNamespace(id="main", kind="main", line_ids=["a1", "a2", "b1"]),
        ]
    )
    stream, after, position, confidence, _ = ownership.display_anchor(
        _box(50, 20, 150, 32), layout, order
    )
    assert (stream, after, position, confidence) == ("main", "a1", 0, 0.9)


def _figure(fid, objects, captions=()):
    return SimpleNamespace(
        id=fid,
        page=1,
        name=f"name_{fid}",
        object_ids=list(objects),
        captions=list(captions),
        image=SimpleNamespace(file_name=f"{fid}.png"),
    )


def _region(rid, objects, box=(10, 10, 30, 20)):
    return SimpleNamespace(id=rid, object_ids=list(objects), bbox=_box(*box))


def test_figures_of_equation_evidence_only_are_converted():
    native = SimpleNamespace(
        objects=[
            _obj("bg", (0, 0, 100, 40), ops=("re",), fill=(0.9, 0.9, 0.9)),  # behind, first
            _obj("g1", (12, 12, 18, 18)),
            _obj("g2", (20, 12, 26, 18)),
            _obj("axis", (0, 50, 100, 51), ops=("l",)),
        ]
    )
    content = ownership.FigureContent(None, None, native)
    region = _region("e1", ["g1", "g2"])
    only = _figure("f1", ["bg", "g1", "g2"])
    chart = _figure("f2", ["g1", "g2", "axis"])
    captioned = _figure("f3", ["g1", "g2"], captions=["c"])
    assert content(only, [region]) == []
    assert content(chart, [region]) == ["1 drawing object(s) of its own"]
    assert content(captioned, [region]) == ["it has a caption"]
    decided = ownership.classify_figures([region], [only], content)
    assert decided["f1"][0] is True


class _Model(SimpleNamespace):
    def model_copy(self, update):
        return _Model(**{**vars(self), **update})


def test_the_final_archive_drops_converted_figures_and_renumbers():
    def record(fid, index):
        return _Model(id=fid, page=1, anchor=_Model(reading_index=index))

    figures = _Model(
        page=1,
        figures=[record("f1", 1), record("f2", 2)],
        page_credits=[_Model(proposed_figure_ids=["f1", "f2"])],
    )
    equations = SimpleNamespace(figure_conversions=[SimpleNamespace(figure_id="f1")])
    final = ownership.final_figures(figures, equations)
    assert [f.id for f in final.figures] == ["f2"]
    assert final.figures[0].anchor.reading_index == 1
    assert final.page_credits[0].proposed_figure_ids == ["f2"]
    assert [f.id for f in figures.figures] == ["f1", "f2"]  # the stage record is unchanged


def test_every_region_needs_an_owner():
    region = EquationRegion(
        id="e", page=1, bbox=_box(0, 0, 1, 1), presentation="inline", source="vector",
        object_ids=["o"], rules=["r"], confidence=0.5,
    )  # fmt: skip
    with pytest.raises(ValidationError, match="owner"):
        PageEquations(
            source_sha256="0" * 64, page=1, version="t", regions=[region],
            ownership=GlyphOwnership(objects=1, text_unit=0, equation_unit=0, figure=0,
                                     review=0, unowned=1),
        )  # fmt: skip


@pytest.fixture
def equation_pdf(tmp_path):
    return _equation_book(tmp_path / "equations.pdf")


def test_every_drawn_equation_has_an_owner_and_units_are_unchanged(equation_pdf, tmp_path):
    result = run_book(equation_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    for number in (1, 2):
        page = _page(result, number)
        equations = page["equations"]
        assert equations["ownership"]["unowned"] == 0
        assert equations["ownership"]["objects"] == sum(
            len(r["object_ids"]) for r in equations["regions"]
        )
        by_kind = {r["presentation"]: r for r in equations["regions"] if r["source"] == "vector"}
        inline, display = by_kind["inline"], by_kind["display"]
        assert inline["owner"]["kind"] == "text_unit"
        assert inline["owner"]["unit_id"] == inline["host"]["unit_id"]
        place = inline["owner"]["place"]
        spans = page["source"]["store"]["spans"]
        # Read after "The value" (its own visual line), before "is small.".
        assert spans[place["span_id"]]["raw_text"] == "The value"
        assert place["offset"] == len("The value")
        assert display["owner"]["kind"] == "equation_unit"
        (unit,) = equations["units"]
        assert unit["equation_id"] == display["id"] and unit["anchor"]["reading_index"] == 1
        anchor_line = unit["anchor"]["after_line_id"]
        assert anchor_line in page["line_spans"]
        text_owned = [r for r in equations["regions"] if r["source"] == "text"]
        assert all(r["owner"]["kind"] == "text_unit" for r in text_owned)
        # Units and lines are the list stage's own: equations add records only.
        unit_lines = [line for u in page["units"]["units"] for line in u["line_ids"]]
        assert sorted(unit_lines) == sorted(page["line_spans"])
    book = read_json(Path(result["output"]) / "book.json.gz")
    assert book["equations"]["ownership"]["unowned"] == 0
    assert book["equations"]["units"] == 2


def test_lettering_reversed_out_of_a_dark_shape_is_not_typeset_math():
    dark = _obj("logo_ground", (0, 0, 40, 40), ops=("re",), fill=(0.1, 0.2, 0.3))
    letters = [_obj(f"l{i}", (5 + 8 * i, 15, 11 + 8 * i, 25), fill=(1, 1, 1)) for i in range(3)]
    order = {o.id: i for i, o in enumerate([dark, *letters])}
    fills = [(0, dark)]
    white = (1.0, 1.0, 1.0)
    assert detect.reversed_out(letters, order, fills, [])
    # Reversed math in a shaded text area (a table header) is set among text of its colour.
    cell = _obj("cell", (50, 0, 90, 40), ops=("re",), fill=(0.1, 0.2, 0.3))
    fills.append((1, cell))
    assert not detect.reversed_out(letters, order, fills, [(_box(55, 10, 85, 20), white)])
    # Dark math on a light shaded cell is ordinary typeset math.
    light = _obj("light", (0, 0, 40, 40), ops=("re",), fill=(0.9, 0.9, 0.9))
    ink = [_obj("x", (5, 15, 11, 25))]
    assert not detect.reversed_out(ink, {"light": 0, "x": 1}, [(0, light)], [])


# Text-set math and mixed expressions -------------------------------------------------------


def _text_runs(text):
    from test_equations import _runs

    return _runs([(text, 10, False)])


def test_a_letter_applied_to_a_bracket_is_math_and_words_inside_belong_to_it():
    assert _text_runs("we need f(x) here") == ["f(x)"]
    assert _text_runs("Find P(A AND B) now") == ["P(A AND B)"]
    assert _text_runs("the student(s) and (a) list") == []
    assert _text_runs("so (1.5)(IQR) = 3") == ["(1.5)(IQR) = 3"]


def test_list_separators_end_an_expression_except_inside_brackets():
    assert _text_runs("F(1, 147) = 4.50, p < .001 here") == ["F(1, 147) = 4.50", "p < .001"]
    assert _text_runs("x = 2, y = 6.2 holds") == ["x = 2", "y = 6.2"]


def test_a_spaced_dash_is_a_minus_only_beside_a_relation():
    assert _text_runs("so x = 1 – 0.80 here") == ["x = 1 – 0.80"]
    assert _text_runs("in 1933 - 1944 and A – G") == []
    assert _text_runs("ranges 1914–1918 only") == []


def test_a_glued_modifier_symbol_is_an_operator():
    assert _text_runs("then e^(x) = 2 holds") == ["e^(x) = 2"]


def _draft(atoms, objects=(), part=False, rules=("r",)):
    return {
        "box": detect._union(a[0] for a in atoms),
        "objects": list(objects),
        "ranges": [] if objects else [("s", 0, len(atoms))],
        "line_ids": [] if objects else ["L"],
        "rules": [] if part else list(rules),
        "signals": {},
        "groups": frozenset(),
        "atoms": atoms,
        "part": part,
    }


def test_text_parts_join_a_drawn_part_through_an_operator_or_bracket():
    fraction = _draft([(_box(40, 0, 50, 14), None, True)], objects=["frac"])
    relation = _draft(
        [(_box(10, 4, 14, 12), "f", False), (_box(15, 4, 30, 12), "(", False),
         (_box(32, 4, 36, 12), "=", False)],
        part=True,
    )  # fmt: skip
    drafts = [fraction, relation]
    detect._join_mixed(drafts, SIZE)
    assert len(drafts) == 1 and "text_part" in drafts[0]["rules"]
    label = _draft([(_box(30, 4, 34, 12), "b", False)], part=True)  # "b." before a fraction
    drafts = [_draft([(_box(40, 0, 50, 14), None, True)], objects=["frac"]), label]
    detect._join_mixed(drafts, SIZE)
    assert len(drafts) == 2


def test_character_ranges_use_rendered_glyph_boxes():
    span = SimpleNamespace(raw_text="for 8 < x", bbox=_box(0, 0, 90, 10))
    glyphs = [_box(i * 4, 0, i * 4 + 3, 10) for i in range(9)]
    assert detect.range_box(span, 4, 9, None, glyphs) == _box(16, 0, 35, 10)
    assert detect.range_box(span, 4, 9, None).x0 == 40  # the even-share estimate


def test_a_letter_with_a_lowered_letter_span_is_a_base_and_script():
    from test_equations import _runs

    assert _runs([("b. H", 10, False), ("a", 7, True), (": ____", 10, False)]) == ["Ha"]
    # A long shifted span is other lettering, not a script.
    assert _runs([("e o", 10, False), ("H- efa (Haifa)", 7, True)]) == []


def test_a_separator_between_text_and_drawn_parts_keeps_them_apart():
    fraction = _draft([(_box(40, 0, 50, 14), None, True)], objects=["frac"])
    text = _draft([(_box(56, 4, 70, 12), "P", True)])
    comma = _box(51, 4, 53, 12)
    drafts = [fraction, text]
    detect._join_mixed(drafts, SIZE, [comma])
    assert len(drafts) == 2
    drafts = [_draft([(_box(40, 0, 50, 14), None, True)], objects=["frac"]), text]
    detect._join_mixed(drafts, SIZE)
    assert len(drafts) == 1
