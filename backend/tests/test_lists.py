"""Step 11: lists, definitions, glossary and index entries (synthetic), metrics and keys."""

import shutil
import unicodedata
from types import SimpleNamespace

import pytest
from test_cache_keys import closure
from test_furniture import HEBREW, PageBuilder
from test_paragraphs import band, built, column, furnished_book
from test_structure import Book, decide

from book_core.caching import PACKAGE, coverage_files
from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.lists import (
    Ours,
    cross_page_scores,
    definition_scores,
    index_scores,
    list_item_scores,
)
from book_core.lists.cache import _link_pages, _summary
from book_core.lists.keys import (
    LISTS_ENTRY_POINTS,
    book_fingerprint,
    book_key_components,
    lists_code_digest,
    lists_scope_files,
)
from book_core.lists.lines import read_marker
from book_core.lists.page import PageContext, build_page_lists
from book_core.model.spans import TextSpan
from book_core.paragraphs.page import build_page
from book_core.paragraphs.text import unit_text
from book_core.reading_order.graph import check
from book_core.settings import Settings

PROFILE = {"pitch_by_size": {"10.0": 14.0}, "compounds": {}}


def rich(builder, lid, x0, y, parts, size=10.0, direction="ltr"):
    """A line of several spans: parts = [(text, bold)]; widths follow the text length."""
    text = "".join(t for t, _ in parts)
    line = builder.line(lid, x0, y, x0 + 0.52 * size * len(text), text, size=size,
                        direction=direction)  # fmt: skip
    first = builder.spans.pop(line.span_ids[0])
    ids, x = [], x0
    for index, (piece, bold) in enumerate(parts):
        width = 0.52 * size * len(piece)
        sid = f"{first.id}-{index}"
        builder.spans[sid] = TextSpan(
            id=sid, line_id=first.line_id, page=first.page, raw_text=piece,
            text=unicodedata.normalize("NFKC", piece),
            bbox=first.bbox.model_copy(update={"x0": x, "x1": x + width}),
            font="Serif-Bold" if bold else "Serif", size=size, color=0, flags=16 if bold else 0,
            text_direction=direction, provenance=first.provenance,
        )  # fmt: skip
        ids.append(sid)
        x += width
    new = line.model_copy(update={"span_ids": ids})
    builder.lines[builder.lines.index(line)] = new
    source = next(s for s in builder.source_lines if s.id == first.line_id)
    builder.source_lines[builder.source_lines.index(source)] = source.model_copy(
        update={"span_ids": ids}
    )
    return new


def lists_of(page_builder, navigation=None, **context):
    page, layout, step9 = built(page_builder, profile=PROFILE)
    result, lists = build_page_lists(page, layout, step9, PageContext(navigation=navigation,
                                                                      **context))  # fmt: skip
    assert check(result.order, layout) == []
    return page, layout, result, lists


def items(page, layout, result, kinds=("list_item",)):
    """(text with whitespace collapsed, unit) for units of the given kinds."""
    return [(" ".join(unit_text(page.store, layout, u).split()), u) for u in result.units
            if u.kind in kinds]  # fmt: skip


def test_markers_are_read_with_type_value_and_punctuation():
    assert read_marker("•\tApples").type == "bullet"
    assert (read_marker("(3) Pears").value, read_marker("(3) Pears").punctuation) == (
        3, "parentheses")  # fmt: skip
    assert read_marker("01 \tIntroduction").padded
    roman = read_marker("iv. Fourth")
    assert roman.ambiguous and roman.type == "lower_roman" and roman.value == 4
    assert read_marker("1776 was a year") is None  # a year is not a marker
    assert read_marker("١. عنصر").value == 1  # Arabic-Indic digits


def test_nested_bullets_and_hanging_continuations():
    page = PageBuilder(1)
    rows = [
        (100, 0, "The list below has two levels of bullets:"),
        (128, 0, "• First topic of the list"),
        (142, 12, "that continues on a second line"),
        (156, 18, "◦ A detail under the first topic"),
        (170, 18, "◦ Another detail under it"),
        (184, 0, "• Second topic of the list"),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 200, [(60, 550, "column")]))
    p, layout, result, lists = lists_of(page)
    found = items(p, layout, result)
    assert [t for t, _ in found] == [
        "• First topic of the list that continues on a second line",
        "◦ A detail under the first topic", "◦ Another detail under it",
        "• Second topic of the list",
    ]  # fmt: skip
    assert [u.level for _, u in found] == [1, 2, 2, 1]
    nested = next(lst for lst in lists if lst.level == 2)
    assert nested.parent_item_id == found[0][1].id and nested.kind == "bulleted"
    assert found[0][1].marker.type == "bullet" and found[0][1].marker.refs


def test_numbered_list_restarts_and_records_start_value():
    page = PageBuilder(1)
    rows = [
        (100, 0, "1. Read the source carefully"),
        (114, 0, "2. Underline the key words"),
        (128, 0, "3. Write a short summary"),
        (156, 0, "Then answer the questions below."),
        (184, 0, "1. Who wrote the source?"),
        (198, 0, "2. When was it written?"),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 210, [(60, 550, "column")]))
    p, layout, result, lists = lists_of(page)
    numbered = [lst for lst in lists if lst.kind == "numbered"]
    assert [(lst.start, len(lst.item_ids)) for lst in numbered] == [(1, 3), (1, 2)]
    assert numbered[1].role == "questions"


def test_numbered_list_continues_in_the_next_column_without_nesting():
    page = PageBuilder(1)
    bid = band(page, "b", 100, 160, [(60, 290, "column"), (320, 550, "column")])
    left = column(page, "l", 60, 290, [(100, 0, "1. Pay the veterans what we owe"),
                                       (114, 0, "2. Educate all children with the same")],
                  bid, 0)  # fmt: skip
    right = column(page, "r", 320, 550, [(100, 0, "opportunities in every school"),
                                         (128, 0, "3. Raise the revenue from the largest"),
                                         (142, 0, "fortunes of the country")],
                   bid, 1)  # fmt: skip
    assert left and right
    p, layout, result, lists = lists_of(page)
    (numbered,) = [lst for lst in lists if lst.kind == "numbered"]
    assert len(numbered.item_ids) == 3 and numbered.level == 1


def test_lettered_list_with_sequence_evidence():
    page = PageBuilder(1)
    rows = [
        (100, 0, "Choose one of the following options for the task:"),
        (114, 0, "A. Write a short essay about the main events"),
        (128, 0, "B. Draw a timeline of the period studied"),
        (142, 0, "C. Prepare a short talk for the class"),
        (170, 0, "W. Bush argued the case in a long speech."),
    ]
    column(page, "c", 60, 550, rows, page.band("b", 100, 185, [(60, 550, "column")]))
    p, layout, result, lists = lists_of(page)
    (lettered,) = [lst for lst in lists if lst.kind == "lettered"]
    assert lettered.marker_type == "upper_alpha" and lettered.start == 1
    assert len(lettered.item_ids) == 3  # the initial "W." is no list item


def index_page(number=1):
    page = PageBuilder(number)
    rows = [
        (100, 0, "apple, 12, 40"),
        (114, 14, "red varieties, 14"),
        (128, 14, "green varieties, 15–16"),
        (142, 0, "banana, the fruit and its trade in the old ports, 3,"),
        (156, 14, "18, 77, 102"),
        (170, 0, "cherry, 9, see also Fruit"),
        (184, 0, "date palms in the desert oases of the south, 5,"),
        (198, 14, "17, 22"),
    ]
    column(page, "c", 60, 330, rows, page.band("b", 100, 210, [(60, 330, "column")]))
    return page


def test_hanging_indent_index_with_sub_entries_and_locators():
    labels = {"12": [20], "14": [22], "15": [23], "16": [24], "9": [17]}
    p, layout, result, lists = lists_of(index_page(), "index", label_pages=labels)
    found = items(p, layout, result, ("index_entry",))
    assert [(t, u.level) for t, u in found] == [
        ("apple, 12, 40", 1), ("red varieties, 14", 2), ("green varieties, 15–16", 2),
        ("banana, the fruit and its trade in the old ports, 3, 18, 77, 102", 1),
        ("cherry, 9, see also Fruit", 1),
        ("date palms in the desert oases of the south, 5, 17, 22", 1),
    ]  # fmt: skip
    apple, green, cherry = found[0][1], found[2][1], found[4][1]
    assert [loc.target_page for loc in apple.locators] == [20, None]
    assert (green.locators[0].kind, green.locators[0].target_page,
            green.locators[0].end_target_page) == ("range", 23, 24)  # fmt: skip
    assert [loc.kind for loc in cherry.locators] == ["page", "cross_reference"]
    assert lists[0].kind == "index"


def glossary_page(number=1):
    page = PageBuilder(number)
    left, refs, right = [], [], []
    entries = [
        (100, "casa", " vivienda de una familia que vive", "house", " a home for one family"),
        (128, "río", " corriente de agua que fluye", "river", " a stream of flowing water"),
        (156, "valle", " tierra baja entre montes", "valley", " low land between hills"),
    ]
    for i, (y, term, definition, term_en, definition_en) in enumerate(entries):
        left.append(rich(page, f"l{i}", 60, y, [(term + " ", True), (definition, False)]))
        left.append(page.line(f"l{i}b", 69, y + 12, 200, "junto a otras casas"))
        refs.append(page.line(f"r{i}", 250, y + 6, 290, f"(pág. {i + 10})"))
        right.append(rich(page, f"e{i}", 320, y, [(term_en + " ", True),
                                                  (definition_en, False)]))  # fmt: skip
    bid = band(page, "b", 100, 190, [(60, 240, "column"), (250, 300, "column"),
                                     (320, 550, "column")])  # fmt: skip
    page.region("left", "main_text", left, bid, 0)
    page.region("refs", "main_text", refs, bid, 1)
    page.region("right", "main_text", right, bid, 2)
    return page


def test_bilingual_glossary_rows_read_entry_by_entry():
    p, layout, result, lists = lists_of(glossary_page(), "glossary")
    found = items(p, layout, result, ("definition_entry",))
    assert [t for t, _ in found] == [
        "casa vivienda de una familia que vive junto a otras casas (pág. 10)",
        "house a home for one family",
        "río corriente de agua que fluye junto a otras casas (pág. 11)",
        "river a stream of flowing water",
        "valle tierra baja entre montes junto a otras casas (pág. 12)",
        "valley low land between hills",
    ]  # fmt: skip
    assert all(u.term for _, u in found)
    assert result.order_changes and result.order_changes[0].choice == "entry_by_entry"
    assert lists[0].kind == "glossary"


def test_definition_run_in_a_note_box():
    page = PageBuilder(1)
    lines = [
        rich(page, "d0", 60, 100, [("tariff ", True), ("a tax on imported goods that", False)]),
        page.line("d1", 60, 112, 300, "protects local makers"),
        rich(page, "d2", 60, 124, [("quota ", True), ("a limit on an amount", False)]),
    ]
    page.region("n", "main_text", lines, page.band("b", 100, 140, [(60, 550, "column")]), 0)
    p, layout, result, lists = lists_of(page)
    found = items(p, layout, result, ("definition_entry",))
    assert [t for t, _ in found] == [
        "tariff a tax on imported goods that protects local makers",
        "quota a limit on an amount",
    ]
    assert lists[0].kind == "definition"


def test_right_to_left_list_uses_the_reading_start():
    page = PageBuilder(1)
    lines = [
        page.line("h0", 300, 100, 550, "• " + HEBREW[0], direction="rtl"),
        page.line("h1", 300, 114, 538, HEBREW[1], direction="rtl"),  # hanging, from the right
        page.line("h2", 300, 128, 550, "• " + HEBREW[2], direction="rtl"),
    ]
    page.region("h", "main_text", lines, page.band("b", 100, 140, [(60, 550, "column")]), 0)
    p, layout, result, lists = lists_of(page)
    found = items(p, layout, result)
    assert [len(u.line_ids) for _, u in found] == [2, 1]
    assert lists[0].kind == "bulleted"


def test_every_line_in_exactly_one_unit_and_heading_units_kept():
    page = index_page()
    p, layout, step9 = built(page, profile=PROFILE)
    heading = next(u for u in step9.units if u.kind in ("paragraph", "list_item_candidate"))
    result, _ = build_page_lists(p, layout, step9, PageContext(
        navigation="index", heading_units=frozenset({heading.id})))  # fmt: skip
    lines = [lid for u in result.units for lid in u.line_ids]
    assert sorted(lines) == sorted(line.id for line in layout.lines)
    kept = next(u for u in result.units if u.id == heading.id)
    assert kept.line_ids == heading.line_ids and kept.kind == heading.kind


def test_entries_across_a_page_break_link_and_never_join_like_prose():
    first, second = index_page(1), PageBuilder(2)
    rows = [(100, 14, "40, 56, 61"), (114, 0, "elder, 31"), (128, 0, "fig, 4")]
    column(second, "c", 60, 330, rows, second.band("b", 100, 140, [(60, 330, "column")]))
    summaries, pages = [], []
    for page, layout, furniture in furnished_book([first, second]):
        step9 = build_page(page, layout, furniture, PROFILE)
        context = PageContext(navigation="index")
        result, lists = build_page_lists(page, layout, step9, context)
        summaries.append(_summary(layout.page, result, lists, context))
        pages.append(result)
    last = pages[0].units[-1].line_ids[-1]
    top = next(u for u in pages[1].units if u.kind == "index_entry").line_ids[0]
    join = SimpleNamespace(from_page=1, to_page=2, join=SimpleNamespace(
        previous_line_id=last, next_line_id=top))  # fmt: skip
    aliases, links, dropped, _ = _link_pages(summaries, SimpleNamespace(
        book=SimpleNamespace(page_joins=[join])))  # fmt: skip
    entry_links = [link for link in links if link["kind"] == "entry"]
    assert len(entry_links) == 1  # the indented top line continues the entry: linked
    assert dropped and dropped[0]["reason"] == "entries never join across pages like prose"
    assert list(aliases.values()) == [pages[0].units[0].list_id or summaries[0]["last"]["list"]]


def test_body_starts_at_the_first_arabic_run_without_sectioning_openers():
    book = Book(8)
    book.unit(1, "A Handbook of Anatomy", size=30, bold=True)
    book.body(2)
    book.body(3)
    book.unit(4, "Bones of the arm", size=14, bold=True)
    book.body(4)
    for page in (5, 6, 7):
        book.unit(page, f"{page - 3} Muscles of the region", size=16, bold=True)
        book.body(page)
    book.body(8)
    book.runs = [
        {"kind": "roman", "first_page": 2, "last_page": 3, "inferred_pages": [], "index": 0},
        {"kind": "arabic", "first_page": 4, "last_page": 8, "inferred_pages": [], "index": 1},
    ]
    decided = decide(book)
    zones = [z.zone for z in decided["page_zones"]]
    assert zones[:4] == ["front", "front", "front", "body"]
    assert decided["profile"]["zones"]["body_start_rule"].startswith("first Arabic folio run")


def test_reader_takes_page_markers_only_from_anchors_with_a_page_id():
    from book_core.reference.dialects import dialects_from_data
    from book_core.reference.xml_reader import read_reference

    data = {
        "common": {"inline_elements": [], "unit_kinds": {"paragraph": ["para"]},
                   "containers": ["book"], "sectioning": [], "list_containers": [],
                   "table_containers": [], "row_elements": [],
                   "declared_heading_levels": {}, "zones": {}},
        "dialects": [{"name": "anchors", "detect": {"root_names": ["book"]},
                      "page_marker_elements": ["anchor"],
                      "page_marker_label": {"attribute": "id", "pattern": "^page(.+)$"}}],
    }  # fmt: skip
    xml = (b'<book><para>one <anchor id="page1"/>two</para>'
           b'<para>three <anchor id="fig3"/>four</para></book>')  # fmt: skip
    doc = read_reference(xml, dialects_from_data(data))
    assert len(doc.markers) == 1  # the figure anchor is an ordinary element
    assert [t.value for t in doc.tokens] == ["one", "two", "three", "four"]


def gold_unit(unit, kind, pdf, **extra):
    row = {
        "unit": unit,
        "kind": kind,
        "pdf": pdf,
        "zone": "body",
        "table": None,
        "list": None,
        "element": "li",
        "start": [pdf[0][0], pdf[0][1]] if pdf else None,
    }
    row.update(extra)
    return row  # fmt: skip


def test_list_metrics_on_toy_gold():
    lst = {"list": "/l1", "depth": 1, "item": None}
    units = [
        gold_unit(0, "list_item", [[1, 0, 3]], list=lst),
        gold_unit(1, "list_item", [[1, 3, 2]], list=lst),
        gold_unit(2, "definition_term", [[1, 5, 1]], element="dt"),
        gold_unit(3, "definition_description", [[1, 6, 3]], element="dd"),
        gold_unit(4, "index_entry", [[2, 0, 2]], element="primaryie"),
        gold_unit(5, "index_entry", [[2, 2, 2]], element="secondaryie"),
        gold_unit(6, "list_item", [[2, 4, 2], [3, 0, 2]], list={**lst, "list": "/l2"}),
    ]  # fmt: skip
    gold = DerivedGold(book="b", split="development", manifest={"notes": []}, units=units,
                       markers=[], pages=[])  # fmt: skip
    unit_of = {(1, i): "a" for i in range(3)} | {(1, i): "b" for i in (3, 4)}
    unit_of |= {(1, i): "d" for i in range(5, 9)} | {(2, 0): "x", (2, 1): "x"}
    unit_of |= {(2, 2): "y", (2, 3): "y", (2, 4): "p", (2, 5): "p", (3, 0): "q", (3, 1): "q"}
    ours = Ours(unit_of=unit_of,
                kind_of={"a": "list_item", "b": "list_item", "d": "definition_entry",
                         "x": "index_entry", "y": "index_entry", "p": "list_item",
                         "q": "list_item"},
                list_of={"a": "L", "b": "L", "p": "M", "q": "M"},
                level_of={"a": 1, "b": 1, "x": 1, "y": 2, "p": 1, "q": 1},
                chain_of={"q": "p"}, terms={(1, 5)}, links=[("p", "q")])  # fmt: skip
    items_ = list_item_scores(gold, ours)
    # The item crossing pages is two per-page units: per-page exact match is 2 of 3.
    assert items_["exact_match"] == round(2 / 3, 6) and items_["list_boundary"]["f1"] == 1.0
    assert items_["nesting"]["exact"] == 1.0
    definitions = definition_scores(gold, ours)
    assert definitions["definition_term"]["exact"] == 1.0
    assert definitions["definition_description"]["exact"] == 1.0
    index = index_scores(gold, ours)
    assert index["exact_match"] == 1.0 and index["sub_entry_level_accuracy"] == 1.0
    crossing = cross_page_scores(gold, ours)
    assert crossing["held_in_one_chain"] == 1 and crossing["false_joins"] == 0


@pytest.mark.parametrize("entry", LISTS_ENTRY_POINTS)
def test_lists_scope_covers_the_import_closure(entry):
    missing = closure(entry) - set(coverage_files("lists"))
    assert not missing, f"Step 11 cache key ignores {sorted(missing)}"


def test_editing_any_lists_producer_changes_the_digest(tmp_path):
    copy = tmp_path / "book_core"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    original = lists_code_digest()
    assert lists_code_digest(copy) == original
    for relative in lists_scope_files(copy):
        if not relative.startswith("lists/"):
            continue
        target = copy / relative
        data = target.read_bytes()
        target.write_bytes(data + b"\n# edited\n")
        assert lists_code_digest(copy) != original, relative
        target.write_bytes(data)


@pytest.mark.parametrize("change", ["lists", "structure_key", "paragraph_key", "config",
                                    "version"])  # fmt: skip
def test_every_lists_key_component_changes_the_key(change):
    base = {"lists": "l", "structure_key": "s", "paragraph_key": "p", "settings": Settings(),
            "config": {"a": 1}, "version": "v"}  # fmt: skip
    other = {**base, change: {"a": 2} if change == "config" else "other"}
    assert book_fingerprint(book_key_components(**base)) != book_fingerprint(
        book_key_components(**other)
    )
