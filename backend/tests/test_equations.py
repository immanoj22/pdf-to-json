"""Step 13a equations: detection, no invention, repair traceability, multilingual text,
cache closure and worker equality."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from pydantic import ValidationError
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.characters.models import GlyphEvidence, PageCharacterEvidence
from book_core.equations.models import CharacterRepair
from book_core.equations.repairs import page_repairs
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

# Two filled outlines, 7 units tall: drawn characters of different shapes.
GLYPHS = (
    [(0, 7), (2, 0), (4, 4), (6, 0), (8, 7), (4, 5)],
    [(0, 0), (6, 0), (6, 2), (2, 2), (6, 7), (0, 7)],
)


def _glyph(shape, x, y, scale=1.0, kind=0):
    points = [pymupdf.Point(x + px * scale, y + py * scale) for px, py in GLYPHS[kind]]
    shape.draw_polyline(points + [points[0]])
    shape.finish(fill=(0, 0, 0), color=None, closePath=True)


def _equation_book(path):
    with pymupdf.open() as document:
        for number in range(2):
            page = document.new_page(width=420, height=600)
            page.insert_text(
                (40, 60), "Results: p < .001 and F(1, 147) = 4.50 overall.", fontsize=10
            )
            page.insert_text((40, 80), "El niño comió más pan en la mañana.", fontsize=10)
            page.insert_text(
                (40, 100), "Ελληνικά κείμενα και Русский текст.", fontsize=10, fontname="china-s"
            )
            page.insert_text((40, 120), "Notes are cited in children", fontsize=10)
            page.insert_text((169, 116), "12", fontsize=6)
            page.insert_text((40, 150), "The value", fontsize=10)
            shape = page.new_shape()
            for i in range(3):
                _glyph(shape, 92 + 10 * i, 143, kind=i % 2)
            page.insert_text((128, 150), "is small.", fontsize=10)
            for i in range(3):  # a display fraction: glyphs above and below a bar
                _glyph(shape, 180 + 10 * i, 200, kind=i % 2)
                _glyph(shape, 180 + 10 * i, 214, kind=(i + 1) % 2)
            shape.draw_rect(pymupdf.Rect(178, 210, 210, 211))
            shape.finish(fill=(0, 0, 0), color=None)
            for i in range(4):  # an ornament: identical dots beside a heading
                shape.draw_circle(pymupdf.Point(150 + 9 * i, 285), 3)
                shape.finish(fill=(0.2, 0.6, 0.9), color=None)
            shape.commit()
            page.insert_text((40, 260), f"Closing text of page {number + 1}.", fontsize=10)
            page.insert_text((40, 288), "Applications", fontsize=10)
            page.insert_text((380, 560), "Note. Rotated table: *p < .05", fontsize=8, rotate=90)
        document.save(path)
    return path


@pytest.fixture
def equation_pdf(tmp_path):
    return _equation_book(tmp_path / "equations.pdf")


def _page(result, number=1):
    return read_json(Path(result["output"]) / f"page_{number:06d}.json.gz")


def _region_text(page, region):
    spans = page["source"]["store"]["spans"]
    return "".join(
        spans[r["span_id"]]["raw_text"][r["start"] : r["end"]] for r in region["span_refs"]
    )


def test_detects_text_vector_inline_and_display_equations(equation_pdf, tmp_path):
    result = run_book(equation_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = _page(result)
    regions = page["equations"]["regions"]
    texts = sorted(_region_text(page, r) for r in regions if r["source"] == "text")
    assert texts == ["F(1, 147) = 4.50", "p < .001", "p < .05"]  # last: a rotated line
    assert all(r["presentation"] == "inline" for r in regions if r["source"] == "text")
    vector = [r for r in regions if r["source"] == "vector"]
    assert sorted(r["presentation"] for r in vector) == ["display", "inline"]
    display = next(r for r in vector if r["presentation"] == "display")
    assert "rule_bar" in display["rules"] and len(display["object_ids"]) == 7
    inline = next(r for r in vector if r["presentation"] == "inline")
    assert inline["host"]["relation"] == "inside" and inline["host"]["unit_kind"] == "paragraph"
    assert all(r["review_required"] for r in regions)
    assert not [r for r in vector if r["bbox"]["y0"] > 270]  # the dot ornament is not math
    assert result["cache_keys"]["equations"] and result["source_hashes"] == 1


def test_note_references_and_multilingual_text_are_not_equations(equation_pdf, tmp_path):
    result = run_book(equation_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    page = _page(result)
    texts = " ".join(_region_text(page, r) for r in page["equations"]["regions"])
    for word in ("12", "niño", "Ελληνικά", "Русский"):
        assert word not in texts
    assert page["equations"]["repairs"] == [] and page["equations"]["character_flags"] == []


def test_no_invention_text_is_unchanged_and_references_resolve(equation_pdf, tmp_path):
    result = run_book(equation_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu")
    native = PyMuPDFExtractor("cpu").extract_object_page(equation_pdf, 1)
    page = _page(result)
    assert page["source"]["store"] == native.page.store.model_dump(mode="json")
    objects = {o.id for o in native.objects}
    for region in page["equations"]["regions"]:
        assert set(region["object_ids"]) <= objects
        for ref in region["span_refs"]:
            span = page["source"]["store"]["spans"][ref["span_id"]]
            assert 0 <= ref["start"] < ref["end"] <= len(span["raw_text"])
        assert not {"mathml", "latex", "text"} & set(region)


def _evidence(page_text, name, named, decoded):
    page = SimpleNamespace(
        source_sha256="0" * 64,
        store=SimpleNamespace(spans={"s1": SimpleNamespace(raw_text=page_text)}),
    )
    glyph = GlyphEvidence(
        offset=2,
        glyph_id=7,
        glyph_name=name,
        name_codepoint=named,
        decoded_codepoints=[ord(decoded)],
        font="Fixture",
        name_disagrees=True,
    )
    evidence = PageCharacterEvidence(
        source_sha256="0" * 64, page=1, version="t", candidates={"s1": [glyph]}
    )
    return page, evidence


class _Fonts:
    def __init__(self, confirms):
        self.confirms = confirms

    def maps(self, font, glyph_name, code):
        return self.confirms


def test_repair_needs_glyph_name_and_font_program_and_keeps_the_original():
    page, evidence = _evidence("x a = 1", "alpha", ord("α"), "a")
    repairs, flags = page_repairs(page, evidence, _Fonts(True), [])
    assert flags == [] and len(repairs) == 1
    repair = repairs[0]
    assert (repair.original, repair.corrected, repair.start, repair.end) == ("a", "α", 2, 3)
    assert repair.review_status == "needs_review" and len(repair.evidence) >= 2
    assert page.store.spans["s1"].raw_text == "x a = 1"  # the span store is never changed
    repairs, flags = page_repairs(page, evidence, _Fonts(False), [])
    assert repairs == [] and flags[0].proposed == "α"
    assert "the font program does not confirm the glyph name" in flags[0].reasons


def test_unnamed_disagreement_is_only_flagged():
    page, evidence = _evidence("x a = 1", "glyph7", None, "a")
    repairs, flags = page_repairs(page, evidence, _Fonts(True), [])
    assert repairs == [] and flags[0].proposed is None


def test_a_repair_must_change_the_character():
    with pytest.raises(ValidationError):
        CharacterRepair(
            id="r", span_id="s", start=0, end=1, original="a", corrected="a", glyph_id=1,
            glyph_name="a", font="F", evidence=["x", "y"], confidence=0.9,
        )  # fmt: skip


def test_workers_and_production_give_identical_equations(equation_pdf, tmp_path):
    serial = run_book(equation_pdf, tmp_path / "a_out", tmp_path / "a", workers=1, device="cpu")
    parallel = run_book(equation_pdf, tmp_path / "b_out", tmp_path / "b", workers=2, device="cpu")
    production = run_book(
        equation_pdf, tmp_path / "c_out", tmp_path / "c", mode="production", workers=2,
        device="cpu",
    )  # fmt: skip

    def files(result):
        root = Path(result["output"])
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    assert files(serial) == files(parallel) == files(production)
    assert _page(serial)["equations"]["regions"]


def test_equations_cache_closure_covers_its_imports():
    assert closure("equations/cache.py") <= set(caching.coverage_files("equations"))
    assert closure("book_run.py") <= set(caching.coverage_files("final"))


def test_missing_equations_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(
        caching.DEPENDENCIES, "final", ("lists", "metadata", "characters", "figures")
    )
    missing = closure("book_run.py") - set(caching.coverage_files("final"))
    assert "equations/cache.py" in missing


def _runs(parts):
    """Text runs of one synthetic line: [(text, size, raised)] spans set left to right."""
    from book_core.equations.text import line_runs

    spans, geometry, x = {}, {}, 0
    for index, (text, size, raised) in enumerate(parts):
        sid = f"s{index}"
        spans[sid] = SimpleNamespace(id=sid, raw_text=text, size=size, font="F")
        geometry[sid] = SimpleNamespace(origin=(x, 100 - (4 if raised else 0)), direction=(1, 0))
        x += 10 * len(text)
    line = SimpleNamespace(span_ids=list(spans), font_size=10, horizontal=True)
    store = SimpleNamespace(spans=spans)
    return [
        "".join(spans[s].raw_text[a:b] for s, a, b in run.ranges)
        for run in line_runs(store, line, geometry, frozenset())
    ]


def test_raised_marks_on_numbers_and_words_are_not_exponents():
    assert _runs([("mean 3.38", 10, False), ("b", 6, True), (" here", 10, False)]) == []
    assert _runs([("in children", 10, False), ("12", 6, True), (" note", 10, False)]) == []
    assert _runs([("area x", 10, False), ("2", 6, True), (" units", 10, False)]) == ["x2"]
    assert _runs([("so 10", 10, False), ("n", 6, True), (" + 1 = y", 10, False)]) == ["10n + 1 = y"]


def test_list_commas_and_prose_comparisons_are_not_equations():
    assert _runs([("TI-83, 83+, 84, 84+ calculators", 10, False)]) == []
    assert _runs([("mothers aged >35 years", 10, False)]) == []
    assert _runs([("(M = 12.52, SD = 3.1) here", 10, False)]) == ["(M = 12.52, SD = 3.1)"]
