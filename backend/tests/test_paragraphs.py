"""Step 9: paragraph units, continuations, hyphenation, inline runs and anchors (synthetic)."""

import shutil

import pytest
from test_cache_keys import closure
from test_furniture import HEBREW, LATIN, SOURCE, PageBuilder

from book_core.caching import PACKAGE, coverage_files
from book_core.evaluation.paragraphs import hyphen_scores, join_scores, paragraph_scores
from book_core.furniture.apply import apply_page
from book_core.furniture.cache import decide_book
from book_core.furniture.features import page_features
from book_core.paragraphs.anchors import move_anchors
from book_core.paragraphs.crosspage import page_join
from book_core.paragraphs.keys import (
    PARAGRAPH_ENTRY_POINTS,
    book_fingerprint,
    book_key_components,
    paragraph_code_digest,
    paragraph_scope_files,
)
from book_core.paragraphs.lexicon import Profile
from book_core.paragraphs.models import PageParagraphs
from book_core.paragraphs.page import build_page
from book_core.paragraphs.segment import PageSegmenter
from book_core.paragraphs.text import unit_text
from book_core.settings import Settings

PROFILE = {"pitch_by_size": {"10.0": 14.0}, "compounds": {}}


def band(builder, bid, y0, y1, lanes):
    """A band whose lanes are separated by gutters (as the layout validator requires)."""
    from book_core.layout.models import Band, Gutter, Lane
    from book_core.model.common import BBox

    lanes = [
        Lane(index=i, x0=a, x1=b, kind=k, line_count=1, confidence=0.8, reasons=["t"])
        for i, (a, b, k) in enumerate(lanes)
    ]
    gutters = [
        Gutter(x0=a.x1, x1=b.x0, y0=y0, y1=y1, left_items=1, right_items=1, ink_fraction=0,
               confidence=0.8, reasons=["t"])
        for a, b in zip(lanes, lanes[1:], strict=False)
    ]  # fmt: skip
    bid = f"p{builder.number}-{bid}"
    builder.bands.append(
        Band(id=bid, scope_id="page", bbox=BBox(x0=lanes[0].x0, y0=y0, x1=lanes[-1].x1, y1=y1),
             gutters=gutters, lanes=lanes,
             column_count=sum(lane.kind == "column" for lane in lanes),
             confidence=0.8, reasons=["t"])
    )  # fmt: skip
    return bid


def furnished_book(builders):
    """[(page, layout, PageFurniture)] for consecutive synthetic pages 1..n (one book)."""
    pages = [b.build() for b in builders]
    features = {p[1].page: page_features(*p) for p in pages}
    decisions = decide_book(features, {}, SOURCE)
    return [
        (page, layout, apply_page(page, layout, order, decisions.roles[layout.page],
                                  decisions.book.markers[layout.page - 1]))
        for page, layout, order in pages
    ]  # fmt: skip


def furnished(page_builder):
    """(page, layout, PageFurniture) for one synthetic page (a one-page book)."""
    page, layout, order = page_builder.build()
    decisions = decide_book({1: page_features(page, layout, order)}, {}, SOURCE)
    number = layout.page
    roles = decisions.roles[next(iter(decisions.roles))]
    furniture = apply_page(page, layout, order, roles, decisions.book.markers[0])
    assert furniture.page == number
    return page, layout, furniture


def built(page_builder, vocabulary=None, profile=PROFILE, **options):
    page, layout, furniture = furnished(page_builder)
    result = build_page(page, layout, furniture, profile, vocabulary, **options)
    return page, layout, result


def texts(page, layout, result, kinds=("paragraph",)):
    return [unit_text(page.store, layout, u) for u in result.units if u.kind in kinds]


def column(builder, prefix, x0, x1, rows, band=None, lane=0, kind="main_text", size=10.0):
    """rows: [(y, indent, text)] -> lines in one region."""
    lines = [
        builder.line(
            f"{prefix}{i}", x0 + indent, y, min(x1, x0 + indent + 0.52 * size * len(text)),
            text, size=size,
        )  # line width follows the text length, as in a real layout
        for i, (y, indent, text) in enumerate(rows)
    ]  # fmt: skip
    builder.region(prefix, kind, lines, band, lane)
    return lines


def test_indent_only_paragraphs():
    page = PageBuilder(1)
    rows = [
        (100, 18, "The first paragraph starts with an indent and runs on"),
        (114, 0, "over a second line of the same text that is long"),
        (128, 0, "and ends here with a full stop at the end."),
        (142, 18, "Another paragraph begins with the same indent"),
        (156, 0, "and continues on a full line of running text here"),
        (170, 0, "before it ends."),
    ]
    band = page.band("b", 100, 190, [(60, 550, "column")])
    column(page, "c", 60, 550, rows, band)
    p, layout, result = built(page)
    assert len(texts(p, layout, result)) == 2


def test_gap_only_paragraphs():
    page = PageBuilder(1)
    rows = [
        (100, 0, "A block paragraph without any indent runs on"),
        (114, 0, "and ends on its second line here."),
        (142, 0, "After a blank line another paragraph begins"),
        (156, 0, "and ends again."),
    ]
    band = page.band("b", 100, 170, [(60, 550, "column")])
    column(page, "c", 60, 550, rows, band)
    p, layout, result = built(page)
    assert texts(p, layout, result) == [
        "A block paragraph without any indent runs on and ends on its second line here.",
        "After a blank line another paragraph begins and ends again.",
    ]


def test_hanging_indent_entries():
    page = PageBuilder(1)
    rows = [
        (100, 0, "apple, 12, 40"),
        (114, 0, "banana, the fruit and its trade in the old ports, 3,"),
        (128, 14, "18, 77, 102; history of, 45"),
        (142, 14, "51, 60"),
        (156, 0, "cherry, 9"),
        (170, 0, "date palms in the desert oases of the south, 5,"),
        (184, 14, "17, 22"),
        (198, 0, "elder, 31"),
    ]
    band = page.band("b", 100, 210, [(60, 330, "column")])
    column(page, "c", 60, 330, rows, band)
    p, layout, result = built(page)
    units = texts(p, layout, result)
    assert len(units) == 5
    assert units[1].startswith("banana") and units[1].endswith("51, 60")


def test_drop_cap_joins_its_paragraph():
    page = PageBuilder(1)
    cap = page.line("cap", 60, 96, 84, "O", size=32.0)
    page.region("cap", "main_text", [cap], None, None)
    rows = [
        (100, 30, "nce upon a time the story began in a small town"),
        (114, 30, "near the river where everyone knew each other well"),
        (128, 0, "and the days were long."),
    ]
    band = page.band("b", 96, 140, [(60, 550, "column")])
    column(page, "c", 60, 550, rows, band)
    p, layout, result = built(page)
    seg = PageSegmenter(p, layout, furnished_order(result), PROFILE, None, None)
    lines = seg.lines
    decision = seg.decide(None, lines["p1-cap"], lines["p1-c0"], lines["p1-c1"])
    assert decision[0] is False and "drop cap" in decision[2][0]


def furnished_order(result):
    class _Furniture:
        order = result.order
        roles = []

    furniture = _Furniture()
    furniture.roles = [
        type("R", (), {"line_id": lid, "role": "content"})()
        for s in result.order.streams
        for lid in s.line_ids
    ]
    return furniture


def test_cross_column_continuation_and_break():
    page = PageBuilder(1)
    left = column(
        page, "l", 60, 290,
        [(100, 0, "The text of the first column runs"), (114, 0, "down to the bottom and the")],
        band(page, "b", 100, 130, [(60, 290, "column"), (320, 550, "column")]), 0,
    )  # fmt: skip
    right = column(
        page, "r", 320, 550,
        [(100, 0, "sentence goes on in the next one."), (114, 0, "It ends there.")],
        page.bands[-1].id, 1,
    )  # fmt: skip
    p, layout, result = built(page)
    units = [u for u in result.units if u.kind == "paragraph"]
    assert len(units) == 1 and [j.kind for j in units[0].joins].count("column") == 1
    assert {lid for u in units for lid in u.line_ids} == {x.id for x in left + right}


def _two_pages(first_rows, second_rows):
    builders = []
    for number, rows in ((1, first_rows), (2, second_rows)):
        builder = PageBuilder(number)
        column(builder, "a", 60, 550, rows, builder.band("b", 100, 130, [(60, 550, "column")]))
        builders.append(builder)
    (pa, la, fa), (pb, lb, fb) = furnished_book(builders)
    ra, rb = build_page(pa, la, fa, PROFILE), build_page(pb, lb, fb, PROFILE)
    furnitures = {id(la): fa, id(lb): fb}

    def factory(page, layout):
        return PageSegmenter(page, layout, furnitures[id(layout)], PROFILE, {}, {})

    return page_join((pa, la, ra.units), (pb, lb, rb.units), {}, factory)


def test_cross_page_continuation():
    join, candidate = _two_pages(
        [(100, 0, "A long paragraph runs to the very end of the page and")],
        [(100, 0, "continues at the top of the next page.")],
    )
    assert join is not None and join.join.kind == "page" and candidate["joined"]
    # A finished sentence followed by an indented new paragraph is not joined.
    join, candidate = _two_pages(
        [(100, 0, "A paragraph ends here on the first page.")],
        [(100, 20, "New paragraph after a full stop."), (114, 0, "It goes on here and ends.")],
    )
    assert join is None and candidate["joined"] is False


def test_break_hyphen_joins_and_real_compound_keeps():
    page = PageBuilder(1)
    rows = [
        (100, 0, "The new govern-"),
        (114, 0, "ment met the Austro-"),
        (128, 0, "Hungarian envoy and a self-"),
        (142, 0, "made man."),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 155, [(60, 550, "column")]))
    vocabulary = {"government": 4, "govern": 1, "ment": 1, "self": 9, "made": 7}
    profile = {**PROFILE, "compounds": {"self-made": 3}}
    p, layout, result = built(page, vocabulary, profile)
    (unit,) = [u for u in result.units if u.kind == "paragraph"]
    choices = [j.hyphen.choice for j in unit.joins if j.hyphen is not None]
    assert choices == ["join", "keep", "keep"]
    assert unit_text(p.store, layout, unit) == (
        "The new government met the Austro-Hungarian envoy and a self-made man."
    )
    # Raw spans are never rewritten: the raw view keeps every hyphen.
    assert unit_text(p.store, layout, unit, raw=True).count("-") == 3


def test_soft_hyphen_always_joins():
    page = PageBuilder(1)
    column(page, "c", 60, 550, [(100, 0, "the uni­"), (114, 0, "versity opened.")],
           page.band("b", 100, 130, [(60, 550, "column")]))  # fmt: skip
    p, layout, result = built(page)
    (unit,) = [u for u in result.units if u.kind == "paragraph"]
    assert unit.joins[0].hyphen.choice == "soft_join"
    assert unit_text(p.store, layout, unit) == "the university opened."


def test_right_to_left_paragraphs_use_the_right_edge():
    page = PageBuilder(1)
    lines = [
        page.line("h0", 60, 100, 532, HEBREW[0], direction="rtl"),  # indented from the right
        page.line("h1", 60, 114, 550, HEBREW[1], direction="rtl"),
        page.line("h2", 300, 128, 550, HEBREW[2], direction="rtl"),  # short last line
        page.line("h3", 60, 142, 532, HEBREW[0], direction="rtl"),
        page.line("h4", 60, 156, 550, HEBREW[1], direction="rtl"),
    ]
    page.band("b", 100, 170, [(60, 550, "column")])
    page.region("h", "main_text", lines, page.bands[-1].id, 0)
    p, layout, result = built(page)
    units = [u for u in result.units if u.kind == "paragraph"]
    assert [len(u.line_ids) for u in units] == [3, 2]


def test_mixed_language_paragraph_records_language_runs():
    pytest.importorskip("lingua")
    from book_core.paragraphs.cache import detector_for

    detector, _ = detector_for(Settings(), 10)
    page = PageBuilder(1)
    rows = [
        (100, 0, "La casa es muy grande y tiene un jardín con muchas flores rojas."),
        (114, 0, "The house is very large and it has a garden with many red flowers."),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 130, [(60, 550, "column")]))
    p, layout, result = built(page, detector=detector)
    (unit,) = [u for u in result.units if u.kind == "paragraph"]
    assert {run.language for run in unit.language_runs} == {"es", "en"}


def test_inline_style_runs_are_recorded_on_spans():
    page = PageBuilder(1)
    line = page.line("x", 60, 100, 550, "Plain text and more.")
    page.region("x", "main_text", [line], page.band("b", 100, 115, [(60, 550, "column")]), 0)
    span = page.spans[line.span_ids[0]]
    page.spans[span.id] = span.model_copy(update={"flags": 1 << 4})  # bold
    p, layout, result = built(page)
    (unit,) = [u for u in result.units if u.kind == "paragraph"]
    assert unit.style_runs and unit.style_runs[0].bold


def test_every_line_in_exactly_one_unit_and_furniture_apart():
    from test_furniture import synthetic_page

    page, layout, order = synthetic_page(1)
    decisions = decide_book({1: page_features(page, layout, order)}, {}, SOURCE)
    furniture = apply_page(page, layout, order, decisions.roles[1], decisions.book.markers[0])
    result = build_page(page, layout, furniture, PROFILE)
    lines = [lid for u in result.units for lid in u.line_ids]
    assert sorted(lines) == sorted(line.id for line in layout.lines)
    data = result.model_dump()
    data["units"][1]["line_ids"] = data["units"][0]["line_ids"] + data["units"][1]["line_ids"]
    with pytest.raises(ValueError):
        PageParagraphs.model_validate(data)


def test_anchor_moves_to_a_paragraph_boundary_and_keeps_evidence():
    page = PageBuilder(1)
    rows = [(100 + 14 * i, 0, LATIN[i % 2]) for i in range(6)]
    band_id = band(page, "b", 100, 190, [(60, 290, "column"), (320, 550, "sidebar")])
    column(page, "c", 60, 290, rows, band_id, 0)
    side = page.line("s", 330, 128, 540, "A sidebar beside the text")
    page.region("s", "sidebar", [side], band_id, 1)
    p, layout, furniture = furnished(page)
    result = build_page(p, layout, furniture, PROFILE, anchor_rule="nearest")
    for move in result.anchor_moves:
        unit = next(u for u in result.units if u.id == move.unit_id)
        assert move.after_line_id in (unit.line_ids[-1], None) or move.applied
        assert move.original_after_line_id in unit.line_ids
    kept = build_page(p, layout, furniture, PROFILE)
    assert all(not move.applied for move in kept.anchor_moves)
    moved, moves = move_anchors(furniture.order, result.units, "end")
    assert all(m.rule == "end" for m in moves)


def test_paragraph_metric_on_toy_gold():
    class Gold:
        units = [
            {"unit": 0, "kind": "paragraph", "pdf": [[1, 0, 3]]},
            {"unit": 1, "kind": "paragraph", "pdf": [[1, 3, 2]]},
            {"unit": 2, "kind": "heading", "pdf": [[1, 5, 1]]},
        ]

    perfect = {(1, i): "a" if i < 3 else "b" for i in range(5)}
    merged = {(1, i): "a" for i in range(5)}
    assert paragraph_scores(Gold, perfect)["exact_unit_match"] == 1.0
    scores = paragraph_scores(Gold, merged)
    assert scores["merge_errors"] == 1 and scores["boundary_recall"] == 0.0
    joins = join_scores(Gold, [("page", True, (1, 2), (1, 3)), ("page", False, (1, 1), (1, 2))])
    assert (
        joins["page"]["precision"] == 0.0
        and joins["page"]["joins_of_adjacent_reference_units"] == 1
    )
    assert hyphen_scores([("join", (1, 0), (1, 1))], {1: [7, 7]})["accuracy"] == 1.0


def test_profile_pitch_comes_from_the_book():
    from test_furniture import synthetic_page

    profile = Profile()
    for number in (7, 8):
        page, layout, order = synthetic_page(number)
        profile.add_page(page, layout, order)
    assert profile.freeze()["pitch_by_size"]["10.0"] == pytest.approx(14.0)


# ------------------------------------------------------------------ cache identity


@pytest.mark.parametrize("entry", PARAGRAPH_ENTRY_POINTS)
def test_paragraph_scope_covers_the_import_closure(entry):
    missing = closure(entry) - set(coverage_files("paragraphs"))
    assert not missing, f"Step 9 cache key ignores {sorted(missing)}"


def test_editing_any_paragraph_producer_changes_the_digest(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    original = paragraph_code_digest()
    assert paragraph_code_digest(copy) == original
    for relative in paragraph_scope_files(copy):
        target = copy / relative
        data = target.read_bytes()
        target.write_bytes(data + b"\n# edited\n")
        assert paragraph_code_digest(copy) != original, relative
        target.write_bytes(data)


def _components(**changes):
    base = {
        "paragraphs": "p" * 64,
        "furniture_key": "f" * 64,
        "vocabulary": {"casa": 3},
        "navigation": {7: {"line": "entry"}},
        "detector": {"name": "lingua", "version": "2.2.0"},
        "settings": Settings(),
        "config": {"anchor_rule": "keep"},
        "version": "paragraphs-1",
    }
    base.update(changes)
    return book_key_components(**base)


@pytest.mark.parametrize(
    "change",
    [
        {"paragraphs": "q" * 64},
        {"furniture_key": "g" * 64},
        {"vocabulary": {"casa": 4}},
        {"navigation": {7: {"line": "other"}}},
        {"detector": {"name": "lingua", "version": "2.3.0"}},
        {"settings": Settings(ocr_languages=["eng"])},
        {"config": {"anchor_rule": "nearest"}},
        {"version": "paragraphs-2"},
    ],
)
def test_every_paragraph_key_component_changes_the_key(change):
    assert book_fingerprint(_components(**change)) != book_fingerprint(_components())


def test_initial_at_line_start_never_splits_a_paragraph():
    page = PageBuilder(1)
    rows = [
        (100, 0, "Durante la audiencia, el equipo legal de George"),
        (114, 0, "W. Bush argumentó que la Corte Suprema de Florida no"),
        (128, 0, "tenía autoridad para ordenar un recuento manual."),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 140, [(60, 550, "column")]))
    p, layout, result = built(page)
    units = [u for u in result.units if u.kind in ("paragraph", "list_item_candidate")]
    assert len(units) == 1 and units[0].kind == "paragraph"


def test_lettered_list_with_sequence_evidence_splits():
    page = PageBuilder(1)
    rows = [
        (100, 0, "Choose one of the following options for the task:"),
        (114, 0, "A. Write a short essay about the main events"),
        (128, 0, "B. Draw a timeline of the period studied"),
        (142, 0, "C. Prepare a short talk for the class"),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 155, [(60, 550, "column")]))
    p, layout, result = built(page)
    items = [u for u in result.units if u.kind == "list_item_candidate"]
    assert len(items) == 3
    assert [unit_text(p.store, layout, u)[:2] for u in items] == ["A.", "B.", "C."]


def test_lone_letter_marker_counts_in_a_hanging_indent_block():
    page = PageBuilder(1)
    rows = [
        (100, 0, "apple, 12, 40"),
        (114, 0, "banana, the fruit and its trade in the old ports, 3,"),
        (128, 14, "18, 77, 102; history of, 45"),
        (142, 14, "51, 60"),
        (156, 0, "Q. cherry orchards, 9"),
        (170, 0, "date palms in the desert oases of the south, 5,"),
        (184, 14, "17, 22"),
    ]
    column(page, "c", 60, 330, rows, page.band("b", 100, 200, [(60, 330, "column")]))
    p, layout, result = built(page)
    starts = [unit_text(p.store, layout, u)[:2] for u in result.units
              if u.kind in ("paragraph", "list_item_candidate")]  # fmt: skip
    assert "Q." in starts
