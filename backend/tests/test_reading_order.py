"""Step 7: reading order (main flow, floats, side streams) on synthetic and real pages.

Synthetic PDF pages are generated with PyMuPDF and run through the unchanged Step 4 layout.
Right-to-left, vertical and card-grid pages are built directly as layouts (model level), so
the ordering rules are tested independently of layout detection. Real fixtures cover the
Step 7 regression targets and the every-line-exactly-once invariant on all 24 measured pages.
"""

import json
import unicodedata

import pymupdf
import pytest
import regex
from conftest import ROOT
from test_layout_invariants import write_rotated_table

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.models import Band, Lane, PageLayout, Region, Scope, VisualLine
from book_core.model.common import BBox, Provenance
from book_core.model.spans import SourceLine, SpanStore, TextSpan
from book_core.reading_order.builder import build_reading_order
from book_core.reading_order.cache import analyze_reading_order
from book_core.reading_order.continuation import continuation
from book_core.reading_order.graph import check, to_graph
from book_core.reading_order.models import FLOAT_KINDS, PageReadingOrder

CACHE = ROOT / ".cache/objects"
FIXTURES = ROOT / "experiments/fixtures"
UNSEEN = ROOT / "experiments/fixtures_unseen"
MARK = regex.compile(r"m(\d)n(\d{3})")


# ------------------------------------------------------------------ helpers


def order_of(source, cache=None):
    order, layout, analysis = analyze_reading_order(source, 1, PyMuPDFExtractor(), cache_dir=cache)
    assert check(order, layout) == []
    store = analysis.native.page.store
    lines = {line.id: line for line in layout.lines}

    def text(lid):
        return "".join(store.spans[s].raw_text for s in lines[lid].span_ids)

    return order, layout, text


def real(path):
    if not path.exists():
        pytest.skip(f"{path.name} is not tracked; run experiments/recreate_unseen_fixtures.py")
    return order_of(path, CACHE)


def marks(texts):
    return [(int(c), int(k)) for t in texts for c, k in MARK.findall(t)]


def fill(page, rects, column, start=0, size=10):
    """Fill rects in order with ordered marker words of one column; returns the next index."""
    k = start
    for rect in rects:
        words = [f"m{column}n{i:03d}" for i in range(k, k + 400)]
        count = len(words)
        while page.insert_textbox(rect, " ".join(words[:count]), fontsize=size) < 0:
            count = int(count * 0.9)
        k += count
    return k


def columns_page(path, columns, top=100, bottom=700, label_offset=0):
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        width = (512 - 16 * (columns - 1)) / columns
        for i in range(columns):
            x0 = 50 + i * (width + 16)
            fill(page, [pymupdf.Rect(x0, top, x0 + width, bottom)], i + 1 + label_offset)
        pdf.save(path)


def main_texts(order, text):
    return [text(lid) for lid in order.main.line_ids]


# ------------------------------------------------------------ synthetic: PDF


@pytest.mark.parametrize("columns", [1, 2, 3, 4])
def test_columns_read_lane_by_lane(tmp_path, columns):
    source = tmp_path / f"c{columns}.pdf"
    columns_page(source, columns)
    order, layout, text = order_of(source)
    found = marks(main_texts(order, text))
    assert found == sorted(found)
    assert {c for c, _ in found} == set(range(1, columns + 1))
    kinds = {e.kind for e in order.edges}
    assert ("next_lane_in_band" in kinds or "continues_across_column" in kinds) == (columns > 1)


def test_spanning_title_breaks_the_column_flow(tmp_path):
    source = tmp_path / "title.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        fill(page, [pymupdf.Rect(50, 100, 298, 330)], 1)
        fill(page, [pymupdf.Rect(314, 100, 562, 330)], 2)
        page.insert_text((50, 372), "Encabezado que cruza la página entera", fontsize=22)
        fill(page, [pymupdf.Rect(50, 400, 298, 700)], 3)
        fill(page, [pymupdf.Rect(314, 400, 562, 700)], 4)
        pdf.save(source)
    order, _, text = order_of(source)
    texts = main_texts(order, text)
    title = next(i for i, t in enumerate(texts) if t.startswith("Encabezado"))
    found = marks(texts)
    assert found == sorted(found)
    assert all(c <= 2 for c, _ in marks(texts[:title])) and marks(texts[:title])
    assert all(c >= 3 for c, _ in marks(texts[title:])) and marks(texts[title:])


@pytest.mark.parametrize("shape", ["circle", "framed_box"])
def test_pull_quote_is_a_float_and_never_splits_a_column(tmp_path, shape):
    """A circle gives one band with an inset; a framed box makes Step 4 split the columns
    into bands around it. Either way each column is read whole and the quote is a float."""
    source = tmp_path / "quote.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        if shape == "circle":
            page.draw_circle((306, 390), 70, color=None, fill=(0.85, 0.93, 0.97))
        else:
            box = pymupdf.Rect(220, 330, 392, 450)
            page.draw_rect(box, color=(0.2, 0.4, 0.6), fill=(0.85, 0.93, 0.97), width=1.5)
        page.insert_textbox(
            pymupdf.Rect(240, 345, 372, 440),
            "Una cita destacada en el centro",
            fontsize=16,
            align=1,
        )
        k = fill(page, [pymupdf.Rect(50, 100, 298, 320)], 1)
        k = fill(page, [pymupdf.Rect(50, 320, 210, 460)], 1, k)
        fill(page, [pymupdf.Rect(50, 460, 298, 700)], 1, k)
        k = fill(page, [pymupdf.Rect(314, 100, 562, 320)], 2)
        k = fill(page, [pymupdf.Rect(402, 320, 562, 460)], 2, k)
        fill(page, [pymupdf.Rect(314, 460, 562, 700)], 2, k)
        pdf.save(source)
    order, _, text = order_of(source)
    texts = main_texts(order, text)
    assert not any("cita" in t for t in texts)
    found = marks(texts)
    assert found == sorted(found)
    quote = [s for s in order.streams if any("cita" in text(lid) for lid in s.line_ids)]
    assert len(quote) == 1 and quote[0].kind in FLOAT_KINDS
    anchor = quote[0].anchor
    assert anchor.after_line_id is not None
    assert marks([text(anchor.after_line_id)])[0][0] == 1  # interrupts the first column


def test_sidebar_box_is_a_float_anchored_in_the_flow(tmp_path):
    source = tmp_path / "sidebar.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        fill(page, [pymupdf.Rect(50, 100, 370, 700)], 1)
        box = pymupdf.Rect(400, 100, 562, 400)
        page.draw_rect(box, color=None, fill=(0.98, 0.9, 0.75))
        page.insert_textbox(
            box + (8, 8, -8, -8), "Nota lateral. " + "Texto del recuadro lateral. " * 8, fontsize=9
        )
        pdf.save(source)
    order, _, text = order_of(source)
    texts = main_texts(order, text)
    assert not any("recuadro" in t or "Nota lateral" in t for t in texts)
    found = marks(texts)
    assert found == sorted(found) and found
    side = [s for s in order.streams if any("recuadro" in text(lid) for lid in s.line_ids)]
    assert len(side) == 1 and side[0].kind in {"sidebar", "callout"}
    assert side[0].anchor is not None


def test_rotated_block_is_read_in_its_own_frame(tmp_path):
    source = tmp_path / "rotated.pdf"
    write_rotated_table(source, with_credit=False)
    order, layout, text = order_of(source)
    assert any(s.kind == "rotated" for s in layout.scopes)
    main = main_texts(order, text)
    title = next(i for i, t in enumerate(main) if t.startswith("Table 4.1"))
    table = next(s for s in order.streams if s.kind == "table")
    assert table.anchor.position >= title
    cells = [text(lid).strip() for lid in table.line_ids]
    assert cells.index("Sociability") < cells.index("Aggression") < cells.index("Shyness")
    note = next(s for s in order.streams for lid in s.line_ids if text(lid).startswith("Note."))
    position = note.anchor.position if note.anchor else len(main)
    assert position >= table.anchor.position


# ---------------------------------------------------------- synthetic: model


class Builder:
    """A hand-built PageLayout plus span store (one span per line)."""

    def __init__(self):
        self.lines, self.spans, self.source_lines, self.regions = [], {}, [], []
        self.bands, self.scopes = (
            [],
            [Scope(id="page", kind="page", bbox=BBox(x0=0, y0=0, x1=612, y1=792))],
        )

    def line(self, lid, x0, y0, x1, text, direction="ltr", vertical=False, size=10.0):
        y1 = y0 + (x1 - x0 if vertical else size * 1.2)
        if vertical:
            box = BBox(x0=x0, y0=y0, x1=x0 + size * 1.2, y1=x1)
            start, end, rotation, mode = (x0 + 6, y0), (x0 + 6, x1), 0.0, "vertical"
        else:
            box = BBox(x0=x0, y0=y0, x1=x1, y1=y1)
            start, end, rotation, mode = (x0, y1 - 2), (x1, y1 - 2), 0.0, "horizontal"
        sid = f"s-{lid}"
        self.spans[sid] = TextSpan(
            id=sid,
            line_id=f"n-{lid}",
            page=1,
            raw_text=text,
            text=unicodedata.normalize("NFKC", text),
            bbox=box,
            font="t",
            size=size,
            color=0,
            flags=0,
            text_direction=direction,
            provenance=Provenance(source_sha256="c" * 64),
        )
        self.source_lines.append(SourceLine(id=f"n-{lid}", page=1, bbox=box, span_ids=[sid]))
        line = VisualLine(
            id=lid,
            span_ids=[sid],
            source_line_ids=[f"n-{lid}"],
            bbox=box,
            baseline_start=start,
            baseline_end=end,
            direction=(0.0, 1.0) if vertical else (1.0, 0.0),
            rotation=rotation,
            writing_mode=mode,
            text_direction=direction,
            font_size=size,
            visible=True,
            inside_content=True,
        )
        self.lines.append(line)
        return line

    def band(self, bid, y0, y1, lanes, scope="page"):
        lanes = [
            Lane(index=i, x0=a, x1=b, kind=k, line_count=1, confidence=0.8, reasons=["t"])
            for i, (a, b, k) in enumerate(lanes)
        ]
        from book_core.layout.models import Gutter

        gutters = [
            Gutter(
                x0=a.x1,
                x1=b.x0,
                y0=y0,
                y1=y1,
                left_items=1,
                right_items=1,
                ink_fraction=0,
                confidence=0.8,
                reasons=["t"],
            )
            for a, b in zip(lanes, lanes[1:], strict=False)
        ]
        x0, x1 = min(lane.x0 for lane in lanes), max(lane.x1 for lane in lanes)
        self.bands.append(
            Band(
                id=bid,
                scope_id=scope,
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                gutters=gutters,
                lanes=lanes,
                column_count=sum(lane.kind == "column" for lane in lanes),
                confidence=0.8,
                reasons=["t"],
            )
        )

    def region(self, rid, kind, lines, band, lane, scope="page"):
        box = BBox(
            x0=min(line.bbox.x0 for line in lines),
            y0=min(line.bbox.y0 for line in lines),
            x1=max(line.bbox.x1 for line in lines),
            y1=max(line.bbox.y1 for line in lines),
        )
        self.regions.append(
            Region(
                id=rid,
                type=kind,
                bbox=box,
                scope_id=scope,
                band_id=band,
                lane_index=lane,
                line_ids=[line.id for line in lines],
                confidence=0.8,
                reasons=["t"],
            )
        )

    def build(self):
        layout = PageLayout(
            source_sha256="c" * 64,
            page=1,
            layout_version="t",
            content_bbox=BBox(x0=0, y0=0, x1=612, y1=792),
            lines=self.lines,
            scopes=self.scopes,
            bands=self.bands,
            regions=self.regions,
            provenance=Provenance(source_sha256="c" * 64),
        )
        store = SpanStore(spans=self.spans, lines=self.source_lines)
        order = build_reading_order(layout, store)
        assert check(order, layout) == []
        return order


def column(builder, prefix, x0, x1, y0, count, texts, direction="ltr"):
    return [
        builder.line(f"{prefix}{i}", x0, y0 + 14 * i, x1, texts[i % len(texts)], direction)
        for i in range(count)
    ]


def test_right_to_left_two_columns_read_right_lane_first():
    page = Builder()
    hebrew = ["שלום עולם וטקסט ארוך", "המשך השורה בעברית", "סוף הפסקה בעברית."]
    left = column(page, "L", 60, 290, 100, 4, hebrew, "rtl")
    right = column(page, "R", 320, 550, 100, 4, hebrew, "rtl")
    page.band("b", 100, 160, [(60, 290, "column"), (320, 550, "column")])
    page.region("rl", "main_text", left, "b", 0)
    page.region("rr", "main_text", right, "b", 1)
    order = page.build()
    assert order.main.line_ids == [line.id for line in right + left]


def test_right_to_left_row_reads_right_to_left():
    page = Builder()
    first = page.line("a", 300, 100, 550, "عربي أول", "rtl")
    second = page.line("b", 60, 100, 280, "عربي ثان", "rtl")
    page.band("b", 100, 112, [(60, 550, "column")])
    page.region("r", "main_text", [second, first], "b", 0)
    assert page.build().main.line_ids == ["a", "b"]


def test_vertical_lines_read_right_to_left():
    page = Builder()
    lines = [
        page.line(f"v{i}", 500 - 20 * i, 100, 400, "縦書きの行です", "ttb", True) for i in range(4)
    ]
    page.band("b", 100, 400, [(400, 520, "column")])
    page.region("r", "main_text", list(reversed(lines)), "b", 0)
    assert page.build().main.line_ids == ["v0", "v1", "v2", "v3"]


def test_card_grid_reads_card_by_card_after_the_columns():
    page = Builder()
    words = ["Texto de la columna", "sigue la columna"]
    left = column(page, "L", 60, 290, 100, 3, words)
    right = column(page, "R", 320, 550, 100, 3, words)
    page.band("cols", 100, 142, [(60, 290, "column"), (320, 550, "column")])
    page.region("rl", "main_text", left, "cols", 0)
    page.region("rr", "main_text", right, "cols", 1)
    lanes, cards = [], []
    for c in range(3):
        x0 = 60 + 170 * c
        lanes.append((x0, x0 + 150, "card"))
        cards.append(column(page, f"K{c}-", x0, x0 + 150, 200, 3, ["1909: Fundada", "1954: Caso"]))
    page.band("cards", 200, 242, lanes)
    for c, lines in enumerate(cards):
        page.region(f"card{c}", "sidebar", lines, "cards", c)
    order = page.build()
    assert order.main.line_ids == [line.id for line in left + right]
    streams = [s for s in order.streams if s.kind == "card"]
    assert [s.line_ids for s in streams] == [[line.id for line in lines] for lines in cards]
    assert [s.anchor.order for s in streams] == [0, 1, 2]
    assert all(s.anchor.after_line_id == right[-1].id for s in streams)


def test_columns_continue_across_a_float_band_only_on_evidence():
    page = Builder()
    upper_left = column(page, "A", 60, 290, 100, 3, ["el texto continúa y"])
    upper_right = column(page, "B", 320, 550, 100, 3, ["Nueva sección aquí."])
    lower_left = column(page, "C", 60, 290, 400, 3, ["sigue en minúscula"])
    lower_right = column(page, "D", 320, 550, 400, 3, ["final del texto."])
    figure = page.line("F", 100, 250, 400, "Etiqueta")
    page.band("up", 100, 142, [(60, 290, "column"), (320, 550, "column")])
    page.band("fig", 240, 380, [(60, 550, "figure")])
    page.band("low", 400, 442, [(60, 290, "column"), (320, 550, "column")])
    page.region("a", "main_text", upper_left, "up", 0)
    page.region("b", "main_text", upper_right, "up", 1)
    page.region("f", "figure", [figure], "fig", 0)
    page.region("c", "main_text", lower_left, "low", 0)
    page.region("d", "main_text", lower_right, "low", 1)
    order = page.build()
    ids = [line.id for line in upper_left + lower_left + upper_right + lower_right]
    assert order.main.line_ids == ids
    decision = next(d for d in order.decisions if d.kind == "column_flow")
    assert decision.choice == "columns_continue_across_float_band"


def test_every_float_is_anchored_and_graph_is_typed():
    page = Builder()
    text = column(page, "T", 60, 550, 100, 4, ["línea de texto"])
    page.band("b", 100, 156, [(60, 550, "column")])
    page.region("t", "main_text", text, "b", 0)
    note = page.line("n", 60, 700, 300, "nota al pie")
    page.band("nb", 700, 712, [(60, 300, "column")])
    page.region("n", "footnote_candidate", [note], "nb", 0)
    order = page.build()
    graph = to_graph(order)
    kinds = {data["kind"] for *_, data in graph.edges(data=True)}
    assert {"next_in_lane", "anchored_after"} <= kinds
    assert PageReadingOrder.model_validate_json(order.model_dump_json()) == order


def test_duplicate_line_in_two_streams_is_rejected():
    page = Builder()
    text = column(page, "T", 60, 550, 100, 2, ["línea"])
    page.band("b", 100, 128, [(60, 550, "column")])
    page.region("t", "main_text", text, "b", 0)
    data = json.loads(page.build().model_dump_json())
    data["streams"].append({**data["streams"][0], "id": "x", "kind": "furniture"})
    with pytest.raises(ValueError, match="more than once"):
        PageReadingOrder.model_validate(data)


def test_continuation_tokens_follow_the_ledger_rule():
    from book_core.ledger.tokenization import TOKEN_PATTERN as LEDGER
    from book_core.reading_order.continuation import TOKEN_PATTERN

    assert TOKEN_PATTERN.pattern == LEDGER.pattern


def test_continuation_evidence_is_script_agnostic():
    assert continuation("de la guerra de Indepen-", "dencia").verdict == "continues"
    assert continuation("los derechos de la", "Constitución de 1787").score > 0
    assert continuation("fin de la frase.", "Nueva frase").verdict == "break"
    caseless = continuation("東京で", "会議")
    assert caseless.features["following_start"] == "caseless"
    assert continuation("Texto", "Título", following_type="heading_candidate").verdict == "break"
    vocabulary = {"independencia": 3}
    attested = continuation("guerra de Indepen-", "dencia", vocabulary=vocabulary)
    assert attested.features["hyphen_join_attested"] == 3


# -------------------------------------------------------- regression targets


def _index(texts, prefix):
    return next(i for i, t in enumerate(texts) if t.strip().startswith(prefix))


def test_column_26_left_before_right_and_pull_quote_float():
    order, layout, text = real(FIXTURES / "column_26.pdf")
    texts = main_texts(order, text)
    assert _index(texts, "secesión de naciones") < _index(texts, "Los ideales de la Gran Ley")
    assert _index(texts, "Según la tradición") < _index(texts, "secesión de naciones")
    quote = next(
        s
        for s in order.streams
        if any(text(lid).startswith("sabios antepasados") for lid in s.line_ids)
    )
    assert quote.kind in {"callout", "sidebar"} and quote.anchor.mode == "inset"
    left = {
        lid
        for r in layout.regions
        if r.lane_index == 0 and r.type == "main_text"
        for lid in r.line_ids
    }
    assert quote.anchor.after_line_id in left
    assert [text(lid).strip() for lid in quote.line_ids[:2]] == ["“Nuestros", "sabios antepasados"]


def test_column_100_left_before_right_and_continuation_after_left_prose():
    order, _, text = real(FIXTURES / "column_100.pdf")
    texts = main_texts(order, text)
    continued = _index(texts, "de la guerra de Independencia")
    assert texts[continued - 1].strip().endswith("después")
    assert (
        _index(texts, "La Unión siguió venciendo")
        < continued
        < _index(texts, "El final de la guerra")
    )
    edge = next(
        e
        for e in order.edges
        if e.target == order.main.line_ids[continued]
        and e.source == order.main.line_ids[continued - 1]
    )
    assert edge.kind == "continues_across_column"


def test_complex_cards_columns_then_cards_with_naacp_chronology():
    order, _, text = real(FIXTURES / "complex_cards.pdf")
    texts = main_texts(order, text)
    assert _index(texts, "Durante la Reconstrucción") < _index(texts, "Los nueve de Little Rock")
    cards = [s for s in order.streams if s.kind == "card"]
    heads = [text(s.line_ids[0]).strip() for s in cards]
    assert heads == ["CORE", "NAACP", "SCLC", "SNCC"]
    assert all(s.anchor.position == len(texts) - 1 for s in cards)
    naacp = [text(lid) for lid in cards[1].line_ids]
    years = [_index(naacp, y) for y in ("1909", "1954", "1955")]
    assert years == sorted(years)


def test_complex_map_band_then_two_column_body():
    order, _, text = real(FIXTURES / "complex_map.pdf")
    texts = main_texts(order, text)
    figure = next(s for s in order.streams if s.kind == "figure")
    assert figure.anchor.position < _index(texts, "La solución final")
    assert _index(texts, "enormes cámaras de gas") < _index(texts, "Campos de concentración")


def test_complex_sidebar_reads_section_by_section():
    order, _, text = real(FIXTURES / "complex_sidebar.pdf")
    texts = main_texts(order, text)
    c, d = _index(texts, "CRelaciones"), _index(texts, "D Razonamiento")
    assert c < _index(texts, "El conflicto en Vietnam") < _index(texts, "de Dat abrieron") < d
    assert d < _index(texts, "El uso de sustancias")


def test_background_worksheet_reads_section_by_section():
    order, _, text = real(FIXTURES / "background_worksheet.pdf")
    texts = main_texts(order, text)
    a, b = _index(texts, "A A Relaciones"), _index(texts, "BComprensión")
    assert a < _index(texts, "Durante la Guerra Fría") < b < _index(texts, "Nueve presidentes")
    side = next(
        s for s in order.streams if any(text(lid).startswith("Usa tu libro") for lid in s.line_ids)
    )
    assert a < side.anchor.position < b
    table = next(s for s in order.streams if s.kind == "table")
    assert table.anchor.position > b


def test_u07_rotated_table_in_its_own_frame():
    order, layout, text = real(UNSEEN / "u07_immigrant_rotated_table.pdf")
    texts = main_texts(order, text)
    title = _index(texts, "Table 4.1")
    table = next(s for s in order.streams if s.kind == "table")
    assert table.anchor.position >= title
    assert any(s.kind == "rotated" for s in layout.scopes)


@pytest.mark.parametrize("name", ["u01_art_index_3col", "u02_science_index"])
def test_three_column_indexes_read_column_by_column(name):
    order, layout, text = real(UNSEEN / f"{name}.pdf")
    band = max(layout.bands, key=lambda b: b.column_count)
    assert band.column_count == 3
    lane_of = {
        lid: r.lane_index for r in layout.regions if r.band_id == band.id for lid in r.line_ids
    }
    sequence = [lane_of[lid] for lid in order.main.line_ids if lid in lane_of]
    assert sequence == sorted(sequence) and set(sequence) == {0, 1, 2}


# ---------------------------------------------------- invariant, 24 pages

PAGES = sorted(FIXTURES.glob("*.pdf")) + [
    UNSEEN / f"{row['id']}.pdf"
    for row in json.loads(
        (ROOT / "experiments/out/step4av/fixtures_manifest.json").read_text("utf-8")
    )
]


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.stem)
def test_every_line_is_ordered_exactly_once(path):
    order, layout, _ = real(path)
    assert check(order, layout) == []
    ordered = [lid for s in order.streams for lid in s.line_ids]
    assert sorted(ordered) == sorted(line.id for line in layout.lines)
    assert not [d for d in order.decisions if d.kind == "unplaced"]
