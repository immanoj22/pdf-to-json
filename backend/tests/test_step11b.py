"""Step 11b rules (synthetic): navigation kinds (glossary terms, space-separated locators,
sub-entries, merged entries, contents guard), set-off list markers, float titles in heading
order, and the list-item evaluation of a paragraph-item dialect."""

import unicodedata
from types import SimpleNamespace

from test_furniture import PageBuilder
from test_lists import items, lists_of
from test_paragraphs import column
from test_structure import BODY, Book, decide

from book_core.evaluation.lists import Ours, list_item_scores, list_items
from book_core.lists.lines import set_off_marker
from book_core.model.spans import TextSpan
from book_core.structure.navigation import page_statistics

TERMS = ["Abdomen", "Abductor", "Acromion", "Afferent", "Ala", "Alba", "Allantois", "Alveus",
         "Amnion", "Ampulla", "Anastomosis", "Annulus"]  # fmt: skip


def lead(letters, rest):
    return {"bold": True, "italic": False, "letters": letters, "rest_letters": rest,
            "size_ratio": 1.0, "color_differs": False, "span_ids": ["s"], "end": letters,
            "tokens": 1, "last": "x", "rest_bold": False, "rest_italic": False}  # fmt: skip


def glossary_page(book, page, terms):
    for term in TERMS:
        text = f"{term} a part of the body that holds or covers other parts"
        book.unit(page, text, lead_run=lead(len(term), 40) if terms else None)


def test_glossary_needs_set_off_terms_alphabetical_rows_of_plain_cells_are_not_one():
    book = Book(3)
    book.body(1)
    glossary_page(book, 2, terms=True)
    glossary_page(book, 3, terms=True)
    kinds = {n.page: n.kind for n in decide(book)["navigation_pages"]}
    assert kinds == {2: "glossary", 3: "glossary"}
    table = Book(3)
    table.body(1)
    glossary_page(table, 2, terms=False)
    glossary_page(table, 3, terms=False)
    assert decide(table)["navigation_pages"] == []


def index_page(book, page, start=0, merged=False):
    """Entries "Term 12" (space before the first locator) with indented sub-entries."""
    rows = []
    for i, term in enumerate(TERMS):
        rows.append((f"{term} {page * 10 + i}", 0.0))
        rows.append((f"cells of {page * 10 + i + 1}, {page * 10 + i + 2}f", 12.0))
    if merged:  # Step 9 held a column's entries in a few units
        rows = [(" ".join(text for text, _ in rows[k : k + 8]), 0.0) for k in range(0, 24, 8)]
    for text, indent in rows:
        unit = book.unit(page, text)
        unit["start"] = 60.0 + indent
        unit["lines"] = 8 if merged else 1


def test_index_with_space_separated_locators_and_indented_sub_entries():
    book = Book(4)
    book.unit(1, "Index", size=20, bold=True)
    index_page(book, 1)
    index_page(book, 2)
    index_page(book, 3, merged=True)
    book.body(4)
    evidence = book.evidence()
    stats = page_statistics(evidence["pages"][1], 4)
    # Sub-entries ("cells of") do not break the order of the base-indent entries.
    assert stats["alphabetical"] == 1.0 and stats["locators"] == 1.0
    kinds = {n.page: n.kind for n in decide(book)["navigation_pages"]}
    # Page 3: three merged units hold 24 lines; the run extends to it.
    assert kinds == {1: "index", 2: "index", 3: "index"}


def test_contents_entries_ending_with_page_numbers_are_not_an_index():
    book = Book(12)
    titles = ["Anatomy", "Bones", "Cells", "Digestion", "Eyes", "Fascia", "Glands", "Hearts",
              "Joints"]  # fmt: skip
    for page in range(1, 13):
        book.pages[page - 1]["label"] = str(page)
    entries = []
    for i, title in enumerate(titles):
        entry = {"id": f"e{i}", "title": title, "target_label": str(3 + i),
                 "level_evidence": {}, "leaders": False}  # fmt: skip
        entries.append(entry)
        book.unit(1, f"{title} {3 + i}", entries=[entry["id"]])
    book.pages[0]["navigation"] = entries
    book.toc_pages = [{"page": 1}]
    for page in range(2, 13):
        book.body(page)
    kinds = {n.page: n.kind for n in decide(book)["navigation_pages"]}
    assert kinds.get(1) == "table_of_contents"


def styled_line(builder, lid, x0, y, parts, size=10.0):
    """A line of spans with their own font and colour: parts = [(text, font, colour)]."""
    text = "".join(t for t, _, _ in parts)
    line = builder.line(lid, x0, y, x0 + 0.52 * size * len(text), text, size=size)
    first = builder.spans.pop(line.span_ids[0])
    ids, x = [], x0
    for index, (piece, font, colour) in enumerate(parts):
        width = 0.52 * size * len(piece)
        sid = f"{first.id}-{index}"
        builder.spans[sid] = TextSpan(
            id=sid, line_id=first.line_id, page=first.page, raw_text=piece,
            text=unicodedata.normalize("NFKC", piece),
            bbox=first.bbox.model_copy(update={"x0": x, "x1": x + width}),
            font=font, size=size, color=colour, flags=0, provenance=first.provenance,
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


def spans_of(parts):
    store = SimpleNamespace(spans={})
    rows, offset = [], 0
    for index, (text, font, colour) in enumerate(parts):
        store.spans[f"s{index}"] = SimpleNamespace(font=font, color=colour)
        rows.append((f"s{index}", offset, offset + len(text), False, False, 10.0))
        offset += len(text)
    return "".join(t for t, _, _ in parts), rows, store


def test_set_off_markers_are_glyphs_in_their_own_span():
    raw, rows, store = spans_of([("	◆", "Sans", 0), ("Thyroid gland", "Serif", 0)])
    marker = set_off_marker(raw, rows, store)  # no space after the glyph
    assert marker.type == "bullet" and marker.signature == (False, "◆", "Sans", "Serif")
    # A symbol-font glyph extracted as a letter; colour is not required.
    raw, rows, store = spans_of([("	", "Sans", 0), ("Ǌ", "Dingbats", 0), (" Blood", "Sans", 0)])
    assert raw[set_off_marker(raw, rows, store).start] == "Ǌ"
    raw, rows, store = spans_of([("A", "Serif", 0), ("ll of it", "Serif", 0)])
    assert set_off_marker(raw, rows, store) is None  # same font and colour: text
    raw, rows, store = spans_of([("3", "Bold", 0), (" Results", "Serif", 0)])
    assert set_off_marker(raw, rows, store) is None  # digits are numbers, not bullets
    raw, rows, store = spans_of([("–Pyloric part", "Serif", 0)])
    assert set_off_marker(raw, rows, store) is None  # the dash shares the word's span
    for glyph, rest in (
        ("p", " < .001, were found"),
        ("F", "(1, 147) = 16.87"),
        ("α", " = .77, a sample"),
        ("(", "SD = 2.88)"),
        ("“", "Nuestros"),
    ):
        raw, rows, store = spans_of([(glyph, "Serif-Italic", 0), (rest, "Serif", 0)])
        assert set_off_marker(raw, rows, store) is None, glyph  # expressions and quotes


def split_glyph(builder, line, font, colour):
    """Set the first character of ``line`` in a span of its own (font, colour)."""
    span = builder.spans.pop(line.span_ids[0])
    width = span.bbox.x1 - span.bbox.x0
    step = width / max(1, len(span.raw_text))
    ids = []
    for index, (piece, f, c, x0, x1) in enumerate([
        (span.raw_text[0], font, colour, span.bbox.x0, span.bbox.x0 + step),
        (span.raw_text[1:], span.font, span.color, span.bbox.x0 + step, span.bbox.x1),
    ]):  # fmt: skip
        sid = f"{span.id}-{index}"
        builder.spans[sid] = span.model_copy(update={
            "id": sid, "raw_text": piece, "text": unicodedata.normalize("NFKC", piece),
            "font": f, "color": c, "bbox": span.bbox.model_copy(update={"x0": x0, "x1": x1}),
        })  # fmt: skip
        ids.append(sid)
    builder.lines[builder.lines.index(line)] = line.model_copy(update={"span_ids": ids})
    source = next(s for s in builder.source_lines if s.id == span.line_id)
    builder.source_lines[builder.source_lines.index(source)] = source.model_copy(
        update={"span_ids": ids}
    )


def test_set_off_bullets_make_a_list_and_a_lone_unusual_glyph_does_not():
    def page_with(glyphs):
        page = PageBuilder(1)
        texts = ["Thyroid gland", "Parathyroid glands", "Adrenal glands", "Pituitary gland"]
        pairs = zip(glyphs, texts, strict=True)
        rows = [(100 + 14 * i, 0, g + " " + t) for i, (g, t) in enumerate(pairs)]
        column(page, "c", 60, 550, rows, page.band("b", 100, 160, [(60, 550, "column")]))
        for line, glyph in zip(list(page.lines), glyphs, strict=True):
            if glyph in {"Ǌ", "p", "α"}:
                split_glyph(page, line, "Dingbats" if glyph == "Ǌ" else "Serif-Italic", 0)
        return lists_of(page)

    p, layout, result, lists = page_with(["Ǌ"] * 4)
    found = items(p, layout, result)
    assert len(found) == 4 and all(u.marker.type == "bullet" for _, u in found)
    assert lists[0].kind == "bulleted"
    p, layout, result, lists = page_with(["Ǌ", "A", "B", "C"])
    assert items(p, layout, result) == []  # one unusual glyph alone opens no list


def test_statistics_lines_stay_paragraphs():
    page = PageBuilder(1)
    rows = [(100, 0, "p < .001, were found for the group and the measure"),
            (114, 0, "p < .05 and .01, respectively, for both scales used"),
            (128, 0, "α = .77 and 15 questions for ethnic acculturation"),
            (142, 0, "α = .91 for the language use scale in this sample")]  # fmt: skip
    column(page, "c", 60, 550, rows, page.band("b", 100, 160, [(60, 550, "column")]))
    for line in list(page.lines):
        split_glyph(page, line, "Serif-Italic", 0)
    p, layout, result, lists = lists_of(page)
    assert items(p, layout, result) == [] and lists == []


def test_float_title_takes_its_place_before_the_running_text():
    book = Book(4)
    for page, title in ((1, "Introduction to Anatomy"), (3, "Levels of Organization")):
        for section in ("DEFINITION OF ANATOMY", "STRUCTURE OF THE BODY"):
            unit = book.unit(page, section, size=12, bold=True)
            unit["block"] = unit["block_end"] = 0.4
            body = book.unit(page, BODY + ".")
            body["block"] = body["block_end"] = 0.5
        banner = book.unit(page, title, size=24, bold=True, stream="figure", kind="figure_text")
        banner["block"] = banner["block_end"] = 0.1
        book.body(page + 1)
    units = {u["unit"]: u for p in book.pages for u in p["units"]}
    levels = [(h.page, units[h.unit_ids[0]]["text"], h.level) for h in decide(book)["headings"]]
    for page, title in ((1, "Introduction to Anatomy"), (3, "Levels of Organization")):
        assert (page, title, 1) in levels  # the banner title opens the chapter
        assert (page, "DEFINITION OF ANATOMY", 2) in levels  # its sections nest below it


def test_list_items_of_a_dialect_that_writes_items_as_paragraphs():
    units = [
        {"unit": 1, "kind": "paragraph", "list": {"list": "/l1", "item": "/l1/i1", "depth": 1},
         "table": None, "start": [1, 0], "pdf": [[1, 0, 2]], "zone": "body"},
        {"unit": 2, "kind": "paragraph", "list": {"list": "/l1", "item": "/l1/i2", "depth": 1},
         "table": None, "start": [1, 2], "pdf": [[1, 2, 2]], "zone": "body"},
        {"unit": 3, "kind": "paragraph", "list": None, "table": None, "start": [1, 4],
         "pdf": [[1, 4, 2]], "zone": "body"},
    ]  # fmt: skip
    gold = SimpleNamespace(units=units)
    assert [u["unit"] for u in list_items(gold)] == [1, 2]
    ours = Ours(unit_of={(1, 0): "a", (1, 1): "a", (1, 2): "b", (1, 3): "b"})
    assert list_item_scores(gold, ours)["exact_match"] == 1.0
    # A dialect with list-item units keeps them as the items.
    units.append({**units[0], "unit": 4, "kind": "list_item", "pdf": [[1, 6, 1]]})
    assert [u["unit"] for u in list_items(gold)] == [4]


def plain_page(rows, glyph_font=None):
    """One column of lines; ``glyph_font`` sets each line's first character in its own span."""
    page = PageBuilder(1)
    column(page, "c", 60, 550, [(100 + 14 * i, 0, text) for i, text in enumerate(rows)],
           page.band("b", 100, 100 + 14 * len(rows) + 10, [(60, 550, "column")]))  # fmt: skip
    if glyph_font:
        for line in list(page.lines):
            split_glyph(page, line, glyph_font, 0)
    return lists_of(page)


def test_aligned_equation_lines_stay_text():
    for font in (None, "Math"):
        p, layout, result, lists = plain_page(
            ["= 3x + 2y for the first case", "+ 4y when the second applies",
             "= 7x after both are added", "+ 2 for the constant term"], font,
        )  # fmt: skip
        assert items(p, layout, result) == [] and lists == [], font


def test_spanish_dialogue_lines_stay_paragraphs():
    for font in (None, "Serif"):
        p, layout, result, lists = plain_page(
            ["— ¿Dónde estabas anoche? —preguntó Ana.", "— En casa de mi abuela —dijo él.",
             "— ¡No te creo! —respondió ella.", "—«Es verdad» —insistió."], font,
        )  # fmt: skip
        assert items(p, layout, result) == [] and lists == [], font


def test_glued_bullet_and_dash_items_become_lists():
    p, layout, result, lists = plain_page(
        ["◆Thyroid gland", "◆Parathyroid glands", "◆Adrenal glands"], "Serif"
    )
    assert [u.marker.type for _, u in items(p, layout, result)] == ["bullet"] * 3
    p, layout, result, lists = plain_page(
        ["–Myo = muscle (prefix)", "–Sub = below (prefix)", "–Itis = inflammation"], "Serif"
    )
    found = items(p, layout, result)
    assert [u.marker.type for _, u in found] == ["dash"] * 3 and lists[0].kind == "bulleted"


def test_float_title_set_like_the_main_title_keeps_the_stream_order():
    book = Book(2)
    piece = book.unit(1, "y la expansión estadounidense", size=24, bold=True)
    piece["block"] = piece["block_end"] = 0.4
    book.unit(1, "LESSONS OF THE UNIT", size=12, bold=True)["block"] = 0.5
    book.unit(1, BODY + ".")["block"] = 0.6
    banner = book.unit(1, "La Primera Guerra Mundial", size=24, bold=True, stream="figure",
                       kind="figure_text")  # fmt: skip
    banner["block"] = banner["block_end"] = 0.3
    book.body(2)
    units = {u["unit"]: u for p in book.pages for u in p["units"]}
    order = [units[h.unit_ids[0]]["text"] for h in decide(book)["headings"]]
    # Not more prominent than the main-flow title piece: the banner keeps its stream place.
    assert order.index("y la expansión estadounidense") < order.index("La Primera Guerra Mundial")


def test_index_column_of_long_wrapped_entries_keeps_its_base_indent():
    # Nearly every line is an indented continuation: the base is the start two lines share.
    page = PageBuilder(1)
    rows = [(100, 0, "civil rights movement: affirmative action,")]
    rows += [(114 + 14 * i, 14, f"{400 + i}; campaign number {i} of the long entry,")
             for i in range(24)]  # fmt: skip
    rows += [(450, 0, "civil service reform, 77, 79,"), (464, 14, "81")]
    column(page, "c", 60, 330, rows, page.band("b", 100, 480, [(60, 330, "column")]))
    p, layout, result, lists = lists_of(page, "index")
    found = items(p, layout, result, ("index_entry",))
    assert [len(u.line_ids) for _, u in found] == [25, 2]
