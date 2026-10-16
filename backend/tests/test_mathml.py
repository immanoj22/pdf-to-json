"""Step 13c MathML: recognition paths, validation, confidence, fallback, never-invent,
client options, cache closure and worker equality."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_cache_keys import closure
from test_equations import _equation_book, _page

from book_core import caching
from book_core.book_run import run_book
from book_core.mathml import checks, layout, markup, paths, shapes
from book_core.mathml.decide import decide
from book_core.mathml.latex import from_latex, latex
from book_core.mathml.models import EquationMath, PageMath
from book_core.mathml.settings import MathSettings
from book_core.mathml.symbols import Symbol
from book_core.mathml.tree import Node, canonical, characters, token


def sym(char, x, y=100.0, size=10.0, kind="char", width=None, height=None, sid=None):
    """A symbol on baseline ``y`` (y downwards) of the given size; bars span ``width``."""
    width = width if width is not None else 0.55 * size
    height = height if height is not None else 0.7 * size
    if kind == "bar":
        box = (x, y, x + width, y + 0.06 * size)
    else:
        box = (x, y - height, x + width, y)
    return Symbol(sid or f"{char}{x}:{y}", char, kind, box, y, size, "drawn")


def build(symbols):
    tree, _ = layout.build(symbols)
    return tree


# --- layout (text and drawn paths share it) ----------------------------------------------


def test_scripts_numbers_and_operators_from_positions():
    symbols = [
        sym("x", 0),
        sym("2", 6, y=96, size=7),  # raised and smaller: a superscript
        sym("+", 12),
        sym("1", 20),
        sym(".", 25.5, width=1, height=1),
        sym("5", 27),
    ]
    tree = build(symbols)
    assert latex(tree) == "{x}^{2} + 1.5"
    assert [n.kind for n in tree.children] == ["sup", "operator", "number"]


def test_subscript_and_bracket_group_carry_scripts():
    tree = build([sym("s", 0), sym("x", 6, y=103, size=7)])
    assert latex(tree) == "{s}_{x}"
    tree = build(
        [sym("(", 0, height=9), sym("a", 5), sym(")", 11, height=9), sym("2", 16, y=95, size=7)]
    )
    assert tree.kind == "sup" and latex(tree.children[0]) == "( a )"


def test_fraction_radical_and_overline_from_bars():
    fraction = build(
        [sym("1", 2, y=95), sym(None, 0, y=97, kind="bar", width=9), sym("2", 2, y=106)]
    )
    assert latex(fraction) == r"\frac{1}{2}"
    radical = build(
        [
            sym("√", 0, width=6, height=10),
            sym(None, 6, y=90, kind="bar", width=12),
            sym("n", 7),
            sym("p", 13),
        ]
    )
    assert latex(radical) == r"\sqrt{n p}"
    over = build([sym(None, 0, y=91, kind="bar", width=6), sym("x", 0.5)])
    assert over.kind == "over" and over.accent and latex(over) == r"\overline{x}"


def test_bar_pieces_are_one_overline():
    tree = build(
        [
            sym(None, 0, y=91, kind="bar", width=3, sid="b1"),
            sym(None, 3, y=91, kind="bar", width=3, sid="b2"),
            sym("x", 0.5),
        ]
    )
    assert tree.kind == "over" and characters(tree) == ["x", "¯"]


def test_rows_of_a_display_become_a_table():
    tree = build([sym("a", 0), sym("=", 6), sym("b", 12), sym("c", 0, y=125)])
    assert tree.kind == "table" and len(tree.children) == 2


def test_unknown_glyph_never_gets_a_character():
    with pytest.raises(layout.Unknown):
        build([sym("x", 0), sym(None, 6)])
    reading = paths._layout("drawn", [sym("x", 0), sym(None, 6)])
    assert reading.tree is None and reading.problems == [layout.UNKNOWN]


def test_every_symbol_is_used_once():
    reading = paths._layout("text", [sym("a", 0), sym("+", 6), sym("b", 12)])
    assert reading.ok and reading.complete and reading.symbols == 3


# --- drawn path: shape table ---------------------------------------------------------------


def test_shape_decision_uses_context_votes_and_position():
    fold = checks.fold
    label = shapes.decide(
        "•", r"\bullet", None, {"baseline": {".": 12}}, lambda c: "".join(fold(c))
    )
    assert label.char == "." and "context votes overrule the isolated reading" in label.flags
    label = shapes.decide(
        "•", r"\bullet", None, {"baseline": {".": 9}, "axis": {"·": 6}}, lambda c: "".join(fold(c))
    )
    assert label.char == "." and label.by_position == {"axis": "·"}  # a product dot
    label = shapes.decide("x", "x", True, {}, lambda c: c)
    assert (label.char, label.italic, label.confidence) == ("x", True, shapes.ISOLATED_CONFIDENCE)
    assert shapes.decide(None, None, None, {}, lambda c: c).char is None


def test_isolated_reading_keeps_one_plain_character():
    assert shapes.isolated_reading(r"\mathbf{e}") == ("e", False)
    assert shapes.isolated_reading("x") == ("x", True)
    assert shapes.isolated_reading(r"\frac{1}{2}") == (None, None)


def test_unit_height_and_descent_are_learned_from_the_book():
    units = shapes.unit_heights({"a": [7.0, 7.1, 4.9, 7.0, 5.0]})
    assert units["a"] == pytest.approx(7.0, abs=0.1)
    rows = [[("a", (0, 93, 5, 100)), ("b", (6, 93, 11, 100)), ("p", (12, 93, 17, 102))]] * 3
    descent = shapes.descents(rows, {"a": 7, "b": 7, "p": 9}, 10.0)
    assert descent["p"] > 0.1 and abs(descent["a"]) < 0.05


# --- image path, validation ----------------------------------------------------------------


def test_image_path_reads_latex_and_reports_failures():
    reading = paths.image_path(r"\frac{a}{b}", "test")
    assert reading.ok and latex(reading.tree) == r"\frac{a}{b}"
    assert paths.image_path("", "test").problems
    assert "cut at its length limit" in paths.image_path("x", "test", truncated=True).problems[0]


def test_mathml_is_validated_against_mathml3_structure():
    good = markup.write(from_latex(r"x^{2} = \sqrt{y}"))
    assert markup.validate(good) == []
    ns = 'xmlns="http://www.w3.org/1998/Math/MathML"'
    assert "mfrac: 1 children, needs 2" in markup.validate(
        f"<math {ns}><mfrac><mi>a</mi></mfrac></math>"
    )
    assert any("not a MathML 3" in p for p in markup.validate(f"<math {ns}><blink/></math>"))
    assert markup.validate("<math><mi>a</math>")[0].startswith("not well-formed")
    assert not markup.balanced(from_latex("( a"))


def test_sympy_and_arithmetic_checks():
    assert checks.sympy_check(from_latex(r".81 \cdot \frac{9}{50} = .1458")) == (
        "parsed",
        "consistent",
    )
    assert checks.sympy_check(from_latex(r"\frac{1}{2} = 0.7")) == ("parsed", "inconsistent")
    assert checks.sympy_check(from_latex(r"z = \frac{x-\mu}{\sigma}")) == (
        "parsed",
        "not_applicable",
    )
    assert checks.sympy_check(from_latex(r"P(A \cup B)"))[0] == "not_applicable"


# --- decision, fallback, never-invent, client options --------------------------------------


def _region(source="vector", presentation="inline"):
    return SimpleNamespace(id="eq1", page=3, source=source, presentation=presentation)


def _reading(path, tex):
    reading = paths.Reading(path, tree=from_latex(tex), latex=tex, symbols=len(tex))
    reading.complete = True
    return reading


def test_agreeing_paths_are_confident_and_disagreement_is_flagged():
    record = decide(_region(), _reading("drawn", "x+1"), _reading("image", "x+1"), MathSettings())
    assert (record.agreement, record.review_status, record.output) == (
        "agree",
        "paths_agree",
        "mathml",
    )
    assert record.confidence == 0.95 and record.path == "drawn"
    record = decide(_region(), _reading("drawn", "x+1"), _reading("image", "x+7"), MathSettings())
    assert record.agreement == "disagree" and record.confidence < 0.95
    assert "position and image readings disagree" in record.flags
    assert record.review_status != "paths_agree"  # never presented as checked


def test_image_reading_alone_is_must_check_and_keeps_the_original():
    failed = paths.Reading("drawn", problems=[layout.UNKNOWN])
    record = decide(_region(), failed, _reading("image", "x+1"), MathSettings())
    assert record.review_status == "must_check" and record.output == "image"
    assert record.mathml is not None and record.path == "image"
    with pytest.raises(ValidationError):
        record.model_copy(update={"output": "mathml"}).model_validate(
            record.model_copy(update={"output": "mathml"}).model_dump()
        )
    nothing = decide(_region(), failed, None, MathSettings())
    assert (nothing.mathml, nothing.review_status, nothing.output) == (None, "must_check", "image")


def test_text_set_math_stays_text_unless_set_in_a_math_font_or_the_client_asks():
    reading = _reading("text", "p<.001")
    plain = _region("text")
    record = decide(plain, reading, None, MathSettings())
    assert record.output == "text" and record.mathml  # MathML stored, text used
    assert record.review_status == "needs_review"  # no image reading, no disagreement flag
    math_font = SimpleNamespace(**vars(plain), signals={"math_font": True}, rules=["math_font"])
    assert decide(math_font, reading, None, MathSettings()).output == "mathml"
    assert decide(math_font, reading, None, MathSettings(text_set_math="text")).output == "text"
    client = MathSettings(text_set_math="mathml")
    assert decide(plain, reading, _reading("image", "p<.001"), client).output == "mathml"


def test_must_check_records_need_their_fallback_image_on_the_page():
    record = decide(_region(), paths.Reading("drawn", problems=["x"]), None, MathSettings())
    with pytest.raises(ValidationError):
        PageMath(source_sha256="a" * 64, page=3, version="v", equations=[record])


def test_fallback_pattern_is_validated():
    assert MathSettings(fallback_pattern="eq_{label}_{n:02d}").fallback_pattern
    with pytest.raises(ValidationError):
        MathSettings(fallback_pattern="eq_{page}")
    with pytest.raises(ValidationError):
        MathSettings(fallback_unlabelled_pattern="eq_{label}_{n}")


def test_comparison_folds_variants_but_not_content():
    a = canonical(from_latex("a-b"), checks.fold)
    b = canonical(Node("row", children=(token("a"), token("−"), token("b"))), checks.fold)
    assert a == b
    assert canonical(from_latex("a-c"), checks.fold) != b


def test_record_paths_agree_only_with_agreement():
    with pytest.raises(ValidationError):
        EquationMath(
            equation_id="e", page=1, source="vector", presentation="inline", agreement="single",
            confidence=0.9, review_status="paths_agree", output="text",
        )  # fmt: skip


# --- stage integration ----------------------------------------------------------------------


class FakeReader:
    """A formula reader that answers every image with the same LaTeX (no model)."""

    def __init__(self, answer=r"\frac{a}{b}"):
        self.answer = answer
        self.recognizer = SimpleNamespace(identity={"recognizer": "fake", "answer": answer})

    def read(self, png):
        return {
            "latex": self.answer,
            "truncated": False,
            "image_sha256": hashlib.sha256(png).hexdigest(),
        }


@pytest.fixture
def equation_pdf(tmp_path):
    return _equation_book(tmp_path / "equations.pdf")


def _math(result, number=1):
    return _page(result, number)["mathml"]


def test_stage_records_every_region_and_falls_back_without_models(equation_pdf, tmp_path):
    result = run_book(equation_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = _page(result)
    regions = {r["id"] for r in page["equations"]["regions"]}
    records = {e["equation_id"]: e for e in page["mathml"]["equations"]}
    assert regions and set(records) == regions
    assert any("Formula recognition extras" in w for w in result["warnings"])
    for record in records.values():
        if record["source"] == "text":
            assert record["output"] == "text"
        else:  # drawn glyphs cannot be read without the models: never invented
            assert record["review_status"] == "must_check" and record["output"] == "image"
            assert record["fallback_image"]["file_name"].startswith("page_")
            assert (
                Path(result["output"]) / "images" / record["fallback_image"]["file_name"]
            ).exists()


def test_reference_style_parts_and_a_supplied_reader(equation_pdf, tmp_path):
    settings = MathSettings(mixed_expressions="reference", text_set_math="mathml")
    result = run_book(
        equation_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu",
        math_settings=settings, formula_reader=FakeReader(),
    )  # fmt: skip
    book = _page(result)["mathml"]
    assert book["equations"]
    assert all(r["readings"] for r in book["equations"])
    assert any(any(x["path"] == "image" for x in r["readings"]) for r in book["equations"])


def test_workers_and_production_give_identical_mathml(equation_pdf, tmp_path):
    def files(result):
        root = Path(result["output"])
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    reader = FakeReader("x")
    serial = run_book(
        equation_pdf, tmp_path / "a_out", tmp_path / "a", workers=1, device="cpu",
        formula_reader=reader,
    )  # fmt: skip
    parallel = run_book(
        equation_pdf, tmp_path / "b_out", tmp_path / "b", workers=2, device="cpu",
        formula_reader=reader,
    )  # fmt: skip
    assert files(serial) == files(parallel)
    assert _math(serial)["equations"]


def test_mathml_cache_closure_covers_its_imports():
    assert closure("mathml/cache.py") <= set(caching.coverage_files("mathml"))
    assert closure("mathml/recognition.py") <= set(caching.coverage_files("formula"))
    assert closure("book_run.py") <= set(caching.coverage_files("final"))


def test_missing_mathml_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(
        caching.DEPENDENCIES, "final", ("lists", "metadata", "characters", "figures", "equations")
    )
    missing = closure("book_run.py") - set(caching.coverage_files("final"))
    assert "mathml/cache.py" in missing


# --- later rules: rotated lines, upright crops, comparison tolerance ------------------------


def test_rotated_text_is_laid_out_in_its_own_frame():
    from book_core.mathml.symbols import to_line_frame

    up = (0.0, -1.0)  # written bottom to top (a quarter turn counter-clockwise)
    # "x2" set upwards: x at the bottom, its raised 2 further up and to the left of the line.
    x = Symbol(
        "x", "x", "char", (96, 200, 103, 206), 0, 10, "text", origin=(103, 206), direction=up
    )
    two = Symbol("2", "2", "char", (93, 192, 98, 197), 0, 7, "text", origin=(98, 197), direction=up)
    tree = build(to_line_frame([x, two]))
    assert latex(tree) == "{x}^{2}"


def test_crops_of_rotated_lines_are_turned_upright():
    import numpy as np

    from book_core.mathml.images import _upright

    crop = np.zeros((10, 30, 3), np.uint8)
    assert _upright(crop, (1.0, 0.0)).shape == (10, 30, 3)
    assert _upright(crop, (0.0, -1.0)).shape == (30, 10, 3)
    assert _upright(crop, (0.0, 1.0)).shape == (30, 10, 3)


def test_comparison_ignores_end_punctuation_and_empty_scripts():
    from book_core.mathml.decide import compare

    assert compare(from_latex("p<.01"), from_latex("p<.01."))[0]
    assert compare(from_latex("F(1)"), from_latex("F_{}(1)"))[0]
    assert not compare(from_latex("p<.01"), from_latex("p<.05"))[0]


def test_a_minus_bar_high_above_the_base_opens_an_exponent():
    tree = build(
        [sym("e", 0), sym(None, 6, y=94, kind="bar", width=3, sid="m"), sym("x", 9.5, y=96, size=7)]
    )
    assert tree.kind == "sup" and latex(tree) == "{e}^{− x}"


def test_rules_in_pieces_and_radical_signs_count_as_used_symbols():
    pieces = [
        sym(None, 0, y=91, kind="bar", width=3, sid="b1"),
        sym(None, 3, y=91, kind="bar", width=3, sid="b2"),
        sym("x", 0.5),
    ]
    assert paths._layout("drawn", pieces).complete
    radical = [
        sym("√", 0, width=6, height=10),
        sym(None, 6, y=90, kind="bar", width=12),
        sym("n", 7),
    ]
    assert paths._layout("drawn", radical).complete


def test_invalid_reading_markup_is_not_recorded_as_mathml():
    from book_core.mathml.tree import Node

    empty = paths.Reading("image", tree=Node("row"), latex="{}^{}", symbols=0)
    record = decide(_region(), _reading("drawn", "x"), empty, MathSettings())
    image = next(r for r in record.readings if r.path == "image")
    assert image.mathml is None and any("no token" in p for p in image.problems)


def test_an_overline_compares_equal_whatever_bar_character_or_accent_flag():
    from book_core.mathml.decide import compare
    from book_core.mathml.tree import Node

    drawn = Node("over", children=(token("x"), token("¯")), accent=True)
    for source in (r"\bar{x}", r"\overline{x}", r"\overline{{x}}"):
        assert compare(drawn, from_latex(source))[0], source
    assert not compare(drawn, from_latex(r"\hat{x}"))[0]
    assert not compare(drawn, from_latex(r"\overline{y}"))[0]
