"""Step 4a-fix: layout invariants I1-I7 on synthetic pages and on real fixtures.

Every synthetic page is generated with PyMuPDF inside the test. Real unseen fixtures that
are not tracked in git (oversized) are recreated with experiments/recreate_unseen_fixtures.py
and skipped here with an explicit message when absent.
"""

import json

import cv2
import numpy as np
import pymupdf
import pytest
from conftest import ROOT

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.invariants import check
from book_core.layout.models import Band, Lane, PageLayout, Region, Scope, VisualLine
from book_core.layout.pipeline import analyze_layout
from book_core.model.common import BBox, Provenance

BODY = (
    "The vibrating electric and magnetic fields of the wave exert forces on the charged "
    "particles and magnetic materials that make up the object, so the particles gain energy "
    "and the surface warms during the long sunny afternoon. "
) * 3


def png(array):
    return cv2.imencode(".png", array)[1].tobytes()


def textured(height, width, seed=7):
    rng = np.random.default_rng(seed)
    array = rng.integers(40, 220, size=(height, width, 3), dtype=np.uint8)
    for k in range(12):
        cv2.circle(array, (int(width * (k + 1) / 13), height // 2), height // 5, (20, 60, 200), 3)
    return array


def fit(page, rect, text, size=10, font="helv"):
    while page.insert_textbox(rect, text, fontsize=size, fontname=font) < 0:
        text = text[: int(len(text) * 0.8)]


def run(source):
    layout, analysis = analyze_layout(source, 1, PyMuPDFExtractor())
    return layout, analysis, check(layout, analysis)


def text_of(layout, analysis, line_ids):
    store = analysis.native.page.store
    lines = {line.id: line for line in layout.lines}
    return [
        "".join(store.spans[s].raw_text for s in lines[lid].span_ids).strip() for lid in line_ids
    ]


def region_types(layout, analysis):
    """Text of each non-blank line -> region type."""
    out = {}
    for region in layout.regions:
        for text in text_of(layout, analysis, region.line_ids):
            if text:
                out[text] = region.type
    return out


# ---------------------------------------------------------------- I1, I2: model validation


def provenance():
    return Provenance(source_sha256="c" * 64)


def lane(index, x0, x1, kind="column"):
    return Lane(index=index, x0=x0, x1=x1, kind=kind, line_count=1, confidence=0.8, reasons=["t"])


def test_i1_lane_rejects_non_positive_width():
    with pytest.raises(ValueError, match="x0 < x1"):
        lane(0, 466.0, 242.0)
    with pytest.raises(ValueError, match="x0 < x1"):
        lane(0, 100.0, 100.0)
    assert lane(0, 10.0, 20.0).x1 == 20.0


def _line(lid, y0, y1):
    return VisualLine(
        id=lid,
        span_ids=[f"s-{lid}"],
        source_line_ids=[f"n-{lid}"],
        bbox=BBox(x0=50, y0=y0, x1=300, y1=y1),
        baseline_start=(50, y1 - 2),
        baseline_end=(300, y1 - 2),
        direction=(1.0, 0.0),
        rotation=0.0,
        writing_mode="horizontal",
        font_size=10.0,
        visible=True,
        inside_content=True,
    )


def _layout(bands, scopes, lines):
    regions = [
        Region(
            id=f"r-{line.id}",
            type="main_text",
            bbox=line.bbox,
            scope_id=scopes[0].id,
            line_ids=[line.id],
            confidence=0.8,
            reasons=["t"],
        )
        for line in lines
    ]
    return PageLayout(
        source_sha256="c" * 64,
        page=1,
        layout_version="t",
        content_bbox=BBox(x0=0, y0=0, x1=612, y1=792),
        lines=lines,
        scopes=scopes,
        bands=bands,
        regions=regions,
        provenance=provenance(),
    )


def _band(bid, scope, y0, y1):
    return Band(
        id=bid,
        scope_id=scope,
        bbox=BBox(x0=50, y0=y0, x1=300, y1=y1),
        lanes=[lane(0, 50, 300)],
        column_count=1,
        confidence=0.8,
        reasons=["t"],
    )


def test_i2_bands_of_one_scope_must_not_overlap():
    page = Scope(id="page", kind="page", bbox=BBox(x0=0, y0=0, x1=612, y1=792))
    lines = [_line("a", 100, 112), _line("b", 300, 312)]
    with pytest.raises(ValueError, match="overlap"):
        _layout([_band("b1", "page", 100, 250), _band("b2", "page", 200, 400)], [page], lines)
    # Touching within half a font size is not an overlap.
    _layout([_band("b1", "page", 100, 250), _band("b2", "page", 254, 400)], [page], lines)
    _layout([_band("b1", "page", 100, 250), _band("b2", "page", 246, 400)], [page], lines)
    # A nested callout scope may hold bands inside a page band.
    callout = Scope(
        id="box", kind="callout", bbox=BBox(x0=60, y0=120, x1=290, y1=240), parent_id="page"
    )
    _layout([_band("b1", "page", 100, 250), _band("c1", "box", 130, 230)], [page, callout], lines)


# ---------------------------------------------------------------- I3: labels only in figures


def write_faded_figure(path):
    """A picture whose raster continues as a flat fade under a heading and running text."""
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        array = np.full((480, 900, 3), 250, dtype=np.uint8)
        array[:300] = textured(300, 900)
        page.insert_image(pymupdf.Rect(72, 90, 540, 340), stream=png(array))
        page.insert_text((120, 150), "Nucleus", fontsize=9, fontname="hebo")
        page.insert_text((300, 200), "Electrons", fontsize=9, fontname="hebo")
        page.insert_text((80, 272), "Waves interact with matter", fontsize=14, fontname="hebo")
        fit(page, pymupdf.Rect(80, 280, 540, 336), BODY)
        fit(page, pymupdf.Rect(80, 360, 540, 700), BODY * 2)
        pdf.save(path)


def test_i3_running_text_over_a_faded_picture_stays_in_the_flow(tmp_path):
    source = tmp_path / "faded.pdf"
    write_faded_figure(source)
    layout, analysis, violations = run(source)
    assert violations["I3"] == []
    types = region_types(layout, analysis)
    assert types["Nucleus"] == "figure" and types["Electrons"] == "figure"
    assert types["Waves interact with matter"] != "figure"
    assert sum(t == "figure" for t in types.values()) == 2


def write_flat_backdrop(path):
    """Text set on a raster of flat colour fields (title bar and panel): a backdrop."""
    people = [
        ("Danielle Chirip", "University High School", "Orlando, FL"),
        ("Carol Jones", "Macomb Intermediate", "Clinton Township, MI"),
        ("Sara Tondra", "Marysville High School", "Marysville, OH"),
        ("Dwight Dutton", "East Chapel Hill School", "Chapel Hill, NC"),
        ("Shelli Pace", "Captain Shreve School", "Shreveport, LA"),
        ("Tiffany Tammasini", "Cypress Creek School", "Orlando, FL"),
    ]
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        panel = np.full((330, 600, 3), (225, 222, 218), dtype=np.uint8)
        panel[:80] = (150, 80, 120)
        page.insert_image(pymupdf.Rect(40, 60, 572, 390), stream=png(panel))
        page.insert_text((72, 100), "AUTHORS AND REVIEWERS", fontsize=20, color=(1, 1, 1))
        page.insert_text((72, 160), "High School Reviewers", fontsize=16, fontname="hebo")
        fit(page, pymupdf.Rect(72, 170, 540, 205), BODY[:150])
        for i, (name, school, city) in enumerate(people):
            x, y = 72 + (i % 3) * 160, 230 + (i // 3) * 60
            page.insert_text((x, y), name, fontsize=10, fontname="hebo")
            page.insert_text((x, y + 14), school, fontsize=10)
            page.insert_text((x, y + 28), city, fontsize=10)
        fit(page, pymupdf.Rect(72, 410, 540, 700), BODY * 2)
        pdf.save(path)


def test_i3_flat_backdrop_is_not_a_figure(tmp_path):
    source = tmp_path / "backdrop.pdf"
    write_flat_backdrop(source)
    layout, analysis, violations = run(source)
    assert violations["I3"] == []
    types = region_types(layout, analysis)
    assert "figure" not in types.values()
    assert not [b for b in layout.blocks if b.kind == "figure"]


# ---------------------------------------------------------------- I4: content frame


def write_bleed_figure(path):
    """A picture bleeding off the page under a footer line in the bottom furniture zone."""
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.set_trimbox(pymupdf.Rect(36, 36, 576, 756))
        page.insert_image(pymupdf.Rect(-10, -10, 300, 760), stream=png(textured(600, 240)))
        page.insert_text((100, 300), "Gran Cuenca", fontsize=12, fontname="hebo")
        page.insert_text((150, 420), "Llano Estacado", fontsize=10, fontname="hebo")
        page.insert_text(
            (60, 745),
            "Explore the digital edition for maps, timelines and interactive tools.",
            fontsize=9,
        )
        pdf.save(path)


def test_i4_figure_stays_in_content_and_never_takes_furniture(tmp_path):
    source = tmp_path / "bleed.pdf"
    write_bleed_figure(source)
    layout, analysis, violations = run(source)
    assert violations["I4"] == []
    content = layout.content_bbox
    for block in layout.blocks:
        if block.kind == "figure":
            assert content.x0 - 1 <= block.bbox.x0 and block.bbox.x1 <= content.x1 + 1
            assert content.y0 - 1 <= block.bbox.y0 and block.bbox.y1 <= content.y1 + 1
    types = region_types(layout, analysis)
    footer = next(t for t in types if t.startswith("Explore the digital"))
    assert types[footer] != "figure"
    assert types["Gran Cuenca"] == "figure"


# ---------------------------------------------------------------- I5: rotated structure


def write_rotated_table(path, with_credit=True):
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.insert_text(
            (90, 700), "Table 4.1 Means and standard deviations", fontsize=11, rotate=90
        )
        labels = ["Sociability", "Aggression", "Shyness", "Victimization", "Popularity"]
        values = [["-.39", "(.66)", "1.21"], [".12", "(.95)", "3.54"], ["-.04", "(.70)", "2.96"]]
        for r, label in enumerate(labels):
            x = 130 + r * 26
            page.insert_text((x, 700), label, fontsize=10, rotate=90)
            for c, value in enumerate(values[r % 3]):
                page.insert_text((x, 520 - c * 110), value, fontsize=10, rotate=90)
        page.insert_text(
            (300, 700), "Note. Standard deviations in parentheses.", fontsize=8, rotate=90
        )
        if with_credit:
            page.insert_image(pymupdf.Rect(360, 100, 540, 300), stream=png(textured(200, 180)))
            page.insert_text((562, 300), "Photo: Example Agency", fontsize=6, rotate=90)
        pdf.save(path)


def test_i5_rotated_cells_build_structure_not_credits(tmp_path):
    source = tmp_path / "rotated.pdf"
    write_rotated_table(source)
    layout, analysis, violations = run(source)
    assert violations["I5"] == []
    types = region_types(layout, analysis)
    assert types["Sociability"] != "credit_candidate"
    assert types["Photo: Example Agency"] == "credit_candidate"
    rotated_scopes = [s for s in layout.scopes if s.kind == "rotated"]
    assert len(rotated_scopes) == 1 and abs(rotated_scopes[0].rotation - 90) < 1
    rotated_ids = {line.id for line in layout.lines if not line.horizontal and not line.blank} - {
        lid for r in layout.regions if r.type == "credit_candidate" for lid in r.line_ids
    }
    banded = {lid for r in layout.regions if r.band_id is not None for lid in r.line_ids}
    assert rotated_ids <= banded
    assert any(r.type == "table_candidate" for r in layout.regions)


# ---------------------------------------------------------------- I6: tables


def write_unruled_table(path):
    rows = [
        ("Cape Verde", "65,485", "16.0"),
        ("Brazil", "65,463", "16.0"),
        ("Ukraine", "37,851", "9.3"),
        ("Angola", "33,215", "8.1"),
        ("Moldova", "12,673", "3.1"),
        ("Romania", "10,299", "2.5"),
        ("China", "9,695", "2.4"),
    ]
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 90), "Table 10.1 Foreigners with legal residence", fontsize=10)
        page.insert_text((72, 112), "Nationality", fontsize=10)
        page.insert_text((300, 112), "2006", fontsize=10)
        page.insert_text((450, 112), "%", fontsize=10)
        for i, (name, count, share) in enumerate(rows):
            y = 132 + i * 15
            page.insert_text((72, y), name, fontsize=10)
            page.insert_text((300, y), count, fontsize=10)
            page.insert_text((450, y), share, fontsize=10)
        fit(page, pymupdf.Rect(72, 260, 540, 700), BODY * 2)
        pdf.save(path)


def test_i6_aligned_numeric_cells_are_a_table_candidate(tmp_path):
    source = tmp_path / "unruled.pdf"
    write_unruled_table(source)
    layout, analysis, violations = run(source)
    assert violations["I6"] == []
    types = region_types(layout, analysis)
    assert types["65,485"] == "table_candidate" and types["Ukraine"] == "table_candidate"
    assert types[next(t for t in types if t.startswith("The vibrating"))] == "main_text"


def test_i6_multi_column_prose_is_not_a_table(tmp_path):
    from test_layout import write_columns

    source = tmp_path / "prose.pdf"
    write_columns(source, 3)
    layout, _, violations = run(source)
    assert violations["I6"] == []
    assert not any(r.type == "table_candidate" for r in layout.regions)


def write_split_grid(path):
    """One ruled table drawn as a header grid and a body grid with a heavy rule between."""
    columns = [72, 200, 330, 460, 540]
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        header = page.new_shape()
        header.draw_rect(pymupdf.Rect(72, 80, 540, 120))
        header.draw_line((72, 100), (540, 100))
        for x in columns[1:-1]:
            header.draw_line((x, 80), (x, 120))
        header.finish(color=(0, 0, 0), width=0.5)
        header.commit()
        page.draw_line((72, 121), (540, 121), color=(0, 0, 0), width=3)
        body = page.new_shape()
        body.draw_rect(pymupdf.Rect(72, 124, 540, 244))
        for x in columns[1:-1]:
            body.draw_line((x, 124), (x, 244))
        for y in range(144, 244, 20):
            body.draw_line((72, y), (540, y))
        body.finish(color=(0, 0, 0), width=0.5)
        body.commit()
        for c, title in enumerate(["Hazard", "Examples", "Precaution", "Remedy"]):
            page.insert_text((columns[c] + 4, 94), title, fontsize=9)
            page.insert_text((columns[c] + 4, 114), f"({c + 1})", fontsize=9)
        for r in range(6):
            for c in range(4):
                page.insert_text((columns[c] + 4, 138 + r * 20), f"cell {r}-{c}", fontsize=9)
        fit(page, pymupdf.Rect(72, 280, 540, 700), BODY)
        pdf.save(path)


def test_i6_a_ruled_grid_is_not_split_at_a_heavy_rule(tmp_path):
    source = tmp_path / "grid.pdf"
    write_split_grid(source)
    layout, analysis, violations = run(source)
    assert violations["I6"] == []
    tables = [r for r in layout.regions if r.type == "table_candidate"]
    assert len(tables) == 1
    texts = text_of(layout, analysis, tables[0].line_ids)
    assert "Hazard" in texts and "cell 5-3" in texts


# ---------------------------------------------------------------- I7: edges and locators


def write_edge_strip(path):
    """A tall stack of narrow decorative bars along the right edge of the content frame."""
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.set_trimbox(pymupdf.Rect(36, 36, 576, 756))
        for k in range(8):
            page.draw_rect(
                pymupdf.Rect(546, 20 + k * 30, 582, 520 + k * 30),
                color=None,
                fill=(0.3 + 0.05 * k, 0.4, 0.6),
            )
        fit(page, pymupdf.Rect(72, 72, 520, 720), BODY * 4)
        pdf.save(path)


def test_i7_edge_strip_opens_no_lane(tmp_path):
    source = tmp_path / "strip.pdf"
    write_edge_strip(source)
    layout, _, violations = run(source)
    assert violations["I7"] == [] and violations["I2"] == []
    page = next(s.id for s in layout.scopes if s.kind == "page")
    bands = [b for b in layout.bands if b.scope_id == page]
    assert [b.column_count for b in bands] == [1]
    assert all(lane.kind == "column" for lane in bands[0].lanes)


def write_glossary(path):
    """Two language columns of running text with a column of page references between."""
    spanish = (
        "equidad trato justo y sistemático para todas las personas de la nación; "
        "imperialismo política de una nación poderosa que ejerce control sobre otra; "
    ) * 6
    english = (
        "equity the consistent and systematic fair treatment of all individuals; "
        "imperialism the policy of a powerful nation exercising control over others; "
    ) * 6
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        fit(page, pymupdf.Rect(60, 100, 240, 400), spanish, 9)
        for i in range(14):
            page.insert_text((290, 106 + i * 22), f"(pág. {100 + 37 * i})", fontsize=9)
        fit(page, pymupdf.Rect(380, 100, 560, 400), english, 9)
        pdf.save(path)


def test_i7_locator_column_is_not_a_text_column(tmp_path):
    source = tmp_path / "glossary.pdf"
    write_glossary(source)
    layout, _, violations = run(source)
    assert violations["I7"] == [] and violations["I1"] == [] and violations["I2"] == []
    page = next(s.id for s in layout.scopes if s.kind == "page")
    assert max(b.column_count for b in layout.bands if b.scope_id == page) == 2


# ---------------------------------------------------------------- real fixtures

FIXTURES = sorted(p.stem for p in (ROOT / "experiments/fixtures").glob("*.pdf"))
UNSEEN = [
    row["id"]
    for row in json.loads(
        (ROOT / "experiments/out/step4av/fixtures_manifest.json").read_text("utf-8")
    )
]
CACHE = ROOT / ".cache/objects"


def real(path):
    if not path.exists():
        pytest.skip(
            f"{path.name} is not tracked (oversized); recreate it with "
            "`python experiments/recreate_unseen_fixtures.py`"
        )
    layout, analysis = analyze_layout(path, 1, PyMuPDFExtractor(), cache_dir=CACHE)
    return check(layout, analysis)


@pytest.mark.parametrize("name", FIXTURES)
def test_invariants_hold_on_gold_fixtures(name):
    violations = real(ROOT / "experiments/fixtures" / f"{name}.pdf")
    assert {k: v for k, v in violations.items() if v} == {}


@pytest.mark.parametrize("name", UNSEEN)
def test_invariants_hold_on_unseen_pages(name):
    violations = real(ROOT / "experiments/fixtures_unseen" / f"{name}.pdf")
    assert {k: v for k, v in violations.items() if v} == {}
