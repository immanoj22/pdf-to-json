"""Regressions for defects established by the Step 17b rendered-page audit."""

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from test_assembly import _span
from test_continuity import _book, _run

from book_core.assembly import schema as S
from book_core.assembly.assemble import navigation_of
from book_core.assembly.build import Context, PageBuild, sid
from book_core.assembly.fonts import FontTable
from book_core.assembly.links import PyMuPDFLinkExtractor
from book_core.assembly.profile import load_profile
from book_core.cache_store import read_json
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.models import VisualLine
from book_core.model.spans import ExtractedPage


@pytest.fixture
def archive_payload(tmp_path):
    root = tmp_path
    result = _run(_book(root / "book.pdf"), root / "out", root / "cache", 1)
    return read_json(Path(result["output"]) / "page_000001.json.gz")


def build_page(payload):
    fonts = FontTable()
    fonts.add(ExtractedPage.model_validate(payload["source"]).store)
    fonts.freeze()
    ctx = Context(profile=load_profile(), fonts=fonts, language=None, book={}, headings={},
                  run_in={}, styled={}, lists={}, navigation={}, markers={}, zones={})
    page = PageBuild(ctx, 1, payload, None, {})
    unit = next(u for u in page.units.values() if u.kind == "paragraph")
    return ctx, page, unit


@pytest.mark.parametrize("navigation", ["index", "glossary"])
def test_letter_heading_in_navigation_is_a_divider(archive_payload, monkeypatch, navigation):
    ctx, page, unit = build_page(archive_payload)
    ctx.navigation[1] = navigation
    ctx.headings[unit.id] = dict(level=2, role="subsection", level_method="model",
                                reasons=[], confidence=1, review_required=False)
    # One standalone source line, no locators. Heading style must not win over
    # the established alphabetic navigation context.
    unit = unit.model_copy(update={"line_ids": unit.line_ids[:1]})
    built, content = page.text(unit.line_ids, unit=unit)
    content = content.model_copy(update={"text": "Ch", "spans": [], "source_runs": []})
    monkeypatch.setattr(page, "text", lambda *a, **kw: (built, content))
    node = page.unit_node(unit)
    assert node.type == "index_divider" and node.content.text == "Ch"
    ctx.navigation.clear()
    assert page.unit_node(unit).type == "heading"


def test_outline_only_names_published_headings():
    divider = S.IndexDivider(id=sid("letter"), pages=[1], order=0,
                             provenance=S.Provenance(stages=["assembly"]),
                             content=S.TextContent(text="A"))
    structure = {"toc_links": [], "headings": [dict(run_in=[], unit_ids=["letter"],
                 level=2, role="subsection", page=1)],
                 "sections": [dict(id="section", zone="rear", kind="index", first_page=1,
                                    last_page=1, heading_id="letter")]}
    nav = navigation_of(structure, None, [divider])
    assert nav.outline == [] and nav.sections[0].heading is None


def test_cell_ownership_supersedes_old_figure_role_and_keeps_other_flags(archive_payload):
    ctx, page, unit = build_page(archive_payload)
    unit = unit.model_copy(update={"kind": "figure_text", "review_required": True})
    page.original[unit.id] = unit
    cell = SimpleNamespace(content=[SimpleNamespace(kind="paragraph", unit_id=unit.id,
                                                    line_ids=unit.line_ids)])
    (node,) = page.cell_content(cell, None)
    assert node.role == "table_text"
    assert "tables" in node.provenance.stages
    assert not any(flag.startswith("figure:") for flag in node.flags)
    assert any(flag.startswith("structure:") for flag in node.flags)
    outside = page.unit_node(unit)
    assert outside.role == "figure_text" and any(f.startswith("figure:") for f in outside.flags)
    assert outside.id == node.id and outside.content == node.content and outside.refs == node.refs


def test_underlines_need_straight_paths_and_cannot_be_rectangle_edges(tmp_path):
    source = tmp_path / "paths.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        words = ["straight", "river", "curve", "border", "filled", "inside"]
        for i, word in enumerate(words):
            y = 60 + i * 35
            width = pymupdf.get_text_length(word, fontsize=10)
            page.insert_text((40, y), word, fontsize=10)
            if word in {"straight", "inside"}:
                page.draw_line((40, y + 2), (40 + width, y + 2), width=.5)
            elif word == "river":
                page.draw_polyline([(40, y + 2), (40 + width / 2, y + 2.7),
                                    (40 + width, y + 2)], closePath=False, width=.5)
            elif word == "curve":
                page.draw_bezier((40, y + 2), (40 + width / 3, y + 2.5),
                                 (40 + 2 * width / 3, y + 2.5), (40 + width, y + 2), width=.5)
            elif word == "border":
                page.draw_rect((40, y - 10, 40 + width, y + 2), fill=(.2, .4, .6))
                # Some producers emit a separate stroke over the filled box edge.
                page.draw_line((40, y + 2), (40 + width, y + 2), width=.5)
            elif word == "filled":
                page.draw_rect((40, y + 2, 40 + width, y + 2.5), fill=(0, 0, 0), color=None)
            if word == "inside":
                page.draw_rect((35, y - 15, 50 + width, y + 10))
        doc.save(source)
    native = PyMuPDFExtractor("cpu").extract_object_page(source, 1)
    marks = PyMuPDFLinkExtractor("cpu").extract_marks(source, 1, native.page.store, [])
    marked = {native.page.store.spans[r.span].raw_text[r.start:r.end] for r in marks.underlines}
    assert marked == {"straight", "filled", "inside"}


@pytest.mark.parametrize("angle", [90, 270, 37])
def test_rotated_label_letters_are_not_equation_scripts(angle):
    from book_core.equations.text import line_runs

    # Mixed sizes on a native label. Positions follow its own writing axis;
    # page-axis baseline differences must not split a word into math operands.
    radians = math.radians(angle)
    dx, dy = math.cos(radians), -math.sin(radians)
    spans, geometry = {}, {}
    for i, char in enumerate(("R", "i")):
        key = f"s{i}"
        spans[key] = SimpleNamespace(id=key, raw_text=char, size=10 if i == 0 else 8, font="F")
        geometry[key] = SimpleNamespace(origin=(100 + 6 * i * dx - 4 * i * dy,
                                                100 + 6 * i * dy + 4 * i * dx),
                                         direction=(dx, dy))
    line = VisualLine(id="label", span_ids=list(spans), source_line_ids=["native-label"],
                      bbox=_span("box", "Ri").bbox, baseline_start=(100, 100),
                      baseline_end=(100 + 12 * dx, 100 + 12 * dy), direction=(dx, dy),
                      rotation=angle, writing_mode="horizontal", font_size=10,
                      visible=True, inside_content=True)
    assert line_runs(SimpleNamespace(spans=spans), line, geometry, frozenset()) == []
    # Mutation sensitivity: treating this geometry as horizontal invents an equation.
    assert line_runs(SimpleNamespace(spans=spans), line.model_copy(update={"rotation": 0}),
                     geometry, frozenset())


@pytest.mark.parametrize("angle", [90, 270, 37])
def test_interleaved_rotated_source_lines_reconstruct_without_split_tokens(angle):
    from collections import Counter

    from book_core.assembly.lossless import compare
    from book_core.assembly.text import build_text, ordered_spans
    from book_core.model.spans import SourceLine, SpanStore

    # Layout pieces interleave letters from two labels. Native source order is
    # explicit and survives cache key sorting, independently of page geometry.
    dx, dy = math.cos(math.radians(angle)), -math.sin(math.radians(angle))
    spans, lines = {}, []
    for j, word in enumerate(("River", "North")):
        ids = []
        for i, char in enumerate(word):
            key = f"{j}-{9-i}"  # deliberately opposite to serialized key order
            box = _span(key, char).bbox
            box = box.model_copy(update={"x0": 100 + i * 6 * dx + j * 30,
                                          "y0": 100 + i * 6 * dy})
            box = box.model_copy(update={"x1": box.x0 + 5, "y1": box.y0 + 10})
            spans[key] = _span(key, char).model_copy(update={"line_id": f"l{j}", "bbox": box})
            ids.append(key)
        lines.append(SourceLine(id=f"l{j}", page=1, bbox=box, span_ids=ids))
    store = SpanStore(spans=spans, lines=lines)
    store = SpanStore.model_validate_json(json.dumps(store.model_dump(), sort_keys=True))
    pieces = [(f"piece{i}", [(line.span_ids[i], None, None) for line in lines]) for i in range(5)]
    content = build_text(pieces, ordered_spans(store)).content
    assert content.text == "River\nNorth"
    result = compare({"content": [{"type": "paragraph", "content": content.model_dump()}],
                      "furniture": [], "suppressed": []}, Counter({"River": 1, "North": 1}))
    assert (result["missing"], result["extra"]) == (0, 0)
