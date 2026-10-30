"""A folio set beside a column's first line is its own line, and so becomes folio furniture.

Step 18: a roman folio printed just right of a column's first line, larger and bold, shared
its baseline and joined that body line, so a printed folio stayed in a paragraph. A gap of
an em or more where the type size also changes is a line boundary.
"""

import json
from pathlib import Path

import pymupdf
from test_continuity import _run

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.lines import build_lines

WORDS = (
    "The reviewers listed here read every chapter of the book and checked it carefully "
    "while the editors compared each table with the sources and corrected the figures "
).split()


def folio_book(path, pages=6):
    """Two columns whose first lines share a baseline; a bold folio, larger than the text,
    14 pt right of the column (the Step 18 geometry)."""
    with pymupdf.open() as doc:
        for n in range(1, pages + 1):
            page = doc.new_page(width=672, height=852)
            page.insert_text((613, 78), str(n), fontsize=12, fontname="hebo")
            for k in range(30):
                for x, end in ((90, 336), (342, 600)):
                    words, text = WORDS[(n * 7 + k * 3 + x) % 20 :] + WORDS, ""
                    for word in words:
                        if pymupdf.get_text_length(f"{text}{word} ", "helv", 9) > end - x:
                            break
                        text += word + " "
                    # Justified: the line reaches the column edge (filled with stops).
                    while pymupdf.get_text_length(text + ".", "helv", 9) < end - x:
                        text += "."
                    page.insert_text((x, 75 + 13 * k), text, fontsize=9, fontname="helv")
        doc.save(path)
    return path


def test_the_folio_is_its_own_visual_line(tmp_path):
    pdf = folio_book(tmp_path / "folios.pdf")
    native = PyMuPDFExtractor("cpu").extract_object_page(pdf, 3)
    store = native.page.store
    lines = build_lines(native)
    assert "3" in ["".join(store.spans[s].raw_text for s in line.span_ids) for line in lines]


def test_the_folio_is_published_as_folio_furniture(tmp_path):
    result = _run(folio_book(tmp_path / "folios.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    data = json.loads((Path(result["book_json"]) / "book.json").read_text("utf-8"))
    folios = {f["content"]["text"] for f in data["furniture"] if f["kind"] == "folio"}
    assert folios == {"1", "2", "3", "4", "5", "6"}
    assert [page["label"] for page in data["pages"]] == ["1", "2", "3", "4", "5", "6"]


def test_the_first_items_of_two_bulleted_columns_are_separate_lines(tmp_path):
    """A list marker an em or more after the previous text opens its own line (Step 18:
    reviewer columns whose first lines shared a baseline were read as one line)."""
    path = tmp_path / "columns.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=672, height=852)
        left = "Probal Chatterji, Professor, Department of ENT"
        page.insert_text((75, 72), "●", fontsize=8, fontname="zadb")
        page.insert_text((90, 72), left, fontsize=9, fontname="helv")
        start = 90 + pymupdf.get_text_length(left, "helv", 9) + 10
        page.insert_text((start, 72), "●", fontsize=8, fontname="zadb")
        page.insert_text((start + 15, 72), "Sudhakar Vaidya, President", fontsize=9)
        doc.save(path)
    native = PyMuPDFExtractor("cpu").extract_object_page(path, 1)
    store = native.page.store
    texts = ["".join(store.spans[s].raw_text for s in line.span_ids).strip()
             for line in build_lines(native)]  # fmt: skip
    assert not any("Chatterji" in t and "Vaidya" in t for t in texts)


def test_a_larger_heading_across_a_narrow_gutter_is_its_own_line(tmp_path):
    """Step 19: a 12 pt two-line heading opening the right column, 10 pt from the 10 pt body
    of the left column, joined the body line on its baseline (a gap under one larger size)."""
    path = tmp_path / "gutter.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=540, height=720)
        body = "position and to prevent the spread of"
        start = 83 + pymupdf.get_text_length(body, "tiro", 10) + 10
        page.insert_text((83, 610), body, fontsize=10, fontname="tiro")
        page.insert_text((start, 610), "DISSECTION HALL: MAINTENANCE", fontsize=12, fontname="hebo")
        page.insert_text((83, 624), "infection to others and to the", fontsize=10, fontname="tiro")
        page.insert_text((start, 624), "AND PREPARATION", fontsize=12, fontname="hebo")
        doc.save(path)
    native = PyMuPDFExtractor("cpu").extract_object_page(path, 1)
    store = native.page.store
    texts = ["".join(store.spans[s].raw_text for s in line.span_ids).strip()
             for line in build_lines(native)]  # fmt: skip
    assert "DISSECTION HALL: MAINTENANCE" in texts
    assert "AND PREPARATION" in texts


def test_a_larger_word_inside_a_line_stays_in_the_line(tmp_path):
    """A size change across a word space is not a boundary."""
    path = tmp_path / "inline.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=540, height=720)
        lead = "The term "
        x = 72 + pymupdf.get_text_length(lead, "tiro", 10)
        page.insert_text((72, 100), lead, fontsize=10, fontname="tiro")
        word = "HOMEOSTASIS "
        page.insert_text((x, 100), word, fontsize=12.5, fontname="hebo")
        x += pymupdf.get_text_length(word, "hebo", 12.5)
        page.insert_text((x, 100), "keeps the body stable.", fontsize=10, fontname="tiro")
        doc.save(path)
    native = PyMuPDFExtractor("cpu").extract_object_page(path, 1)
    lines = build_lines(native)
    assert len(lines) == 1


def test_a_bullet_set_larger_than_its_item_stays_with_it(tmp_path):
    """A list bullet glyph larger than the item text, a narrow gap before the text, is not a
    line of its own (only text on both sides of a size change is split)."""
    path = tmp_path / "bullet.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=540, height=720)
        page.insert_text((72, 100), "\u00be", fontsize=13, fontname="tiro")
        x = 72 + pymupdf.get_text_length("\u00be", "tiro", 13) + 7.5
        page.insert_text((x, 100), "Blood tests to rule out other causes.", fontsize=9.5)
        doc.save(path)
    native = PyMuPDFExtractor("cpu").extract_object_page(path, 1)
    assert len(build_lines(native)) == 1
