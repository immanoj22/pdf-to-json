"""Text order inside table cells: produced in the cell's own order, and measured separately.

Step 18: multi-line cell prose came out reversed while full TEDS stayed high, because TEDS
compares each cell's tokens as a set. Step 19: a cell whose content fails its check stops a
development run; production reads that cell in source order and flags its table must_check.
"""

from types import SimpleNamespace

import pytest
from test_tables import OrganizerModels, _book, _tables

from book_core.book_run import StageFailure, run_book
from book_core.evaluation.table_scoring import in_cell_order, score, teds
from book_core.model.common import BBox
from book_core.tables import records
from book_core.tables.models import CELL_FALLBACK, CellContent, TableCell
from book_core.tables.records import _cell_lines, _content
from book_core.tables.settings import TableSettings


def box(y0, y1, x0=0, x1=100):
    return BBox(x0=x0, y0=y0, x1=x1, y1=y1)


def test_a_cell_reads_its_rows_first_to_last_whatever_the_page_order():
    boxes = {"a": box(10, 20), "b": box(22, 32), "c": box(34, 44)}
    # The page's reading order crossed the table row by row: c, then b, then a.
    positions = {"c": (0, 0), "b": (0, 5), "a": (0, 9)}
    assert _cell_lines({"a", "b", "c"}, boxes, positions, 0) == ["a", "b", "c"]


def test_lines_sharing_a_row_keep_the_page_order():
    # Two runs of one row (a label and its value); any script or direction.
    boxes = {"right": box(10, 20, 60, 100), "left": box(11, 19, 0, 50), "next": box(22, 32)}
    positions = {"right": (0, 1), "left": (0, 2), "next": (0, 3)}
    assert _cell_lines(set(boxes), boxes, positions, 0) == ["right", "left", "next"]


def grid(order):
    tokens = [(1, n) for n in range(4)]
    return {"cells": [(0, 0, 1, 1, False, frozenset(tokens))], "header_rows": 0,
            "rows": 1, "columns": 1, "problems": [], "extra": frozenset(),
            "sequences": {0: [tokens[i] for i in order]}}  # fmt: skip


def test_in_cell_order_sees_what_teds_cannot():
    gold, reversed_cell = grid([0, 1, 2, 3]), grid([3, 2, 1, 0])
    assert teds(gold, reversed_cell, content=True) == 1.0
    assert in_cell_order(gold, reversed_cell) == (0, 6, 0, 1)
    assert in_cell_order(gold, grid([0, 1, 2, 3])) == (6, 6, 1, 1)
    scores = score({("t", 1): gold}, {(1, 0): reversed_cell})
    assert scores["teds_full_mean"] == 1.0 and scores["in_cell_order_pairs"] == 0.0
    assert scores["in_cell_order_exact"] == 0.0 and scores["in_cell_order_cells"] == 1


def test_a_unit_interrupted_by_a_loose_line_is_read_once():
    # Step 19 (Spanish): a paragraph wholly in a cell, with a loose line of the cell between
    # its lines on the page; reading by rows met the paragraph twice and listed it twice.
    boxes = {"a": box(10, 20), "b": box(22, 32), "c": box(34, 44)}
    lines = [SimpleNamespace(id=lid, bbox=b) for lid, b in boxes.items()]
    evidence = SimpleNamespace(lines=lines, spans={},
                               line=lambda lid: SimpleNamespace(unit_kind="paragraph"))  # fmt: skip
    positions = {"a": (0, 0), "c": (0, 1), "b": (0, 2)}
    content = _content(["a", "b", "c"], [], {"u": ["a", "c"]}, [], [], evidence, positions, 0)
    assert [(item.kind, item.unit_id, item.line_ids) for item in content] == [
        ("paragraph", "u", ["a", "c"]),
        ("text", None, ["b"]),
    ]
    TableCell(id="cell", row=0, column=0, bbox=box(10, 44), line_ids=["a", "b", "c"],
              unit_ids=["u"], content=content)  # fmt: skip
    # The same when the line between is another unit's (paragraphs side by side in a cell).
    units = {"u": ["a", "c"], "v": ["b"]}
    content = _content(["a", "b", "c"], [], units, [], [], evidence, positions, 0)
    assert [(item.unit_id, item.line_ids) for item in content] == [("u", ["a", "c"]), ("v", ["b"])]


@pytest.fixture
def table_pdf(tmp_path):
    return _book(tmp_path / "tables.pdf")


@pytest.fixture
def broken_first_cell(monkeypatch):
    """The first cell's content holds one of its lines twice (any cause of a failed check)."""
    real, calls = records._content, []

    def broken(whole, *args):
        content = real(whole, *args)
        calls.append(1)
        if len(calls) == 1 and whole:
            content = [*content, CellContent(kind="text", line_ids=[whole[0]])]
        return content

    monkeypatch.setattr(records, "_content", broken)


def test_a_failed_cell_stops_a_development_run(broken_first_cell, table_pdf, tmp_path):
    with pytest.raises(StageFailure, match="(?s)Stage tables failed.*lines and span ranges once"):
        run_book(table_pdf, tmp_path / "out", tmp_path / "cache", workers=1, device="cpu",
                 table_settings=TableSettings(model_evidence="on"),
                 table_evidence=OrganizerModels())  # fmt: skip


def test_production_reads_a_failed_cell_in_source_order_and_flags_it(
    broken_first_cell, table_pdf, tmp_path
):
    result = run_book(table_pdf, tmp_path / "out", tmp_path / "cache", workers=1,
                      device="cpu", mode="production",
                      table_settings=TableSettings(model_evidence="on"),
                      table_evidence=OrganizerModels())  # fmt: skip
    tables = [t for n in range(1, 6) for t in _tables(result, n) if t.get("review_flags")]
    flagged = [t for t in tables if any(f.startswith(CELL_FALLBACK) for f in t["review_flags"])]
    assert len(flagged) == 1 and flagged[0]["review_status"] == "must_check"
    (reason,) = [f for f in flagged[0]["review_flags"] if f.startswith(CELL_FALLBACK)]
    assert "row 0, column 0" in reason and "read in source order" in reason
    cell = next(c for c in flagged[0]["cells"] if c.get("row", 0) == 0 and c.get("column", 0) == 0)
    assert [item["kind"] for item in cell["content"]] == ["text"]
    assert sorted(cell["content"][0]["line_ids"]) == sorted(cell["line_ids"])
    # Every other table flag stays needs_review.
    others = [t for t in tables if t is not flagged[0]]
    assert all(t["review_status"] == "needs_review" for t in others)
