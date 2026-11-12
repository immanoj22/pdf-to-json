"""Gutter-aware line building (Step 20): never join line pieces across a column gutter.

A gutter is a white channel between columns, found from many rows that end and start at the
same x, not from the size of one gap: a narrow gutter can be narrower than a justified word
space. Word gaps, list markers and pieces of one cell stay joined.
"""

import pymupdf
import pytest

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.lines import build_lines

WORDS = (
    "The reviewers listed here read every chapter of the book and checked it carefully "
    "while the editors compared each table with the sources and corrected the figures "
    "before the final proofs went to press in the autumn of that year"
).split()
SIZE = 9


def fill(x0, x1, seed):
    """Words from the list that fit between x0 and x1 at SIZE (left-aligned)."""
    text = ""
    for word in WORDS[seed % len(WORDS) :] + WORDS:
        if pymupdf.get_text_length(f"{text}{word}", "helv", SIZE) > x1 - x0:
            break
        text += word + " "
    return text.strip()


def texts(path, number=1):
    native = PyMuPDFExtractor("cpu").extract_object_page(path, number)
    store = native.page.store
    return [
        "".join(store.spans[s].raw_text for s in line.span_ids).strip()
        for line in build_lines(native)
    ]


def column_page(path, columns, rows=20, gutter=6.0, width=560):
    """``columns`` columns of equal width, ``gutter`` points apart, ragged right (so only the
    column starts line up); each column line is its own native line. Returns the expected
    text of every row piece."""
    step = (width - 2 * 40 - gutter * (columns - 1)) / columns
    expected = []
    with pymupdf.open() as doc:
        page = doc.new_page(width=width + 40, height=800)
        for k in range(rows):
            for c in range(columns):
                x0 = 40 + c * (step + gutter)
                text = fill(x0, x0 + step, k * 5 + c * 3)
                page.insert_text((x0, 60 + 12 * k), text, fontsize=SIZE, fontname="helv")
                expected.append(text)
        doc.save(path)
    return expected


@pytest.mark.parametrize("columns", [2, 3, 4, 5])
def test_columns_with_a_narrow_gutter_never_join(tmp_path, columns):
    path = tmp_path / "columns.pdf"
    expected = column_page(path, columns, gutter=6.0)  # under MERGE_GAP x 9 pt = 11.25 pt
    found = texts(path)
    assert sorted(found) == sorted(expected)


def test_six_columns_of_short_lines_never_join(tmp_path):
    """Six columns 3x the font size wide (lines under 4x the font size), 5 pt apart."""
    path = tmp_path / "six.pdf"
    short = ["dose", "time", "rate", "mass", "area", "flow", "size", "heat"]
    expected = []
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=400)
        for k in range(8):
            for c in range(6):
                text = short[(k + c) % len(short)]
                page.insert_text((40 + c * 32, 60 + 12 * k), text, fontsize=SIZE, fontname="helv")
                expected.append(text)
        doc.save(path)
    assert pymupdf.get_text_length("dose", "helv", SIZE) < 4 * SIZE
    assert sorted(texts(path)) == sorted(expected)


def test_justified_word_pieces_on_one_baseline_stay_one_line(tmp_path):
    """Words set as separate pieces with wide justified spaces (wider than the narrow gutter
    above): the gaps do not line up row to row, so every row stays one line."""
    path = tmp_path / "justified.pdf"
    rows = []
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        for k in range(20):
            words = fill(40, 330, k * 7).split()
            natural = sum(pymupdf.get_text_length(w, "helv", SIZE) for w in words)
            space = (330 - 40 - natural) / (len(words) - 1)
            assert space < 1.25 * SIZE
            x = 40
            for word in words:
                page.insert_text((x, 60 + 12 * k), word, fontsize=SIZE, fontname="helv")
                x += pymupdf.get_text_length(word, "helv", SIZE) + space
            rows.append(words)
        doc.save(path)
    found = texts(path)
    assert len(found) == len(rows)
    for words in rows:
        assert any(line.split() == words for line in found), words


def test_hanging_bullets_stay_with_their_text(tmp_path):
    path = tmp_path / "bullets.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        for k in range(8):
            page.insert_text((40, 60 + 12 * k), "•", fontsize=SIZE, fontname="helv")
            page.insert_text((48, 60 + 12 * k), fill(48, 300, k * 4), fontsize=SIZE)
            page.insert_text((40, 200 + 12 * k), f"{k + 1}.", fontsize=SIZE, fontname="helv")
            page.insert_text((52, 200 + 12 * k), fill(52, 300, k * 6), fontsize=SIZE)
        doc.save(path)
    found = texts(path)
    assert len(found) == 16
    assert all(len(line.split()) > 1 for line in found)  # no marker stands alone


def test_table_rows_split_at_columns_and_cells_stay_whole(tmp_path):
    """Cells set as pieces close together across aligned table columns are separate lines;
    a cell made of two runs (bold term, then text) stays one line."""
    path = tmp_path / "table.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        for k in range(6):
            y = 60 + 14 * k
            page.insert_text((40, y), "Term", fontsize=SIZE, fontname="hebo")
            page.insert_text((40 + pymupdf.get_text_length("Term ", "hebo", SIZE), y),
                             f"row {k}", fontsize=SIZE, fontname="helv")  # fmt: skip
            page.insert_text((120, y), f"{k * 13 + 7}.5", fontsize=SIZE, fontname="helv")
            page.insert_text((150, y), "mg per day", fontsize=SIZE, fontname="helv")
        doc.save(path)
    found = texts(path)
    assert sorted(found) == sorted(
        [f"Term row {k}" for k in range(6)]
        + [f"{k * 13 + 7}.5" for k in range(6)]
        + ["mg per day"] * 6
    )


def test_a_heading_across_the_columns_ends_the_channel(tmp_path):
    """Text covering the channel's middle (a heading set across both columns in two pieces)
    is not split by the gutter below it."""
    path = tmp_path / "heading.pdf"
    expected = column_page(path, 2, rows=10, gutter=6.0)
    with pymupdf.open(path) as doc:
        page = doc[0]
        left = "A heading set across"
        page.insert_text((200, 40), left, fontsize=SIZE, fontname="helv")
        start = 200 + pymupdf.get_text_length(left + " ", "helv", SIZE)
        page.insert_text((start, 40), "both of the columns", fontsize=SIZE, fontname="helv")
        doc.save(tmp_path / "heading2.pdf")
    found = texts(tmp_path / "heading2.pdf")
    assert "A heading set across both of the columns" in found
    assert sorted(t for t in found if t.startswith("A heading") is False) == sorted(expected)


def test_a_gap_holding_drawn_ink_is_not_a_gutter(tmp_path):
    """Answer rows whose variable is drawn as vector art at the same x on every row: the gap
    lines up like a channel but is not white, so each row stays one line."""
    path = tmp_path / "ink.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        for k, letter in enumerate("ABCDEF"):
            y = 60 + 14 * k
            page.insert_text((40, y), f"{letter}. The distribution for", fontsize=SIZE)
            page.draw_line((128, y - 7), (133, y - 7))  # a bar over the drawn variable
            page.draw_rect(pymupdf.Rect(128, y - 6, 133, y), color=(0, 0, 0))
            page.insert_text((136, y), "is normal with the same mean", fontsize=SIZE)
        doc.save(path)
    found = texts(path)
    assert len(found) == 6
    assert all("distribution for" in t and "same mean" in t for t in found)


def test_a_small_run_under_a_display_number_is_its_own_line(tmp_path):
    """A running head (9 pt) printed over the chapter number (38 pt) is not a superscript of
    it: the number stays a line of its own; a real script stays with its base."""
    path = str(tmp_path / "opener.pdf")
    with pymupdf.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((111, 114), "2", fontsize=38, fontname="helv")
        page.insert_text((84, 100), "Section 1: Inpatient Management of Major Cases",
                         fontsize=9, fontname="helv")  # fmt: skip
        page.insert_text((111, 300), "x", fontsize=12, fontname="helv")
        page.insert_text((118, 296), "2", fontsize=8, fontname="helv")  # a superscript
        doc.save(path)
    found = texts(path)
    assert "2" in found
    assert not any("Section 1" in line and "2" == line[-1] for line in found)
    assert "x2" in found


def test_a_long_numbered_item_inside_a_frame_is_not_figure_text(monkeypatch):
    """A bold question stem set inside a picture's frame stays item text; a short numbered
    key of a figure stays a label."""
    from types import SimpleNamespace

    import book_core.layout.evidence as evidence

    bold = ("x", 9.0, 0, True, False)
    monkeypatch.setattr(evidence, "line_text", lambda ln, store: ln.text)
    monkeypatch.setattr(evidence, "style_of", lambda lines, store: bold)
    monkeypatch.setattr(evidence, "wrapped_sequence", lambda *args: False)

    def line(text):
        return SimpleNamespace(blank=False, text=text)

    stem = "33. A 30-year-old male investigated infertility, semen analysis shows azoospermia"
    assert evidence.paragraph_like(line(stem), None, ("y", 10.0, 0, False, False), ())
    assert evidence.paragraph_like(line("a) Provides more energy available to cancer cells ok"),
                                   None, ("y", 10.0, 0, False, False), ())  # fmt: skip
    assert not evidence.paragraph_like(line("1. Cerebral hemisphere"), None, None, ())
    for credit in ("(t)WDC Photos/Alamy Stock Photo; (b)larry1235/Shutterstock images today",
                   "S.C. Mexico Texas Louisiana Florida Georgia Alabama Mississippi",
                   "(1)Goebbels, Josef. In Kennedy, David M. Freedom From Fear. Oxford"):
        assert not evidence.paragraph_like(line(credit), None, ("y", 10.0, 0, False, False), ())
    unnumbered = "Cerebral hemisphere of the brain seen from above and behind"
    assert not evidence.paragraph_like(line(unnumbered), None, ("y", 10.0, 0, False, False), ())


def test_a_frame_with_a_short_stem_and_lettered_options_is_a_question_frame(monkeypatch):
    from types import SimpleNamespace

    import book_core.layout.evidence as evidence

    monkeypatch.setattr(evidence, "line_text", lambda ln, store: ln.text)

    def lines(*texts):
        return [SimpleNamespace(blank=False, text=t) for t in texts]

    question = lines("77.  The injury is suggestive of:", "a.\t", "Postmortem wound", "b.\t Cut")
    assert evidence.question_frame(question, None)
    assert not evidence.question_frame(lines("1. Nucleus", "2. Membrane"), None)  # a key
    assert not evidence.question_frame(lines("77. Stem", "a. only one option"), None)
    assert not evidence.question_frame(lines("Stem", "a. one", "b. two"), None)  # no number


def test_texts_with_a_numbered_stem_and_lettered_options_are_a_question():
    from book_core.layout.evidence import question_texts

    assert question_texts(["26.  What will increase life span?", "a.", "Exercise", "b.", "Drugs"])
    assert not question_texts(["Year", "1990", "2000"])  # a table
    assert not question_texts(["1. Nucleus", "2. Membrane"])  # a key


def test_options_a_picture_overlaps_stay_with_their_question(monkeypatch):
    from types import SimpleNamespace

    import book_core.layout.evidence as evidence
    import book_core.layout.pipeline as pipeline
    from book_core.model.common import BBox

    monkeypatch.setattr(pipeline, "line_text", lambda ln, store: ln.text)
    monkeypatch.setattr(evidence, "line_text", lambda ln, store: ln.text)

    def box(x0, y0, x1, y1):
        return BBox(x0=x0, y0=y0, x1=x1, y1=y1)

    def line(name, text, x0, y0, x1):
        return SimpleNamespace(id=name, text=text, blank=False, inside_content=True,
                               visible=True, font_size=8.5,
                               bbox=box(x0, y0, x1, y0 + 11))  # fmt: skip

    lines = [
        line("stem", "58.  A farmer is presented with sinuses", 90, 110, 580),
        line("a", "a.", 111, 243, 120), line("at", "Can be caused by bacteria", 127, 243, 268),
        line("b", "b.", 336, 243, 351), line("bt", "Involves skin only", 351, 243, 537),
        line("c", "c.", 111, 254, 119), line("ct", "Lymphocytes present", 127, 254, 268),
        line("d", "d.", 336, 254, 351), line("dt", "Spread by blood", 351, 254, 469),
    ]
    picture = SimpleNamespace(bbox=box(214, 137, 459, 238))  # ends above the options
    assert pipeline._option_rows(lines, [picture], None) == {"b", "bt", "d", "dt"}
    no_stem = [ln for ln in lines if ln.id != "stem"]  # panel letters of a figure, not options
    assert pipeline._option_rows(no_stem, [picture], None) == set()
