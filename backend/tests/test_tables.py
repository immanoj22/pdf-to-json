"""Step 14a tables: detection from combined evidence, grids with spans and header rows,
rotated tables, look-alikes, continuation, no text lost, scoring, cache closure and workers."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.evaluation import table_gold, table_scoring
from book_core.model.common import BBox
from book_core.tables.rulings import Rule, merged
from book_core.tables.settings import TableSettings

FONT = 9


def _text(page, x, y, text, rotate=0):
    page.insert_text((x, y), text, fontsize=FONT, rotate=rotate)


def _grid(shape, xs, ys, skip=()):
    """Rules of a grid; ``skip`` holds (row, column) whose right rule is left out."""
    for y in ys:
        shape.draw_line((xs[0], y), (xs[-1], y))
    for c, x in enumerate(xs):
        for r in range(len(ys) - 1):
            if (r, c - 1) in skip:
                continue
            shape.draw_line((x, ys[r]), (x, ys[r + 1]))
    shape.finish(color=(0, 0, 0), width=0.6)


def _book(path):
    with pymupdf.open() as document:
        # Page 1: running text, then a ruled grid whose first row spans two columns.
        page = document.new_page(width=420, height=600)
        _text(page, 40, 60, "Paragraph text before the table runs across the whole line.")
        xs, ys = [40, 150, 260, 370], [100, 120, 140, 160, 180]
        shape = page.new_shape()
        _grid(shape, xs, ys, skip={(0, 1)})
        shape.commit()
        _text(page, 45, 114, "Region")
        _text(page, 155, 114, "Systems and parts")
        for r, row in enumerate([("Head", "Brain", "Skull"), ("Trunk", "Heart", "Ribs"),
                                 ("Limbs", "Muscles", "Bones")]):  # fmt: skip
            for c, value in enumerate(row):
                _text(page, xs[c] + 5, ys[r + 1] + 14, value)
        _text(page, 40, 220, "Closing paragraph after the table on this page.")
        # Page 2: an unboxed table (top, header and bottom rules), numeric columns, and a
        # line whose one span holds two cells.
        page = document.new_page(width=420, height=600)
        shape = page.new_shape()
        for y in (100, 118, 190):
            shape.draw_line((40, y), (360, y))
        shape.finish(color=(0, 0, 0), width=0.6)
        shape.commit()
        _text(page, 45, 113, "Variable")
        _text(page, 200, 113, "Mean")
        _text(page, 300, 113, "SD")
        for i, (name, mean, sd) in enumerate([("Age", "12.4", "1.3"), ("Score", "45.1", "6.2"),
                                              ("Height", "151.0", "8.8")]):  # fmt: skip
            y = 133 + 18 * i
            _text(page, 45, y, name)
            _text(page, 200, y, mean)
            _text(page, 300, y, sd)
        _text(page, 45, 186, "Weight")
        _text(page, 200, 186, "40.2" + " " * 38 + "5.1")  # one span reaching the SD column
        # Page 3: the same unboxed table rotated a quarter turn.
        page = document.new_page(width=420, height=600)
        shape = page.new_shape()
        for x in (100, 118, 190):
            shape.draw_line((x, 520), (x, 200))
        shape.finish(color=(0, 0, 0), width=0.6)
        shape.commit()
        for label, offset in [("Variable", 515), ("Mean", 360), ("SD", 260)]:
            _text(page, 113, offset, label, rotate=90)
        for i, (name, mean, sd) in enumerate([("Age", "12.4", "1.3"), ("Score", "45.1", "6.2"),
                                              ("Height", "151.0", "8.8"),
                                              ("Weight", "40.2", "5.1")]):  # fmt: skip
            x = 133 + 16 * i
            _text(page, x, 515, name, rotate=90)
            _text(page, x, 360, mean, rotate=90)
            _text(page, x, 260, sd, rotate=90)
        # Page 4: a graphic organizer (separate boxes joined by arrows), then a table that
        # ends at the page bottom.
        page = document.new_page(width=420, height=600)
        shape = page.new_shape()
        for y in (60, 120):
            shape.draw_rect(pymupdf.Rect(40, y, 160, y + 40))
            shape.draw_rect(pymupdf.Rect(220, y, 340, y + 40))
            shape.draw_line((160, y + 20), (220, y + 20))
            shape.draw_line((212, y + 15), (220, y + 20))
            shape.draw_line((212, y + 25), (220, y + 20))
        shape.finish(color=(0, 0, 0), width=0.6)
        _grid(shape, [40, 200, 360], [440, 460, 480, 500, 520, 540])
        shape.commit()
        _text(page, 45, 84, "Cause one")
        _text(page, 45, 144, "Cause two")
        _text(page, 45, 454, "Year")
        _text(page, 205, 454, "Event")
        for r in range(4):
            _text(page, 45, 474 + 20 * r, f"19{20 + r}")
            _text(page, 205, 474 + 20 * r, f"Event number {r + 1}")
        # Page 5: the same columns continue at the top of the next page.
        page = document.new_page(width=420, height=600)
        shape = page.new_shape()
        _grid(shape, [40, 200, 360], [40, 60, 80, 100])
        shape.commit()
        for r in range(3):
            _text(page, 45, 54 + 20 * r, f"19{30 + r}")
            _text(page, 205, 54 + 20 * r, f"Event number {r + 5}")
        _text(page, 40, 160, "Text after the continued table closes the book.")
        document.save(path)
    return path


@pytest.fixture
def table_pdf(tmp_path):
    return _book(tmp_path / "tables.pdf")


TABLE_BOXES = {
    1: [(38, 98, 372, 182)],
    2: [(38, 98, 362, 192)],
    3: [(98, 198, 192, 522)],
    4: [(38, 438, 362, 542)],
    5: [(38, 38, 362, 102)],
}


class StubModels:
    """Stub detector evidence: two detectors agree on each synthetic table; one also calls
    the organizer on page 4 a table (it is not one)."""

    identity = {"a": "stub", "b": "stub"}

    def __call__(self, number):
        boxes = [BBox(x0=a, y0=b, x1=c, y1=d) for a, b, c, d in TABLE_BOXES.get(number, [])]
        found = {name: [(box, 0.9, "table") for box in boxes] for name in ("a", "b")}
        if number == 4:
            found["a"].append((BBox(x0=38, y0=58, x1=342, y1=162), 0.9, "table"))
        return found


OrganizerModels = StubModels


def _page(result, number):
    return read_json(Path(result["output"]) / f"page_{number:06d}.json.gz")


def _tables(result, number):
    return _page(result, number)["tables"]["tables"]


@pytest.fixture
def run(table_pdf, tmp_path):
    return run_book(
        table_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu",
        table_settings=TableSettings(model_evidence="on"), table_evidence=OrganizerModels(),
    )  # fmt: skip


def _cell_text(page, cell):
    spans = page["source"]["store"]["spans"]
    text = []
    for lid in cell["line_ids"]:
        text.append("".join(spans[s]["raw_text"] for s in page["line_spans"].get(lid, [])))
    for ref in cell["span_refs"]:
        raw = spans[ref["span_id"]]["raw_text"]
        text.append(raw[ref["start"] : ref["end"]] if ref["start"] is not None else raw)
    return " ".join(t.strip() for t in text if t.strip())


def test_ruled_grid_with_a_spanning_header_cell(run):
    tables = _tables(run, 1)
    assert len(tables) == 1
    table = tables[0]
    assert (len(table["rows"]), len(table["columns"])) == (4, 3)
    assert set(table["families"]) >= {"rules", "alignment"}
    spanning = [c for c in table["cells"] if c["column_span"] == 2]
    assert len(spanning) == 1 and spanning[0]["row"] == 0 and spanning[0]["column"] == 1
    assert table["header_rows"] in {0, 1}


def test_unboxed_table_header_rule_and_a_span_split_between_two_cells(run):
    page = _page(run, 2)
    (table,) = page["tables"]["tables"]
    assert (len(table["rows"]), len(table["columns"])) == (5, 3)
    assert table["header_rows"] == 1
    texts = sorted(_cell_text(page, c) for c in table["cells"])
    assert "40.2" in texts and "5.1" in texts  # one PDF span, two cells
    assert any(ref["start"] is not None for c in table["cells"] for ref in c["span_refs"])


def test_rotated_table_is_read_in_its_frame(run):
    (table,) = _tables(run, 3)
    assert table["rotation"] in {90, 270}
    assert (len(table["rows"]), len(table["columns"])) == (5, 3)
    assert table["header_rows"] == 1


def test_graphic_organizer_is_not_a_table(run):
    page = _page(run, 4)
    kinds = [r["kind"] for r in page["tables"]["rejected"]]
    assert "graphic_organizer" in kinds
    assert all(t["bbox"]["y0"] > 300 for t in page["tables"]["tables"])  # only the real table


def test_continuation_is_marked_never_joined(run):
    (first,) = [t for t in _tables(run, 4) if t["bbox"]["y0"] > 300]
    (second,) = _tables(run, 5)
    assert first["continues_to"]["table_id"] == second["id"]
    assert second["continues_from"]["table_id"] == first["id"]
    assert first["id"] != second["id"] and first["cells"] and second["cells"]


def test_no_text_lost_every_line_in_exactly_one_unit_or_table(run):
    for number in range(1, 6):
        page = _page(run, number)
        view = page["table_view"]
        units = [u for u in page["units"]["units"] if u["id"] not in set(view["removed"])]
        units += view["added"]
        owners = {}
        for unit in units:
            for lid in unit["line_ids"]:
                owners[lid] = owners.get(lid, 0) + 1
        for table in page["tables"]["tables"]:
            for lid in table["line_ids"]:
                owners[lid] = owners.get(lid, 0) + 1
            # A table line is a whole line of one cell, or covered by span ranges exactly once.
            whole = [lid for c in table["cells"] for lid in c["line_ids"]]
            assert len(whole) == len(set(whole))
            spans = page["line_spans"]
            for lid in set(table["line_ids"]) - set(whole):
                covered = {}
                for c in table["cells"]:
                    for ref in c["span_refs"]:
                        if ref["span_id"] in spans[lid]:
                            raw = page["source"]["store"]["spans"][ref["span_id"]]["raw_text"]
                            start = ref["start"] or 0
                            end = ref["end"] if ref["end"] is not None else len(raw)
                            for k in range(start, end):
                                covered[(ref["span_id"], k)] = (
                                    covered.get((ref["span_id"], k), 0) + 1
                                )
                expected = {
                    (sid, k)
                    for sid in spans[lid]
                    for k in range(len(page["source"]["store"]["spans"][sid]["raw_text"]))
                }
                assert set(covered) == expected and set(covered.values()) == {1}
        assert set(owners) == set(page["line_spans"]) | {
            lid for t in page["tables"]["tables"] for lid in t["line_ids"]
        }
        assert set(owners.values()) == {1}


def test_without_model_evidence_tables_are_possible_only_and_take_no_text(table_pdf, tmp_path):
    from book_core.tables.settings import MODELS_MISSING

    result = run_book(table_pdf, tmp_path / "o", tmp_path / "c", workers=1, device="cpu")
    assert MODELS_MISSING in result["warnings"]
    for number in range(1, 6):
        page = _page(result, number)
        assert page["tables"]["tables"] == []
        assert page["table_view"] == {"removed": [], "added": []}
    possible = _page(result, 1)["tables"]["possible_tables"]
    assert possible and all(not t["owns_text"] for t in possible)
    assert all(set(t["families"]) >= {"rules", "alignment"} for t in possible)


def test_one_detector_is_not_enough_to_own_text(table_pdf, tmp_path):
    class OneModel(StubModels):
        identity = {"a": "stub"}

        def __call__(self, number):
            return {"a": super().__call__(number)["a"]}

    result = run_book(
        table_pdf, tmp_path / "o", tmp_path / "c", workers=1, device="cpu",
        table_settings=TableSettings(model_evidence="on"), table_evidence=OneModel(),
    )  # fmt: skip
    assert _tables(result, 1) == []
    assert _page(result, 1)["tables"]["possible_tables"]


def test_model_evidence_must_be_supplied_exactly_when_on(table_pdf, tmp_path):
    with pytest.raises(RuntimeError, match="not installed"):
        run_book(table_pdf, tmp_path / "o", tmp_path / "c", workers=1, device="cpu",
                 table_settings=TableSettings(model_evidence="on"))  # fmt: skip


def test_workers_and_production_give_identical_tables(table_pdf, tmp_path):
    def files(result):
        root = Path(result["output"])
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    options = {"table_settings": TableSettings(model_evidence="on"),
               "table_evidence": OrganizerModels(), "device": "cpu"}  # fmt: skip
    serial = run_book(table_pdf, tmp_path / "a_out", tmp_path / "a", workers=1, **options)
    parallel = run_book(table_pdf, tmp_path / "b_out", tmp_path / "b", workers=2, **options)
    production = run_book(
        table_pdf, tmp_path / "c_out", tmp_path / "c", workers=2, mode="production", **options
    )
    assert files(serial) == files(parallel) == files(production)
    assert _tables(serial, 1)


def test_tables_cache_closure_covers_its_imports():
    assert closure("tables/cache.py") <= set(caching.coverage_files("tables"))
    assert closure("tables/recognizers.py") <= set(caching.coverage_files("table_models"))
    assert closure("book_run.py") <= set(caching.coverage_files("final"))


def test_missing_tables_dependency_is_detected(monkeypatch):
    monkeypatch.setitem(
        caching.DEPENDENCIES,
        "final",
        ("lists", "metadata", "characters", "figures", "equations", "mathml"),
    )
    missing = closure("book_run.py") - set(caching.coverage_files("final"))
    assert "tables/cache.py" in missing


# --- units: rules, gold grids, scoring --------------------------------------------------


def test_collinear_rules_merge_only_when_they_meet():
    rules = [
        Rule("v", 470.5, 379.7, 670.0, 0.5, "stroke", "a"),
        Rule("v", 470.7, 259.6, 291.6, 0.5, "stroke", "b"),
        Rule("v", 470.6, 290.0, 300.0, 0.5, "stroke", "c"),
    ]
    found = sorted((round(r.start), round(r.end)) for r in merged(rules, 2.0))
    assert found == [(260, 300), (380, 670)]


def _node(name, attributes=None, children=()):
    node = table_gold.Node(name, "", dict(attributes or {}), list(children))
    for child in node.children:
        child.parent = node
    return node


def test_gold_grid_reads_spans_and_header_rows():
    vocab = table_gold.vocabulary("docbook4-page-anchors")
    entry = lambda **a: _node("entry", a)  # noqa: E731
    head_row = _node("row", children=[entry(colname="1"), entry(namest="2", nameend="3")])
    head = _node("thead", children=[head_row])
    body = _node("tbody", children=[
        _node("row", children=[entry(colname="1", morerows="1"), entry(colname="2"),
                               entry(colname="3")]),
        _node("row", children=[entry(colname="2"), entry(colname="3")]),
    ])  # fmt: skip
    specs = [_node("colspec", {"colname": str(i), "colnum": str(i)}) for i in (1, 2, 3)]
    group = _node("tgroup", {"cols": "3"}, [*specs, head, body])
    root = _node("table", children=[group])
    for i, n in enumerate([root, *root.descendants()]):
        n.path = f"/n[{i}]"
    (table,) = table_gold.read_tables(root, vocab)
    assert (table.rows, table.columns, table.header_rows, table.problems) == (3, 3, 1, [])
    spans = {(c.row, c.column): (c.row_span, c.column_span) for c in table.cells}
    assert spans[(0, 1)] == (1, 2) and spans[(1, 0)] == (2, 1)
    assert (2, 1) in spans and (2, 0) not in spans


def test_teds_and_adjacency_scoring():
    t = frozenset
    gold = {"cells": [(0, 0, 1, 1, True, t({1})), (0, 1, 1, 1, True, t({2})),
                      (1, 0, 1, 1, False, t({3})), (1, 1, 1, 1, False, t({4}))]}  # fmt: skip
    merged_header = {"cells": [(0, 0, 1, 2, True, t({1, 2})), (1, 0, 1, 1, False, t({3})),
                               (1, 1, 1, 1, False, t({4}))]}  # fmt: skip
    assert table_scoring.teds(gold, gold) == 1.0
    assert 0 < table_scoring.teds(gold, merged_header) < 1
    assert table_scoring.adjacency(gold, gold) == (4, 4, 4)
    found, ours, reference = table_scoring.adjacency(gold, merged_header)
    assert reference == 4 and found < 4
    tree = table_scoring._Tree
    a = tree("f", [tree("d", [tree("a"), tree("c", [tree("b")])]), tree("e")])
    b = tree("f", [tree("c", [tree("d", [tree("a"), tree("b")])]), tree("e")])
    assert table_scoring.tree_distance(a, b) == 2  # Zhang-Shasha reference example


def test_unit_view_cuts_units_around_table_lines():
    from book_core.tables.view import unit_view

    join = lambda a, b: SimpleNamespace(previous_line_id=a, next_line_id=b)  # noqa: E731

    class Unit(SimpleNamespace):
        def model_copy(self, update):
            return Unit(**{**vars(self), **update})

    unit = Unit(id="u", line_ids=["a", "b", "c", "d"], joins=[join("a", "b"), join("b", "c"),
                join("c", "d")], continues_from="p", continues_to="n")  # fmt: skip
    table = SimpleNamespace(line_ids=["b"])
    final, removed, parts = unit_view([unit], [table])
    assert [u.line_ids for u in final] == [["a"], ["c", "d"]]
    assert final[0].id == "u" and final[0].continues_to is None and final[1].continues_to == "n"
    assert final[1].continues_from is None and parts == {final[1].id: "u"} and removed == []
    final, removed, _ = unit_view([unit], [SimpleNamespace(line_ids=["a", "b", "c", "d"])])
    assert final == [] and removed == ["u"]
