"""A rule under text is an underline only when it follows that text, not a column.

Step 17b: coloured column-wide separators under headings that nearly fill their column were
read as underlines (the rule passed the heading's end by less than a font size).
"""

import pymupdf

from book_core.assembly.links import PyMuPDFLinkExtractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor


def marks(tmp_path, draw):
    path = tmp_path / "rules.pdf"
    with pymupdf.open() as doc:
        draw(doc.new_page(width=420, height=600))
        doc.save(path)
    store = PyMuPDFExtractor("cpu").extract_object_page(path, 1).page.store
    found = PyMuPDFLinkExtractor().extract_marks(path, 1, store, [])
    return [store.spans[m.span].raw_text[m.start : m.end] for m in found.underlines]


def test_a_column_wide_separator_under_a_heading_is_not_an_underline(tmp_path):
    def draw(page):
        heading = "INNERVATION OF MUSCLE"
        page.insert_text((75, 272), heading, fontsize=12, fontname="hebo", color=(0.55, 0.2, 0.4))
        end = 75 + pymupdf.get_text_length(heading, "hebo", 12)
        # The column ends 5 pt after the heading; the separator spans the column.
        page.draw_line((75, 274), (end + 5, 274), color=(0.55, 0.2, 0.4), width=0.75)

    assert marks(tmp_path, draw) == []


def test_an_underline_drawn_under_its_text_is_kept_across_spans(tmp_path):
    def draw(page):
        page.insert_text((40, 100), "Read the ", fontsize=10)
        start = 40 + pymupdf.get_text_length("Read the ", fontsize=10)
        page.insert_text((start, 100), "manual", fontsize=10, fontname="tiro")
        middle = start + pymupdf.get_text_length("manual", "tiro", 10)
        page.insert_text((middle, 100), " online", fontsize=10)
        end = middle + pymupdf.get_text_length(" online", fontsize=10)
        page.draw_line((start, 102), (end, 102), width=0.6)

    assert "".join(marks(tmp_path, draw)).replace(" ", "") == "manualonline"
