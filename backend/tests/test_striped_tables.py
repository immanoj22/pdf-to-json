"""A table without vertical rules whose rows alternate in shading: with a caption (label word of
the book, any language), a header row and aligned columns it is one table, not a graphic
organizer; the rows above and below the shaded bands (header, first rows, last rows) are in it;
a table continued on the next page is linked; a stack of separate, different boxes is still an
organizer."""

from pathlib import Path

import pymupdf
import pytest

from book_core.book_run import run_book
from book_core.cache_store import read_json
from book_core.figures.settings import FigureSettings
from book_core.model.common import BBox
from book_core.tables.detect import STRIPES, networks, stripes
from book_core.tables.rulings import Rule
from book_core.tables.settings import TableSettings

FONT = 9
XS = [40, 80, 190, 230, 330]  # column starts of the synthetic table (right edge 380)
HEAD = ["N.º", "Autor", "Año", "Objetivo", "Método"]


def _row(page, y, cells, font="helv"):
    for x, value in zip(XS, cells):
        page.insert_text((x + 3, y), value, fontsize=FONT, fontname=font)


def _striped(page, top, rows, number, caption, first=1, repeat=True):
    """Caption, header between two rules, then rows 18 pt apart; every second row shaded."""
    if caption:
        page.insert_text((40, top - 14), caption, fontsize=FONT)
    shape = page.new_shape()
    for r in range(rows):
        if r % 2 == 1:
            shape.draw_rect(pymupdf.Rect(40, top + 22 + 18 * r, 380, top + 22 + 18 * (r + 1)))
    shape.finish(color=None, fill=(0.88, 0.89, 0.9))
    shape.draw_line((40, top), (380, top))
    shape.draw_line((40, top + 20), (380, top + 20))
    shape.finish(color=(0, 0, 0), width=0.6)
    shape.commit()
    if repeat:
        _row(page, top + 14, HEAD, font="hebo")  # a header in bold, as printed
    for r in range(rows):
        _row(page, top + 34 + 18 * r, [f"{first + r}.", f"Autor {first + r}", str(2000 + first + r),
                                       f"Evaluar el tema {first + r}", "Revisión"])
    return top + 22 + 18 * rows


def _book(path):
    with pymupdf.open() as document:
        page = document.new_page(width=420, height=600)
        page.insert_text((40, 50), "Texto antes de la tabla del primer estudio.", fontsize=FONT)
        end = _striped(page, 100, 8, 1, "Tabla 1: Resumen de los estudios incluidos.")
        page.insert_text((40, end + 30), "Texto después de la primera tabla.", fontsize=FONT)
        page = document.new_page(width=420, height=600)
        end = _striped(page, 400, 9, 2, "Tabla 2: Características de otros estudios.")
        page.insert_text((200, end + 8), "Tabla 2 continúa en la página siguiente", fontsize=FONT)
        page = document.new_page(width=420, height=600)
        _striped(page, 40, 7, 2, None, first=10)
        page.insert_text((40, 400), "Texto final del capítulo después de la tabla.", fontsize=FONT)
        # Page 4: two boxes of different size and place, joined by an arrow (an organizer).
        page = document.new_page(width=420, height=600)
        shape = page.new_shape()
        for rect in (pymupdf.Rect(40, 60, 160, 100), pymupdf.Rect(220, 60, 380, 130),
                     pymupdf.Rect(60, 200, 200, 240)):
            shape.draw_rect(rect)
        shape.finish(color=(0, 0, 0), fill=(0.9, 0.9, 0.9), width=0.6)
        shape.commit()
        for y, text in ((84, "Causa uno"), (84, "Efecto")):
            page.insert_text((46 if text == "Causa uno" else 226, y), text, fontsize=FONT)
        page.insert_text((66, 224), "Causa dos", fontsize=FONT)
        document.save(path)
    return path


BOXES = {1: [(38, 98, 382, 100 + 22 + 18 * 8)], 2: [(38, 398, 382, 400 + 22 + 18 * 9)],
         3: [(38, 38, 382, 40 + 22 + 18 * 7)]}


class Models:
    identity = {"a": "stub", "b": "stub"}

    def __call__(self, number):
        boxes = [BBox(x0=a, y0=b, x1=c, y1=d) for a, b, c, d in BOXES.get(number, [])]
        return {name: [(box, 0.9, "table") for box in boxes] for name in ("a", "b")}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("striped")
    pdf = _book(tmp / "striped.pdf")
    return run_book(pdf, tmp / "out", tmp / "cache", workers=1, device="cpu",
                    figure_settings=FigureSettings(model_evidence="off"),
                    table_settings=TableSettings(model_evidence="on", structure_reader="off"), table_evidence=Models())


def _page(result, number):
    return read_json(Path(result["output"]) / f"page_{number:06d}.json.gz")


def _tables(result, number):
    return _page(result, number)["tables"]["tables"]


def test_shaded_rows_without_vertical_rules_are_one_table_with_header_and_every_row(run):
    (table,) = _tables(run, 1)
    assert (len(table["rows"]), len(table["columns"])) == (9, 5)  # header + 8 rows, 5 columns
    assert table["header_rows"] == 1
    assert table["structure_evidence"]["vertical_rules"] == 0
    assert "rules" in table["families"] and "alignment" in table["families"]
    box = table["bbox"]
    assert box["y0"] < 105 and box["y1"] > 100 + 22 + 18 * 8 - 20  # the top rule to the last row


def test_caption_becomes_the_title_and_row_numbers_stay_cells(run):
    page = _page(run, 1)
    (table,) = page["tables"]["tables"]
    assert table["title"] and table["title"]["numbered"] and table["title"]["number"] == "1"
    first_column = [c for c in table["cells"] if c["column"] == 0 and c["row"] > 0]
    assert len(first_column) == 8 and all(c["role"] != "list" for c in first_column)
    paragraphs = [u for u in page["units"]["units"] if u["id"] in set(page["table_view"]["removed"])]
    assert paragraphs  # the table owns its text: no row survives as a paragraph


def test_a_table_continued_on_the_next_page_is_linked(run):
    (first,) = _tables(run, 2)
    (second,) = _tables(run, 3)
    assert first["continues_to"]["table_id"] == second["id"]
    assert second["continues_from"]["table_id"] == first["id"]
    assert (len(first["rows"]), len(second["rows"])) == (10, 8)  # 9 + 7 rows, header on both


def test_boxes_of_different_size_and_place_are_still_an_organizer(run):
    page = _page(run, 4)
    assert not page["tables"]["tables"]


def test_stripes_need_equal_edges_one_above_another():
    def band(y0, y1, x0=40, x1=380):
        def rule(axis, at, start, end):
            return Rule(axis, at, start, end, 0.5, "fill_edge", f"{axis}{at}{start}")

        rules = [rule("h", y0, x0, x1), rule("h", y1, x0, x1), rule("v", x0, y0, y1),
                 rule("v", x1, y0, y1)]
        return networks(rules, FONT)[0]

    same = [band(100 + 36 * i, 118 + 36 * i) for i in range(STRIPES)]
    assert len(stripes(same, FONT)) == STRIPES
    mixed = [band(100, 118), band(136, 154, 100, 300), band(172, 190, 40, 200)]
    assert stripes(mixed, FONT) == []
    assert stripes(same[:2], FONT) == []
