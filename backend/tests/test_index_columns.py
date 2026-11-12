"""An index set in columns is read down each column, not across the rows."""

from types import SimpleNamespace

from book_core.lists.glossary import column_order

COLUMNS = ((78.0, 214.0), (226.0, 354.0), (374.0, 510.0))


def line(name, column, row, start_in=0.0):
    start, end = COLUMNS[column]
    return SimpleNamespace(id=name, start=start + start_in, end=end, block=100.0 + 12.0 * row,
                           size=9.0, blank=False)  # fmt: skip


def page():
    """Three columns of five rows each, named c<column><row>; a note above the columns."""
    note = SimpleNamespace(id="note", start=218.0, end=370.0, block=70.0, size=9.0, blank=False)
    rows = [line(f"c{c}{r}", c, r) for c in range(3) for r in range(5)]
    return note, rows


def test_lines_read_across_the_rows_are_read_down_each_column():
    note, rows = page()
    across = [note, *sorted(rows, key=lambda x: (x.block, x.start))]
    new, evidence = column_order(across)
    assert [x.id for x in new] == ["note", *[f"c{c}{r}" for c in range(3) for r in range(5)]]
    assert evidence["columns"] == 3 and evidence["head"] == 1


def test_an_order_that_already_runs_down_the_columns_is_left_alone():
    note, rows = page()
    new, _ = column_order([note, *rows])
    assert [x.id for x in new] == ["note", *[x.id for x in rows]]


def test_one_column_or_a_line_across_the_columns_leaves_the_order():
    _, rows = page()
    single = [line(f"s{r}", 0, r) for r in range(10)]
    assert column_order(single)[0] is None
    across = SimpleNamespace(id="wide", start=78.0, end=510.0, block=130.0, size=9.0, blank=False)
    assert column_order([*rows, across])[0] is None


def test_a_larger_letter_heading_sets_the_row_and_nothing_above_it_is_a_head():
    """The first column opens with a letter set larger than the text: its baseline is 5 points
    below the second column's first line. Both are the first row of the columns, not a head."""
    rows = [line(f"c{c}{r}", c, r) for c in range(2) for r in range(1, 6)]
    letter = SimpleNamespace(id="A", start=78.0, end=86.0, block=105.0, size=14.0, blank=False)
    top = SimpleNamespace(id="top", start=226.0, end=290.0, block=100.0, size=9.0, blank=False)
    new, evidence = column_order([letter, top, *rows])
    assert evidence["head"] == 0
    assert [x.id for x in new] == ["A", "c01", "c02", "c03", "c04", "c05",
                                   "top", "c11", "c12", "c13", "c14", "c15"]  # fmt: skip


def test_a_column_of_a_few_lines_is_not_an_index_column():
    _, rows = page()
    stray = SimpleNamespace(id="stray", start=30.0, end=70.0, block=300.0, size=9.0, blank=False)
    assert column_order([*rows, stray])[0] is None


def test_the_top_lines_of_a_column_that_begins_higher_are_not_a_head():
    """The second column's first two lines sit above everything in the first (its letter
    heading is not among the lines): they start where the column's other lines start."""
    first = [line(f"c0{r}", 0, r) for r in range(3, 8)]
    second = [line(f"c1{r}", 1, r) for r in range(0, 8)]
    new, evidence = column_order([*first, *second])
    assert evidence["head"] == 0
    assert [x.id for x in new] == [f"c0{r}" for r in range(3, 8)] + [f"c1{r}" for r in range(8)]
