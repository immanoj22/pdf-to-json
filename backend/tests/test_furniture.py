"""Step 8: furniture roles, folio sequence and page markers (synthetic books and labels)."""

import unicodedata

import pytest

from book_core.furniture.apply import apply_page, line_roles, page_marker
from book_core.furniture.cache import decide_book
from book_core.furniture.classify import Classifier
from book_core.furniture.features import page_features
from book_core.furniture.labels import label_candidates, parse_label, to_roman
from book_core.furniture.models import PageFurniture, PageMarker
from book_core.furniture.sequence import Candidate, SequenceConfig, page_labels
from book_core.layout.models import Band, Lane, PageLayout, Region, Scope, VisualLine
from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)
from book_core.reading_order.builder import build_reading_order
from book_core.reading_order.graph import check

SOURCE = "c" * 64
WIDTH, HEIGHT = 612.0, 792.0


# ------------------------------------------------------------------ labels


@pytest.mark.parametrize(
    ("text", "kind", "value", "rendered"),
    [
        ("12", "arabic", 12, "12"),
        ("— 7 —", "arabic", 7, "7"),
        ("xiv", "roman", 14, "xiv"),
        ("XL", "roman", 40, "XL"),
        ("HT12", "prefixed", 12, "HT12"),
        ("3-14", "prefixed", 14, "3-14"),
        ("٤٥", "arabic", 45, "45"),  # Arabic-Indic digits
        ("४२", "arabic", 42, "42"),  # Devanagari digits
    ],
)
def test_label_parsing_is_script_agnostic(text, kind, value, rendered):
    label = parse_label(text)
    assert (label.kind, label.value, label.render()) == (kind, value, rendered)


def test_labels_reject_prose_and_keep_overprint_alternatives():
    assert parse_label("Chapter 3") is None
    assert parse_label("0") is None
    assert parse_label("Índice") is None
    assert [label.value for label in label_candidates("438438438")] == [438]
    assert [label.value for label in label_candidates("8080")] == [8080, 80]
    assert to_roman(1994) == "mcmxciv"


# ------------------------------------------------------------------ sequence


def _candidates(rows):
    return [
        Candidate(page, f"l{page}-{i}", parse_label(text), quality)
        for page, items in rows.items()
        for i, (text, quality) in enumerate(items)
    ]


def test_roman_then_arabic_with_reset_blank_and_missing_folios():
    rows = {
        1: [("i", 1.0)],
        2: [("ii", 1.0)],
        4: [("iv", 1.0)],  # page 3: missing folio
        # page 5: blank
        7: [("2", 1.0)],  # page 6: unnumbered opener of a run starting at 1
        8: [("3", 1.0)],
        9: [("4", 1.0), ("7", 0.3)],  # a number-only table cell
        10: [("5", 1.0)],
        11: [("6", 1.0)],
        12: [("1", 1.0)],  # reset: a new part restarts at 1
        13: [("2", 1.0)],
        15: [("4", 1.0)],  # page 14: missing folio
        16: [("5", 1.0)],
    }
    labels, runs, _ = page_labels(list(range(1, 17)), _candidates(rows))
    by = {d.page: d for d in labels}
    assert [r.series[0] for r in runs] == ["roman", "arabic", "arabic"]
    assert (by[3].label, by[3].source) == ("iii", "inferred")
    assert (by[5].label, by[5].source) == ("v", "inferred")
    assert by[5].review_required
    assert (by[6].label, by[6].source) == ("1", "inferred")
    assert (by[9].label, by[9].folio.line_id) == ("4", "l9-0")
    assert (by[12].label, by[12].source) == ("1", "printed")
    assert (by[14].label, by[14].source) == ("3", "inferred")
    assert all(d.label is not None for d in labels)


def test_stray_numbers_do_not_form_a_sequence():
    rows = {page: [(str(value), 0.3)] for page, value in ((2, 40), (5, 7), (9, 113), (12, 3))}
    labels, runs, _ = page_labels(list(range(1, 15)), _candidates(rows))
    assert runs == []
    assert all(d.source == "none" for d in labels)


def test_inferred_label_never_duplicates_a_printed_label():
    rows = {p: [(str(p), 1.0)] for p in range(1, 6)}
    rows.update({p: [(str(p - 3), 1.0)] for p in range(9, 14)})  # pages 6-8: inserts
    labels, _, _ = page_labels(list(range(1, 14)), _candidates(rows))
    by = {d.page: d for d in labels}
    # Extrapolating 6-8 from the first run would repeat labels printed by the next run.
    assert [by[p].label for p in (6, 7, 8)] == [None, None, None]
    assert by[5].label == "5" and by[9].label == "6"


def test_metadata_is_compared_and_trusted_only_when_it_agrees():
    # Printed folios on pages 4-11 except 6; pages 1-3 are front matter without folios.
    rows = {p: [(str(p - 3), 1.0)] for p in range(4, 12) if p != 6}
    agreeing = {p: (["i", "ii", "iii"][p - 1] if p <= 3 else str(p - 3)) for p in range(1, 14)}
    labels, _, comparison = page_labels(list(range(1, 14)), _candidates(rows), agreeing)
    by = {d.page: d for d in labels}
    assert comparison["trusted"] and comparison["agreement"] == 1.0
    # Front matter only: metadata labels pages before the first printed run.
    assert [(by[p].source, by[p].label) for p in (1, 2, 3)] == [("metadata", "i"),
        ("metadata", "ii"), ("metadata", "iii")]  # fmt: skip
    # Inside and after the runs, inference decides; agreeing metadata raises confidence.
    assert (by[6].source, by[6].label, by[6].confidence) == ("inferred", "3", 0.9)
    assert (by[12].source, by[12].label) == ("inferred", "9")
    assert by[13].source == "inferred" and by[13].label == "10"
    assert by[4].source == "printed"
    rows = {p: [(str(p), 1.0)] for p in range(1, 11) if p != 6}
    wrong = {p: str(p + 100) for p in range(1, 13)}
    labels, _, comparison = page_labels(list(range(1, 13)), _candidates(rows), wrong)
    by = {d.page: d for d in labels}
    assert not comparison["trusted"]
    assert by[6].source == "inferred" and by[3].review_required
    assert "metadata differs" in " ".join(by[3].reasons)


def test_sequence_configuration_is_validated():
    with pytest.raises(ValueError):
        SequenceConfig(switch_penalty=0)


# ------------------------------------------------------------------ synthetic book


class PageBuilder:
    def __init__(self, number):
        self.number = number
        self.lines, self.spans, self.source_lines, self.regions, self.bands = [], {}, [], [], []
        self.scopes = [Scope(id="page", kind="page", bbox=BBox(x0=0, y0=0, x1=WIDTH, y1=HEIGHT))]

    def line(self, lid, x0, y0, x1, text, size=10.0, direction="ltr", font="Serif"):
        lid = f"p{self.number}-{lid}"
        box = BBox(x0=x0, y0=y0, x1=x1, y1=y0 + size * 1.2)
        sid = f"s-{lid}"
        self.spans[sid] = TextSpan(
            id=sid,
            line_id=f"n-{lid}",
            page=self.number,
            raw_text=text,
            text=unicodedata.normalize("NFKC", text),
            bbox=box,
            font=font,
            size=size,
            color=0,
            flags=0,
            text_direction=direction,
            provenance=Provenance(source_sha256=SOURCE),
        )
        self.source_lines.append(
            SourceLine(id=f"n-{lid}", page=self.number, bbox=box, span_ids=[sid])
        )
        line = VisualLine(
            id=lid,
            span_ids=[sid],
            source_line_ids=[f"n-{lid}"],
            bbox=box,
            baseline_start=(x0, box.y1 - 2),
            baseline_end=(x1, box.y1 - 2),
            direction=(1.0, 0.0),
            rotation=0.0,
            writing_mode="horizontal",
            text_direction=direction,
            font_size=size,
            visible=True,
            inside_content=True,
        )
        self.lines.append(line)
        return line

    def band(self, bid, y0, y1, lanes):
        lanes = [
            Lane(index=i, x0=a, x1=b, kind=k, line_count=1, confidence=0.8, reasons=["t"])
            for i, (a, b, k) in enumerate(lanes)
        ]
        bid = f"p{self.number}-{bid}"
        x0, x1 = min(lane.x0 for lane in lanes), max(lane.x1 for lane in lanes)
        self.bands.append(
            Band(
                id=bid,
                scope_id="page",
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                lanes=lanes,
                column_count=sum(lane.kind == "column" for lane in lanes),
                confidence=0.8,
                reasons=["t"],
            )
        )
        return bid

    def region(self, rid, kind, lines, band=None, lane=None):
        self.regions.append(
            Region(
                id=f"p{self.number}-{rid}",
                type=kind,
                bbox=BBox(
                    x0=min(line.bbox.x0 for line in lines),
                    y0=min(line.bbox.y0 for line in lines),
                    x1=max(line.bbox.x1 for line in lines),
                    y1=max(line.bbox.y1 for line in lines),
                ),
                scope_id="page",
                band_id=band,
                lane_index=lane,
                line_ids=[line.id for line in lines],
                confidence=0.8,
                reasons=["t"],
            )
        )

    def build(self):
        frame = BBox(x0=0, y0=0, x1=WIDTH, y1=HEIGHT)
        layout = PageLayout(
            source_sha256=SOURCE,
            page=self.number,
            layout_version="t",
            content_bbox=frame,
            lines=self.lines,
            scopes=self.scopes,
            bands=self.bands,
            regions=self.regions,
            provenance=Provenance(source_sha256=SOURCE),
        )
        page = ExtractedPage(
            source_sha256=SOURCE,
            extractor=ExtractorIdentity(name="t", version="1", configuration={}),
            geometry=PageGeometry(
                page=self.number, width=WIDTH, height=HEIGHT, rotation=0, content_bbox=frame
            ),
            store=SpanStore(spans=self.spans, lines=self.source_lines),
        )
        order = build_reading_order(layout, page.store)
        assert check(order, layout) == []
        return page, layout, order


HEBREW = ["שלום עולם וטקסט ארוך מאוד", "המשך השורה בעברית כאן", "סוף הפסקה בעברית."]
LATIN = ["The body text of this page runs on", "and continues in the next line here", "to end."]

# Physical page -> printed folio (None: unnumbered); roman front matter, a blank page, an
# unnumbered opener, a missing folio, then a part that restarts at 1.
FOLIOS = {1: "i", 2: "ii", 3: None, 4: "iv", 5: "BLANK", 6: None, 7: "2", 8: "3", 9: "4",
          10: "5", 11: "6", 12: "1", 13: "2", 14: "3", 15: None, 16: "5"}  # fmt: skip


def synthetic_page(number):
    """One page: running head (side alternates with parity), body column, folio."""
    page = PageBuilder(number)
    if FOLIOS[number] == "BLANK":
        return page.build()
    rtl = number == 14
    text = HEBREW if rtl else LATIN
    direction = "rtl" if rtl else "ltr"
    even = number % 2 == 0
    body = [
        page.line(f"b{i}", 60, 110 + 14 * i, 550, text[i % 3], direction=direction)
        for i in range(36)
    ]
    body_band = page.band("body", 110, 620, [(60, 550, "column")])
    page.region("body", "main_text", body, body_band, 0)
    if number not in {6, 12}:  # openers carry no running head
        head_text = (
            "ספר סינתטי" if rtl else "A SYNTHETIC BOOK" if even else f"Chapter {number // 4}"
        )
        x0, x1 = (60, 220) if even else (390, 550)
        head = page.line("head", x0, 30, x1, head_text, size=9.0, direction=direction)
        # Step 4 typed some heads as text; Step 8 must still find them.
        page.region("head", "main_text" if number % 3 else "header_footer_candidate", [head])
    folio = FOLIOS[number]
    if folio is not None:
        x0, x1 = (60, 80) if even else (530, 550)
        line = page.line("folio", x0, 750, x1, folio, size=9.0, direction=direction)
        page.region("folio", "page_number_candidate", [line])
    if number == 9:  # a number-only table cell near the bottom edge
        cells = [page.line("c1", 100, 700, 200, "Total"), page.line("c2", 300, 700, 320, "7")]
        band = page.band("table", 698, 715, [(100, 320, "table")])
        page.region("table", "table_candidate", cells, band, 0)
    if number in {10, 11, 13}:  # a map label at the top edge, inside a figure
        label = page.line("map", 250, 60, 330, "Energy", size=8.0)
        band = page.band("fig", 55, 100, [(240, 340, "figure")])
        page.region("fig", "figure", [label], band, 0)
    return page.build()


@pytest.fixture(scope="module")
def book():
    pages = {n: synthetic_page(n) for n in FOLIOS}
    features = {n: page_features(*pages[n]) for n in pages}
    decisions = decide_book(features, {}, SOURCE)
    return pages, decisions


def _roles(decisions, number):
    return {r.line_id.split("-", 1)[1]: r for r in decisions.roles[number]}


def test_odd_even_running_heads_and_folios(book):
    _, decisions = book
    for number in (2, 3, 7, 8, 14):
        roles = _roles(decisions, number)
        assert roles["head"].role == "running_head", number
        assert roles["b0"].role == "content"
    for number, folio in FOLIOS.items():
        if folio not in {None, "BLANK"}:
            assert _roles(decisions, number)["folio"].role == "folio", number
    head_group = next(g for g in decisions.book.groups if g.role == "running_head")
    assert head_group.evidence["side_alternation"] == 1.0


def test_table_cell_and_map_label_stay_content(book):
    _, decisions = book
    assert _roles(decisions, 9)["c2"].role == "content"
    for number in (10, 11, 13):
        assert _roles(decisions, number)["map"].role == "content"


def test_markers_cover_every_physical_page(book):
    _, decisions = book
    markers = {m.page: m for m in decisions.book.markers}
    expected = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "1", 7: "2", 11: "6", 12: "1",
                15: "4", 16: "5"}  # fmt: skip
    for page, label in expected.items():
        assert markers[page].label == label, page
    assert markers[3].source == "inferred" and not markers[3].folio_line_ids
    assert markers[14].source == "printed"  # right-to-left page
    assert markers[14].folio_line_ids == ["p14-folio"]
    assert [r.kind for r in decisions.book.runs] == ["roman", "arabic", "arabic"]


def test_apply_streams_furniture_by_role_and_orders_every_line_once(book):
    pages, decisions = book
    for number, (page, layout, order) in pages.items():
        result = apply_page(
            page, layout, order, decisions.roles[number], decisions.book.markers[number - 1]
        )
        assert check(result.order, None) == []
        ordered = [lid for s in result.order.streams for lid in s.line_ids]
        assert sorted(ordered) == sorted(line.id for line in layout.lines)
        roles = {r.line_id: r.role for r in result.roles}
        for role, stream_id in result.furniture_streams.items():
            stream = next(s for s in result.order.streams if s.id == stream_id)
            assert stream.kind == "furniture"
            assert {roles[lid] for lid in stream.line_ids} == {role}
        main = set(result.order.main.line_ids)
        assert not any(roles[lid] in {"running_head", "folio"} for lid in main)
        if layout.lines:
            assert f"p{number}-b0" in main


def _box_book(box_text):
    pages = {}
    for number in range(1, 7):
        page = PageBuilder(number)
        body = [page.line(f"b{i}", 60, 110 + 14 * i, 550, LATIN[i % 3]) for i in range(30)]
        band = page.band("body", 110, 540, [(60, 550, "column")])
        page.region("body", "main_text", body, band, 0)
        box = page.line("box", 100, 720, 520, box_text, size=7.5)
        page.region("box", "header_footer_candidate", [box])
        folio = page.line("folio", 530, 750, 550, str(number + 20), size=9.0)
        page.region("folio", "page_number_candidate", [folio])
        pages[number] = page.build()
    return pages


def test_repeated_text_without_a_drawn_box_stays_plain_content():
    box_text = "CONNECT Explore the digital edition of this book for maps, timelines and more"
    pages = _box_book(box_text)
    features = {n: page_features(*pages[n]) for n in pages}
    decisions = decide_book(features, {}, SOURCE, box_lines=lambda page, rows: set())
    for number in pages:
        role = _roles(decisions, number)["box"]
        assert role.role == "content"
        assert "without a drawn box" in role.reasons[0]


def test_drawn_box_evidence_from_native_drawings():
    from types import SimpleNamespace

    from book_core.furniture.boxes import boxed_lines

    def drawing(x0, y0, x1, y1, fill=None, stroke=None):
        return SimpleNamespace(
            kind="drawing", bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), fill=fill,
            fill_opacity=None, stroke=stroke, stroke_width=1.0 if stroke else None,
        )  # fmt: skip

    def row(lid, x0, y0, x1, y1):
        return SimpleNamespace(line_id=lid, bbox=(x0, y0, x1, y1), blank=False, font_size=8.0)

    geometry = SimpleNamespace(width=WIDTH, height=HEIGHT)
    native = SimpleNamespace(
        page=SimpleNamespace(geometry=geometry),
        objects=[
            drawing(30, 700, 200, 714, fill=[0.3, 0.3, 0.3]),  # dark bar
            drawing(195, 700, 560, 714, fill=[0.86, 0.86, 0.86]),  # light fill
            drawing(50, 400, 300, 460, stroke=[0, 0, 0]),  # stroked frame
            drawing(0, 0, WIDTH, HEIGHT, fill=[1, 1, 1]),  # page background: ignored
        ],
    )
    rows = [
        row("filled", 100, 701, 520, 713),
        row("framed", 60, 420, 280, 432),
        row("plain", 60, 600, 500, 612),
    ]
    assert boxed_lines(native, rows) == {"filled", "framed"}


def test_repeated_box_stays_content_and_false_furniture_returns_to_the_flow():
    pages = {}
    box_text = "CONNECT Explore the digital edition of this book for maps, timelines and more"
    pages.update(_box_book(box_text))
    features = {n: page_features(*pages[n]) for n in pages}
    boxed = {n: {f"p{n}-box"} for n in pages}
    decisions = decide_book(features, {}, SOURCE, box_lines=lambda page, rows: boxed[page])
    for number, (page, layout, order) in pages.items():
        roles = _roles(decisions, number)
        assert roles["box"].role == "repeated_box"
        result = apply_page(
            page, layout, order, decisions.roles[number], decisions.book.markers[number - 1]
        )
        kinds = {lid: s.kind for s in result.order.streams for lid in s.line_ids}
        assert kinds[f"p{number}-box"] not in {"furniture", "artifact"}
        assert kinds[f"p{number}-folio"] == "furniture"
        assert result.marker.label == str(number + 20)


def test_low_confidence_furniture_stays_content():
    # Large repeated top text on few, sparse pages: kept as content (and flagged if close).
    pages = {}
    for number in range(1, 13):
        page = PageBuilder(number)
        body = [page.line(f"b{i}", 60, 110 + 14 * i, 550, LATIN[i % 3]) for i in range(30)]
        band = page.band("body", 110, 540, [(60, 550, "column")])
        page.region("body", "main_text", body, band, 0)
        if number in {2, 7, 12}:
            title = page.line("title", 60, 30, 400, "RESEARCH ACTIVITY", size=16.0)
            page.region("title", "heading_candidate", [title])
        pages[number] = page.build()
    features = {n: page_features(*pages[n]) for n in pages}
    decisions = decide_book(features, {}, SOURCE)
    for number in (2, 7, 12):
        assert _roles(decisions, number)["title"].role == "content"


def test_classifier_needs_explicit_evidence_not_repetition_alone():
    pages = {n: synthetic_page(n) for n in (7, 8, 9)}
    features = {n: page_features(*pages[n]) for n in pages}
    classifier = Classifier(features).run()
    assert {d["role"] for d in classifier.roles.values()} <= {
        "running_head",
        "running_foot",
        "folio",
        "production_mark",
        "repeated_box",
        "content",
    }


def test_page_marker_model_rules():
    with pytest.raises(ValueError):
        PageMarker(page=1, label="1", kind="arabic", source="printed", confidence=1, reasons=["x"])
    with pytest.raises(ValueError):
        PageMarker(page=1, label=None, kind="none", source="inferred", confidence=1, reasons=["x"])
    PageMarker(page=1, label=None, kind="none", source="none", confidence=0.5, reasons=["none"])


def test_page_furniture_rejects_content_in_a_furniture_stream(book):
    pages, decisions = book
    page, layout, order = pages[8]
    result = apply_page(page, layout, order, decisions.roles[8], decisions.book.markers[7])
    folio_stream = result.furniture_streams["folio"]
    data = result.model_dump()
    data["furniture_streams"] = {"running_head": folio_stream}
    with pytest.raises(ValueError):
        PageFurniture.model_validate(data)
    assert line_roles({"x": {"role": "content", "confidence": 1, "reasons": ["r"]}})
    assert page_marker  # exported helper
