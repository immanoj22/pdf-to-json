"""Step 14b tables: header association, group headers and section rows, cell content kinds,
title and note links (with unlinked flags), the navigation fix, cache closure and workers."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from test_cache_keys import closure

from book_core import caching
from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.model.common import BBox
from book_core.structure.decide import DEFAULT_CONFIG
from book_core.structure.navigation import classify
from book_core.tables import captions, grid
from book_core.tables.models import TableCell
from book_core.tables.records import _content, header_references
from book_core.tables.settings import TableSettings

FONT = 9
BOX = BBox(x0=0, y0=0, x1=10, y1=10)


# --- header association, group headers, section rows -----------------------------------


def _cell(row, column, rows=1, columns=1, role="data", text=True):
    return TableCell(
        id=f"c{row}{column}", row=row, column=column, row_span=rows, column_span=columns,
        header=role == "column_header", role=role, bbox=BOX,
        line_ids=[f"l{row}{column}"] if text else [],
        content=[{"kind": "text", "line_ids": [f"l{row}{column}"]}] if text else [],
    )  # fmt: skip


def test_header_references_include_group_headers_row_headers_and_sections():
    cells = [
        _cell(0, 0, role="column_header", text=False),
        _cell(0, 1, columns=2, role="column_header"),  # group header over two columns
        _cell(1, 0, role="column_header"),
        _cell(1, 1, role="column_header"),
        _cell(1, 2, role="column_header"),
        _cell(2, 0, columns=3, role="section"),
        _cell(3, 0, role="row_header"),
        _cell(3, 1),
        _cell(3, 2),
    ]
    refs = header_references(cells, 2, "text first column beside numeric data")
    named = {cells[k].id: [cells[h].id for h in v] for k, v in refs.items()}
    # A data cell: its group header, its column header, its row header, its section.
    assert named["c32"] == ["c01", "c12", "c30", "c20"]
    assert named["c31"] == ["c01", "c11", "c30", "c20"]
    assert named["c30"] == ["c10", "c20"]  # the row header: the stub head and the section
    assert named["c11"] == ["c01"]  # a sub-header is labelled by its group header
    assert "c00" not in {h for v in named.values() for h in v}  # empty headers label nothing


def _atom(x0, x1, y0=0.0, text="x"):
    return grid.Atom("s", "l", BBox(x0=x0, y0=y0, x1=x1, y1=y0 + 8), text, False, False, "f", 8)


def test_group_headers_widen_over_their_sub_columns_never_into_the_stub():
    columns = [(0, 50), (50, 80), (80, 110), (110, 140), (140, 170)]
    # Row 0: "Boys" centred over columns 1-2 (text only over the boundary 1|2), "Girls"
    # over 3-4; row 1: the sub-headers; column 0 holds the stub head in row 1.
    cells = [grid.Cell(0, 0), grid.Cell(0, 1, atoms=[_atom(70, 90)]), grid.Cell(0, 2),
             grid.Cell(0, 3, atoms=[_atom(130, 150)]), grid.Cell(0, 4)]  # fmt: skip
    cells += [grid.Cell(1, c, atoms=[_atom(c0 + 5, c1 - 5)]) for c, (c0, c1) in enumerate(columns)]
    for cell in cells:
        cell.header = True
    kept, widened = grid._group_headers(cells, 2, columns, 1)
    spans = {(c.row, c.column): c.column_span for c in kept}
    assert widened == 2 and spans[(0, 1)] == 2 and spans[(0, 3)] == 2 and spans[(0, 0)] == 1
    assert (0, 2) not in spans and (0, 4) not in spans


def test_section_lines_are_kept_whole_across_columns():
    def atom(span, line, x0, x1, y0, text):
        return grid.Atom(span, line, BBox(x0=x0, y0=y0, x1=x1, y1=y0 + 8), text, False, False,
                         "f", 8)  # fmt: skip

    atoms = [atom("a", "row", 0, 40, 0, "Topic: General "),
             atom("b", "row", 41, 90, 0, "features of bones"),
             atom("c", "data", 0, 20, 12, "AN1"), atom("d", "data", 60, 80, 12, "Y")]  # fmt: skip
    assert grid._section_lines(atoms, [50.0], 8) == {"row"}  # one continuous line, alone


def test_sparse_bands_may_cross_a_gap_the_full_bands_show():
    rows = []
    # A group header centred over two sub-columns (one piece), then full rows of 3 pieces.
    rows.append([(30, 70)])
    rows.append([(30, 70)])  # a centred count over both sub-columns
    for _ in range(4):
        rows.append([(0, 20), (30, 45), (55, 70)])
    atoms = [_atom(x0, x1, y0=12.0 * r) for r, pieces in enumerate(rows) for x0, x1 in pieces]
    separators, _ = grid.columns_from_text(atoms, 0, 70, 8)
    assert len(separators) == 2 and 45 < separators[1] < 55


# --- cell content ---------------------------------------------------------------------


def test_cell_content_keeps_units_whole_in_reading_order():
    lines = [SimpleNamespace(id=i, bbox=BBox(x0=0, y0=10 * k, x1=50, y1=10 * k + 8),
                             unit_kind=kind)
             for k, (i, kind) in enumerate([("a", "paragraph"), ("b", "list_item"),
                                            ("c", "list_item"), ("d", "table_text")])]  # fmt: skip
    by_id = {line.id: line for line in lines}
    evidence = SimpleNamespace(lines=lines, line=by_id.__getitem__, spans={})
    positions = {"a": (0, 0), "b": (0, 1), "c": (0, 2), "d": (0, 3)}
    units = {"u1": ["b"], "u2": ["c"]}
    items = _content(["a", "b", "c", "d"], [], units, [("eq", BBox(x0=0, y0=8, x1=40, y1=12))],
                     [], evidence, positions, 0)  # fmt: skip
    assert [(i.kind, i.unit_id, i.line_ids) for i in items] == [
        ("text", None, ["a"]), ("equation", "eq", []), ("list_item", "u1", ["b"]),
        ("list_item", "u2", ["c"]), ("text", None, ["d"]),
    ]  # fmt: skip
    with pytest.raises(ValueError, match="content"):
        TableCell(id="x", row=0, column=0, bbox=BOX, line_ids=["a"], content=[])


# --- titles and notes -------------------------------------------------------------------


def _candidate(table, side, unit, label=None, note=None, marker=None, kind="paragraph",
               rank=0, gap=0.5, in_table=False):  # fmt: skip
    return captions.Candidate(table_id=table, side=side, rank=rank, gap=gap, unit_id=unit,
                              line_ids=[f"{unit}-line"], kind=kind, lines=1, label=label,
                              note_label=note, marker=marker, marker_in_table=in_table)  # fmt: skip


def _record(table_id):
    return SimpleNamespace(
        id=table_id, rows=[(0, 1), (1, 2)], review_flags=[], header_rows=0,
        row_header_columns=0, cells=[],
        model_copy=lambda update, _id=table_id: SimpleNamespace(id=_id, **update),
    )  # fmt: skip


def test_titles_need_the_books_table_label_and_notes_its_note_label(monkeypatch):
    found = {
        1: [_candidate("t1", "above", "title1", label="table"),
            _candidate("t1", "below", "note1", note="note"),
            _candidate("t1", "below", "star1", marker="*", in_table=True, rank=1)],
        2: [_candidate("t2", "above", "title2", label="table"),
            _candidate("t2", "below", "note2", note="note")],
        3: [_candidate("t3", "above", "caption3", kind="caption"),  # unnumbered caption
            _candidate("t3", "below", "dagger3", marker="†")],  # marker the table lacks
        4: [_candidate("t4", "above", "title4", label="table")],  # linked to a figure
    }  # fmt: skip
    pages = {n: [_record(c[0].table_id)] for n, c in found.items()}
    monkeypatch.setattr(captions, "_validated", lambda table, update: SimpleNamespace(
        id=table.id, **{"title": None, "notes": [], "unlinked_texts": [], **update}))  # fmt: skip
    out, stats = captions.link(pages, found, {4: {"title4": "caption"}}, ["figure"])
    assert stats["table_labels"] == ["table"] and stats["note_labels"] == ["note"]
    assert stats["title_side"] == "above"
    (t1,) = out[1]
    assert t1.title.unit_id == "title1" and t1.title.numbered
    assert [n.unit_id for n in t1.notes] == ["note1", "star1"]
    (t3,) = out[3]
    assert t3.title is None and t3.notes == []
    reasons = {u.unit_id: u.reason for u in t3.unlinked_texts}
    assert reasons["caption3"] == captions.UNNUMBERED
    assert reasons["dagger3"] == captions.FOREIGN_MARKER
    (t4,) = out[4]
    assert t4.title is None and t4.unlinked_texts[0].reason == captions.FIGURE_CLAIM


def test_without_table_numbering_nothing_is_linked_and_captions_are_flagged(monkeypatch):
    found = {1: [_candidate("t1", "above", "cap", kind="caption")]}
    monkeypatch.setattr(captions, "_validated", lambda table, update: SimpleNamespace(
        id=table.id, **{"title": None, "notes": [], "unlinked_texts": [], **update}))  # fmt: skip
    out, stats = captions.link({1: [_record("t1")]}, found, {}, [])
    assert stats["table_labels"] == [] and out[1][0].title is None
    assert out[1][0].unlinked_texts[0].reason == captions.NO_NUMBERING


def test_note_label_needs_text_after_it():
    assert captions.NOTE_WORD.match("Note. Values are means.")
    assert captions.NOTE_WORD.match("Note. *p < .05")
    assert not captions.NOTE_WORD.match("Contd...")


# --- navigation -----------------------------------------------------------------------


def _unit(text, start=50.0, stream="main", lines=1, line_entries=(), lead=None, tokens=None):
    return {
        "text": text, "start": start, "size": 8.0, "stream": stream, "position": 0,
        "block": 0.0, "letters": sum(c.isalpha() for c in text), "lines": lines,
        "tokens": tokens or len(text.split()), "navigation_entries": [], "lead_run": lead,
        "separator": False, "line_entries": [list(r) for r in line_entries],
    }  # fmt: skip


WORDS = (
    "abbot acorn badge baker cable camel dairy delta eagle earth "
    "fable fancy gamma giant habit hazel icing ideal jelly joker"
).split()


def _page(number, units):
    for k, unit in enumerate(units):
        unit["position"], unit["block"] = k, k / 100
    return {"page": number, "label": str(number), "navigation": [], "units": units}


def test_a_merged_index_unit_is_read_line_by_line():
    first = [_unit("Index", tokens=1)] + [_unit(f"{w} 12, 14") for w in WORDS[:10]]
    rows = []
    for k, word in enumerate(WORDS[10:]):
        rows.append((50.0, f"{word} 31, 40", f"{word} 31, 40", 8, 3))
        if k % 3 == 0:
            rows.append((58.0, "sub-entry 7", "sub-entry 7", 8, 2))  # a deeper line
    merged = _unit(" ".join(r[1] for r in rows), lines=len(rows), line_entries=rows,
                   tokens=3 * len(rows))  # fmt: skip
    body = [(50.0, f"{w} words of running text", f"{w} text", 20, 5) for w in reversed(WORDS)]
    paragraph = _unit("running text", lines=len(body), line_entries=body, tokens=100)
    pages = [_page(1, first), _page(2, [merged]), _page(3, [paragraph])]
    found, stats, _ = classify(pages, [], DEFAULT_CONFIG)
    kinds = {n.page: n.kind for n in found}
    assert kinds == {1: "index", 2: "index"}  # the body paragraph is not split into entries
    assert stats[2]["entries"] == 10


def test_a_glossary_continues_onto_a_page_set_as_a_table_region():
    lead = {"letters": 5, "rest_letters": 20}
    entries = [_unit(f"{w} a word defined by several more words here", lead=lead)
               for w in WORDS[:10]]  # fmt: skip
    first = [_unit("Glossary", tokens=1), *entries]
    table = [_unit(f"{w} another word defined by several more words", stream="table", lead=lead)
             for w in WORDS[10:]]  # fmt: skip
    alone = [_unit(f"{w} another word defined by several more words", stream="table", lead=lead)
             for w in WORDS[10:]]  # fmt: skip
    pages = [_page(1, first), _page(2, table), _page(3, []), _page(4, alone)]
    found, _, _ = classify(pages, [], DEFAULT_CONFIG)
    kinds = {n.page: n for n in found}
    assert kinds[1].kind == kinds[2].kind == "glossary"
    assert "entries set in a table region" in kinds[2].reasons
    assert 4 not in kinds  # a table page alone never starts a run


# --- cache closure ----------------------------------------------------------------------


def test_cache_closure_covers_the_14b_modules():
    assert closure("tables/captions.py") <= set(caching.coverage_files("tables"))
    assert closure("tables/cache.py") <= set(caching.coverage_files("tables"))
    assert closure("structure/cache.py") <= set(caching.coverage_files("structure"))


# --- a small book: numbered titles, notes, group headers, stub column, workers ------------


def _text(page, x, y, text):
    page.insert_text((x, y), text, fontsize=FONT)


def _table(page, top, number):
    """An unboxed table: a title above, group headers over M/SD, a stub column, notes below."""
    _text(page, 40, top - 12, f"Table 1.{number} Pupils by group")
    shape = page.new_shape()
    for y in (top, top + 34, top + 100):
        shape.draw_line((40, y), (380, y))
    shape.finish(color=(0, 0, 0), width=0.6)
    shape.commit()
    _text(page, 180, top + 13, "Boys")
    _text(page, 300, top + 13, "Girls")
    for label, x in (("Group", 45), ("M", 160), ("SD", 215), ("M", 280), ("SD", 335)):
        _text(page, x, top + 29, label)
    for i, (name, *values) in enumerate([("Age", "12.4*", "1.3", "11.9", "1.1"),
                                         ("Score", "45.1", "6.2", "47.0", "5.8"),
                                         ("Height", "151.0", "8.8", "149.2", "7.9")]):  # fmt: skip
        y = top + 50 + 18 * i
        _text(page, 45, y, name)
        for value, x in zip(values, (160, 215, 280, 335), strict=True):
            _text(page, x, y, value)
    _text(page, 40, top + 114, "Note. Values are means and standard deviations.")
    _text(page, 40, top + 128, "* p < .05")


def _book(path):
    with pymupdf.open() as document:
        for number in (1, 2):
            page = document.new_page(width=420, height=600)
            _text(page, 40, 60, "Paragraph text before the table runs across the whole line.")
            _table(page, 120, number)
            _text(page, 40, 320, "Closing paragraph after the table on this page.")
        document.save(path)
    return path


class Detectors:
    identity = {"a": "stub", "b": "stub"}

    def __call__(self, number):
        box = BBox(x0=38, y0=118, x1=382, y1=222)
        return {name: [(box, 0.9, "table")] for name in ("a", "b")}


@pytest.fixture
def titled_pdf(tmp_path):
    return _book(tmp_path / "titled.pdf")


def _run(pdf, out, cache, workers):
    return run_book(pdf, out, cache, workers=workers, device="cpu",
                    table_settings=TableSettings(model_evidence="on"),
                    table_evidence=Detectors())  # fmt: skip


def _page_json(result, number):
    return read_json(Path(result["output"]) / f"page_{number:06d}.json.gz")


def _line_text(page, lid):
    spans = page["source"]["store"]["spans"]
    return "".join(spans[s]["raw_text"] for s in page["line_spans"].get(lid, []))


def test_titles_notes_headers_and_workers_on_a_small_book(titled_pdf, tmp_path):
    serial = _run(titled_pdf, tmp_path / "a_out", tmp_path / "a", 1)
    for number in (1, 2):
        page = _page_json(serial, number)
        (table,) = page["tables"]["tables"]
        assert table["page_label"] is None or isinstance(table["page_label"], str)
        assert table["provenance"]["engine"] == "book_core.tables"
        title = table["title"]
        assert title and title["numbered"] and title["unit_id"]
        assert _line_text(page, title["line_ids"][0]).startswith(f"Table 1.{number}")
        note_text = " ".join(_line_text(page, lid) for n in table["notes"] for lid in n["line_ids"])
        assert "Note." in note_text and "p < .05" in note_text
        cells = {c["id"]: c for c in table["cells"]}
        boys = [c for c in table["cells"] if c["role"] == "column_header" and c["column_span"] == 2]
        assert len(boys) == 2  # the two group headers span their M and SD columns
        stub = [c for c in table["cells"] if c["role"] == "row_header"]
        assert len(stub) == 3 and table["row_header_columns"] == 1
        data = [c for c in table["cells"] if c["role"] == "data" and c["line_ids"] + c["span_refs"]]
        for cell in data:
            roles = [cells[h]["role"] for h in cell["header_cell_ids"]]
            assert roles.count("column_header") == 2 and roles.count("row_header") == 1
        for cell in table["cells"]:
            covered = [lid for item in cell["content"] for lid in item["line_ids"]]
            assert sorted(covered) == sorted(cell["line_ids"])
        # Titles and notes stay in their units: every line is owned once.
        view = page["table_view"]
        units = [u for u in page["units"]["units"] if u["id"] not in set(view["removed"])]
        owned = [lid for u in [*units, *view["added"]] for lid in u["line_ids"]]
        owned += [lid for t in page["tables"]["tables"] for lid in t["line_ids"]]
        assert sorted(owned) == sorted(set(owned)) and set(owned) >= set(title["line_ids"])
    book = read_json(Path(serial["output"]) / "book.json.gz")
    assert book["tables"]["texts"]["table_labels"] == ["table"]
    assert book["tables"]["texts"]["note_labels"] == ["note"]

    def files(result):
        root = Path(result["output"])
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file()}  # fmt: skip

    parallel = _run(titled_pdf, tmp_path / "b_out", tmp_path / "b", 2)
    assert files(serial) == files(parallel)


# --- TableFormer second reader ------------------------------------------------------------


def _raster(width=100.0, height=200.0, scale=2):
    import io

    from PIL import Image

    from book_core.extraction.rasters import RasterPage

    buffer = io.BytesIO()
    Image.new("RGB", (int(width * scale), int(height * scale)), "white").save(buffer, "PNG")
    return RasterPage(png=buffer.getvalue(), width=int(width * scale),
                      height=int(height * scale), page_width=width, page_height=height)  # fmt: skip


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_upright_crop_maps_pixels_back_to_the_page(rotation):
    import io

    from PIL import Image

    from book_core.tables import opinion

    box = BBox(x0=20, y0=30, x1=60, y1=150)
    png, to_page = opinion.upright_crop(_raster(), box, rotation)
    with Image.open(io.BytesIO(png)) as image:
        width, height = image.size
    corners = [to_page(x, y) for x in (0, width) for y in (0, height)]
    xs, ys = sorted({round(c[0], 3) for c in corners}), sorted({round(c[1], 3) for c in corners})
    assert (xs[0], ys[0], xs[-1], ys[-1]) == (14.0, 24.0, 66.0, 156.0)  # the padded region
    if rotation in {90, 270}:
        assert width > height  # the tall rotated table is upright: its text runs along x


def _table_record(header_evidence="no header evidence"):
    from book_core.tables.models import TableAnchor, TableRecord

    cells = [_cell(r, c) for r in range(3) for c in range(2)]
    return TableRecord(
        id="t", page=1, bbox=BOX, rows=[(0, 1), (1, 2), (2, 3)], columns=[(0, 1), (1, 2)],
        cells=cells, line_ids=[lid for c in cells for lid in c.line_ids],
        structure_method="text+text_rows", families=["alignment", "models"],
        structure_evidence={"header": header_evidence},
        anchor=TableAnchor(stream_id="s", position=-1), confidence=0.8, reasons=["test"],
    )  # fmt: skip


def test_tableformer_header_rows_only_without_header_evidence_and_disagreement_flags():
    from book_core.tables import opinion

    same = [(r, c, 1, 1, r == 0, BOX) for r in range(3) for c in range(2)]
    update, stats = opinion.apply(_table_record(), same, 1)
    assert update["header_rows"] == 1 and stats == {"header_rows": 1}
    roles = {(c.row, c.column): c.role for c in update["cells"]}
    assert roles[(0, 0)] == "column_header" and roles[(1, 0)] == "data"
    body = next(c for c in update["cells"] if (c.row, c.column) == (2, 1))
    assert body.header_cell_ids == ["c01"]
    assert opinion.HEADER_RULE in update["review_flags"]
    update, stats = opinion.apply(_table_record("header fill"), same, 2)
    assert update == {} and stats == {}  # our header evidence stands
    other = [(0, 0, 1, 1, False, BOX)]  # one cell: a different structure
    update, stats = opinion.apply(_table_record("header fill"), other, 0)
    assert stats == {"disagreements": 1} and "different structure" in update["review_flags"][-1]
