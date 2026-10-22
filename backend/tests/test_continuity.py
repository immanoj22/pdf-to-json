"""Step 15: content continued across page breaks (continuity stage) and Part 0 changes."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.continuity import decide
from book_core.continuity.cache import column_end
from book_core.continuity.edges import PageEdges, UnitEdge, column_change, end_kind, start_kind
from book_core.model.common import BBox
from book_core.paragraphs.geometry import Frame
from book_core.tables.models import Continuation, TableText, review_status
from book_core.tables.records import title_checks
from book_core.tables.settings import TableSettings

BODY = ("serif", 10.0, False, False)
PROFILE = SimpleNamespace(indents=False)
INDENTED = SimpleNamespace(indents=True)


def _edge(kind="paragraph", role="body", tail="", head="", lines=4, style=BODY, indent=0.0,
          fill=0.2, width=300.0, **extra):  # fmt: skip
    return UnitEdge(id=extra.pop("id", f"{kind}-{tail}{head}"), kind=kind, stream_kind="main",
                    role=role, lines=lines, style=style, size=10.0, width=width,
                    indent=indent if lines > 1 else None, fill=fill if lines > 1 else None,
                    tail=tail, head=head, **extra)  # fmt: skip


# --- join / no-join evidence --------------------------------------------------------------


def test_open_end_and_lowercase_start_join():
    kind, confidence, reasons = decide.decide(_edge(tail="the city of"), _edge(head="ancient"),
                                              PROFILE, None)  # fmt: skip
    assert kind == "paragraph" and confidence >= 0.85
    assert "the sentence continues on the next page" in reasons


def test_a_sentence_end_does_not_join_unless_the_book_indents_paragraphs():
    a, b = _edge(tail="was over."), _edge(head="The next")
    assert decide.decide(a, b, PROFILE, None)[0] is None
    # In a book that indents its paragraphs, a full last line and an unindented next line
    # continue the paragraph with a new sentence.
    assert decide.decide(a, b, INDENTED, None)[0] == "paragraph"
    assert decide.decide(a, _edge(head="The next", indent=2.0), INDENTED, None)[0] is None


def test_style_change_indent_and_width_refuse():
    a = _edge(tail="the city of")
    bold = ("serif", 10.0, True, False)
    assert decide.decide(a, _edge(head="ancient", style=bold), PROFILE, None)[0] is None
    assert decide.decide(a, _edge(head="ancient", indent=1.5), PROFILE, None)[0] is None
    assert decide.decide(a, _edge(head="ancient", width=150.0), PROFILE, None)[0] is None


def test_a_capital_after_an_open_end_needs_a_full_last_line():
    b = _edge(head="United States")
    assert decide.decide(_edge(tail="minority group in the"), b, PROFILE, None)[0] == "paragraph"
    short = _edge(tail="minority group in the", fill=8.0)
    assert decide.decide(short, b, PROFILE, None)[0] is None


def test_skipped_set_apart_text_needs_a_lowercase_start():
    a = _edge(tail="De manera similar,")
    assert decide.decide(a, _edge(head="Henry Kissinger"), PROFILE, None, True)[0] is None
    assert decide.decide(a, _edge(head="la guerra"), PROFILE, None, True)[0] == "paragraph"


def test_list_items_continue_only_from_a_full_last_line():
    one = _edge(kind="list_item", tail="Splanchnic nerves", lines=1)
    assert decide.decide(one, _edge(head="from various parts"), PROFILE, None)[0] is None
    full = _edge(kind="list_item", tail="carried by the")
    assert decide.decide(full, _edge(head="blood"), PROFILE, None)[0] == "list_item"
    marked = _edge(head="next item", marker=True)
    assert decide.decide(full, marked, PROFILE, None)[0] is None


def test_entries_are_linked_never_joined_and_glossary_rows_are_not_linked_by_rule():
    a = _edge(kind="index_entry", tail="Indios de todas las")
    kind, _, _ = decide.decide(a, _edge(kind="index_entry", head="tribus, 495"), PROFILE, None)
    assert kind == "entry"
    done = _edge(kind="index_entry", tail="(NAWSA), 145, 199")
    assert decide.decide(done, _edge(kind="index_entry", head="Asociación"), PROFILE,
                         None)[0] is None  # fmt: skip
    gloss = _edge(kind="definition_entry", tail="as if it were one")
    assert decide.decide(gloss, _edge(kind="definition_entry", head="person"), PROFILE,
                         None)[0] is None  # fmt: skip


def test_an_enumerator_opens_a_new_item_never_a_continuation():
    a = _edge(tail="quantitative discrete, 11,234 students")
    assert decide.decide(a, _edge(head="65 . quantitative continuous"), PROFILE, None)[0] is None
    assert decide.decide(_edge(tail="Then,"), _edge(head="a. Find P"), PROFILE, None)[0] is None
    # Numbers that are text continue: a count, a decimal, a year closing a citation.
    for head in ("12 horas en fábricas", "38.6 percent, and", "2001). Further, the"):
        assert decide.decide(_edge(tail="turnos de"), _edge(head=head), PROFILE, None)[0]


def test_text_cues_are_script_neutral():
    assert end_kind("una palabra-") == "hyphen" and end_kind("fin.") == "terminal"
    assert end_kind("p. 12") == "locator" and end_kind("y la") == "open"
    assert start_kind("«ésta") == "lower" and start_kind("1877 con") == "digit"
    assert start_kind("中文") == "other"  # no case: the decision rests on the end alone


def _page(*items):
    return PageEdges(page=1, navigation=None, label=None, label_source="none", items=list(items))


def test_a_heading_between_the_halves_stops_the_search_floats_are_skipped():
    a = _edge(tail="the city of")
    heading = _edge(kind="heading_candidate", role="heading", tail="Section")
    table = _edge(kind="table", role="float", linked=True)
    assert decide.bottom(_page(a, heading))[0] is None
    found, skipped, _ = decide.bottom(_page(a, table))
    assert found is a and skipped == [table]
    b, skipped, _, float_only = decide.top(_page(table, _edge(head="ancient")))
    assert b is not None and skipped == [table] and not float_only
    assert decide.top(_page(table))[3]  # a page of floats only is skipped
    assert decide.guarded([table])  # anything skipped asks for the strongest evidence


def test_column_change_and_column_ends():
    a = Frame(start=40, end=200, block=500, size=10)
    b = Frame(start=220, end=380, block=80, size=10)
    assert column_change(SimpleNamespace(last_frame=a), SimpleNamespace(first_frame=b))
    below = Frame(start=40, end=200, block=520, size=10)
    assert not column_end(a, [a, b, below], "below")
    assert column_end(a, [a, b], "below") and column_end(b, [a, b], "above")


# --- Part 0 ---------------------------------------------------------------------------------


def test_table_review_status_is_needs_review_for_every_flag_today():
    assert review_status([]) is None
    assert review_status(["TableFormer reads a different structure (similarity 0.40); review"]) \
        == "needs_review"  # fmt: skip


def _titled(table_id, page, number, to=None, came=None):
    from test_tables_14b import _table_record

    title = TableText(role="title", unit_id="u" + table_id, line_ids=["title" + table_id],
                      rule="r", numbered=True, number=number, confidence=0.9)  # fmt: skip
    return _table_record().model_copy(
        update={
            "id": table_id,
            "page": page,
            "title": title,
            "continues_to": to,
            "continues_from": came,
        }
    )


def test_a_continuation_into_a_differently_numbered_table_is_withdrawn():
    to = Continuation(table_id="b", page=2, confidence=0.8, reasons=["x"])
    back = Continuation(table_id="a", page=1, confidence=0.8, reasons=["x"])
    same = {1: [_titled("a", 1, "4.28", to=to)], 2: [_titled("b", 2, "4.28", came=back)]}
    assert title_checks(same)[1] == 0  # a title repeated on each part: still one table
    other = {1: [_titled("a", 1, "4.10", to=to)], 2: [_titled("b", 2, "4.11", came=back)]}
    pages, withdrawn = title_checks(other)
    assert withdrawn == 1 and pages[1][0].continues_to is None
    assert pages[2][0].continues_from is None and "withdrawn" in pages[2][0].review_flags[0]
    assert pages[2][0].with_status().review_status == "needs_review"


def test_cache_closure_covers_the_continuity_stage():
    assert closure("continuity/cache.py") <= set(caching.coverage_files("continuity"))
    assert "continuity" in caching.DEPENDENCIES["final"]
    assert closure("book_run.py") <= set(caching.coverage_files("final"))


# --- a small book: a hyphen across a page, a sentence end, a continued table --------------

FONT = 10
LINE = 14


def _lines(page, top, texts):
    for k, text in enumerate(texts):
        page.insert_text((40, top + LINE * k), text, fontsize=FONT)
    return top + LINE * len(texts)


FILL = "the river valley carried trade goods and news between the towns"


def _grid(page, top, rows, header):
    shape = page.new_shape()
    width, height = 340, 18
    for r in range(len(rows) + 1):
        shape.draw_line((40, top + r * height), (40 + width, top + r * height))
    for c in range(4):
        shape.draw_line((40 + c * width / 3, top), (40 + c * width / 3, top + len(rows) * height))
    shape.finish(color=(0, 0, 0), width=0.6)
    shape.commit()
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            page.insert_text((45 + c * width / 3, top + r * height + 13), value, fontsize=FONT,
                             fontname="hebo" if header and r == 0 else "helv")  # fmt: skip
    return top + len(rows) * height


TABLE_BOXES = {}


def _book(path):
    head = ("Region", "Population", "Area")
    with pymupdf.open() as document:
        page = document.new_page(width=420, height=600)
        _lines(page, 60, ["The early settlements grew along " + FILL[:28]] +
               [FILL] * 30 + ["and the merchants of the valley built a common market for the"
                              " develop-"])  # fmt: skip
        page.insert_text((205, 580), "11", fontsize=8)
        page = document.new_page(width=420, height=600)
        _lines(page, 60, ["ment of the region, which " + FILL[:30]] + [FILL] * 29 +
               ["and the year of the great flood ended this period."])  # fmt: skip
        page.insert_text((205, 580), "12", fontsize=8)
        page = document.new_page(width=420, height=600)
        end = _lines(page, 60, ["The census counted the people of every region of the valley."]
                     + [FILL] * 9 + [FILL + "."])  # fmt: skip
        rows = [head] + [(f"North {k}", f"{1000 + k}", f"{50 + k}") for k in range(17)]
        bottom = _grid(page, end + 20, rows, True)
        TABLE_BOXES[3] = BBox(x0=38, y0=end + 18, x1=382, y1=bottom + 2)
        page.insert_text((205, 580), "13", fontsize=8)
        page = document.new_page(width=420, height=600)
        rows = [head] + [(f"South {k}", f"{2000 + k}", f"{70 + k}") for k in range(6)]
        bottom = _grid(page, 60, rows, True)
        TABLE_BOXES[4] = BBox(x0=38, y0=58, x1=382, y1=bottom + 2)
        _lines(page, bottom + 30, ["The table shows how the population moved south."]
               + [FILL] * 6)  # fmt: skip
        page.insert_text((205, 580), "14", fontsize=8)
        document.save(path)
    return path


class Detectors:
    identity = {"a": "stub", "b": "stub"}

    def __call__(self, number):
        box = TABLE_BOXES.get(number)
        return {name: [(box, 0.9, "table")] for name in ("a", "b")} if box else {}


@pytest.fixture
def continued_pdf(tmp_path):
    return _book(tmp_path / "continued.pdf")


def _run(pdf, out, cache, workers):
    return run_book(pdf, out, cache, workers=workers, device="cpu",
                    table_settings=TableSettings(model_evidence="on"),
                    table_evidence=Detectors())  # fmt: skip


def _text_of(page, lid):
    spans = page["source"]["store"]["spans"]
    return "".join(spans[s]["raw_text"] for s in page["line_spans"].get(lid, []))


def test_continuity_on_a_small_book_and_workers(continued_pdf, tmp_path):
    serial = _run(continued_pdf, tmp_path / "a_out", tmp_path / "a", 1)
    root = Path(serial["output"])
    book = read_json(root / "book.json.gz")["continuity"]
    chains = {}
    for chain in book["chains"]:
        chains.setdefault(chain["kind"], []).append(chain)
    # The paragraph continues across pages 1-2 through a break hyphen, repaired by decision.
    (paragraph,) = chains["paragraph"]
    (brk,) = paragraph["breaks"]
    assert (brk["from_page"], brk["to_page"], brk["kind"]) == (1, 2, "page")
    assert brk["join"]["hyphen"]["choice"] == "join"
    page1, page2 = (read_json(root / f"page_{n:06d}.json.gz") for n in (1, 2))
    assert _text_of(page1, brk["from_line_id"]).rstrip().endswith("develop-")
    assert _text_of(page2, brk["to_line_id"]).startswith("ment of the region")
    # The page marker of the page that begins stays with the break.
    assert brk["page_label"] in {"12", None}
    units = {u["id"]: u for u in page1["units"]["units"]}
    assert units[brk["from_id"]]["continues_to"] == brk["to_id"]
    assert page1["continuity"] and page2["continuity"]
    # A sentence end at the bottom of page 2 does not join page 3.
    assert not any(b["from_page"] == 2 for c in book["chains"] for b in c["breaks"])
    # The table continues on page 4; its repeated header row is named, not repeated.
    (table,) = chains["table"]
    (tbrk,) = table["breaks"]
    assert (tbrk["from_page"], tbrk["to_page"]) == (3, 4)
    assert tbrk["repeated_header_rows"] == 1 and tbrk["column_map"] == [0, 1, 2]

    def files(result):
        base = Path(result["output"])
        return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in base.rglob("*") if p.is_file()}  # fmt: skip

    parallel = _run(continued_pdf, tmp_path / "b_out", tmp_path / "b", 2)
    assert files(serial) == files(parallel)


def _glossary_as_table_text(navigation):
    from test_lists import PROFILE, built, glossary_page

    from book_core.lists.page import PageContext, build_page_lists

    page, layout, step9 = built(glossary_page(), profile=PROFILE)
    units = [u.model_copy(update={"kind": "table_text"}) for u in step9.units]
    step9 = step9.model_copy(update={"units": units})
    result, _ = build_page_lists(page, layout, step9, PageContext(navigation=navigation))
    return page, layout, result


def test_a_glossary_page_set_as_a_table_region_is_read_as_entries():
    from test_lists import items

    p, layout, result = _glossary_as_table_text("glossary")
    found = items(p, layout, result, ("definition_entry",))
    assert [t for t, _ in found][:2] == [
        "casa vivienda de una familia que vive junto a otras casas (pág. 10)",
        "house a home for one family",
    ]  # entry by entry, as on a glossary page set as running text
    # Off a glossary page, table-region text stays table text.
    _, _, plain = _glossary_as_table_text(None)
    assert {u.kind for u in plain.units} == {"table_text"}


def test_a_drawing_fragment_holding_the_numbered_title_becomes_a_table_piece():
    from test_tables_14b import BOX, _table_record

    from book_core.tables import captions

    title = TableText(role="title", unit_id="title", line_ids=["tl"], rule="r", numbered=True,
                      number="2.32", confidence=0.9)  # fmt: skip
    table = _table_record().model_copy(update={
        "title": title, "review_flags": [captions.INSIDE_FIGURE]})  # fmt: skip
    title_box = BBox(x0=BOX.x0, y0=BOX.y1 + 2, x1=BOX.x0 + 40, y1=BOX.y1 + 12)
    piece = BBox(x0=BOX.x0, y0=BOX.y1 - 5, x1=BOX.x0 + 40, y1=BOX.y1 + 12)
    row = table.cells[-1].line_ids
    fragment = {"id": "f1", "bbox": piece,
                "units": {"title": (["tl"], title_box), "cell": (row, BOX)}}  # fmt: skip
    foreign = {
        "id": "f2",
        "bbox": piece,
        "units": {"title": (["tl"], title_box), "other": (["elsewhere"], BOX)},
    }
    pages, notes, count = captions.title_pieces({1: [table]}, {1: [fragment, foreign]})
    (found,) = pages[1]
    assert count == 1 and found.absorbed_figure_ids == ["f1"]
    assert captions.INSIDE_FIGURE not in found.review_flags
    assert notes[1][0].kind == "table_piece" and notes[1][0].figure_id == "f1"
