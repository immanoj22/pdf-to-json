"""I7 on synthetic pages: edge strips open no reading lane; number columns by structure.

Reproduces the Step 18 causes: a coloured thumb tab at the page edge, its rotated chapter
text in its own scope, opened a text-free lane beside the body; short index entries
("variable 7") were taken for a column of bare page numbers. Step 19 hold-out: two gutters
that only touch opened a lane of zero width between them.
"""

from types import SimpleNamespace

import pymupdf
import pytest

from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.bands import Element, make_band, merge_gutters
from book_core.layout.evidence import locator_cell
from book_core.layout.invariants import check
from book_core.layout.models import Gutter
from book_core.layout.pipeline import analyze_layout
from book_core.model.common import BBox

BODY = (
    "The middle ear passes sound from the tympanic membrane to the inner ear through "
    "a chain of three small bones that amplify the vibration before it reaches the fluid. "
)


def layout_of(path):
    layout, analysis = analyze_layout(path, 1, PyMuPDFExtractor("cpu"))
    return layout, check(layout, analysis)


@pytest.mark.parametrize("side", ["left", "right"])
def test_a_thumb_tab_at_the_page_edge_opens_no_lane(tmp_path, side):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    x = 80 if side == "left" else 150
    for k in range(38):
        page.insert_text((x, 80 + 16 * k), (BODY * 3)[k * 7 : k * 7 + 88], fontsize=9.5)
    tab = pymupdf.Rect(24, 150, 62, 600) if side == "left" else pymupdf.Rect(550, 150, 588, 600)
    page.draw_rect(tab, color=None, fill=(0.2, 0.4, 0.7))
    for text, y, font in (("Chapter", 560, "hebo"), ("3", 512, "tiro"), ("The Ear", 498, "hebo")):
        page.insert_text((tab.x0 + 24, y), text, fontsize=11, rotate=90, color=(1, 1, 1),
                         fontname=font)  # fmt: skip
    path = tmp_path / "tab.pdf"
    doc.save(path)
    layout, violations = layout_of(path)
    assert violations["I7"] == []
    assert all(lane.line_count > 0 for band in layout.bands for lane in band.lanes)
    # The tab stays a callout with its own rotated text.
    assert any(region.type == "callout" for region in layout.regions)


def index_page(path, third):
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    long_entries = [f"standard error of the mean value {n}" for n in range(30, 60)]
    for k in range(30):
        y = 80 + 16 * k
        page.insert_text((60, y), long_entries[k][:26], fontsize=9)
        page.insert_text((240, y), long_entries[29 - k][:26], fontsize=9)
        page.insert_text((430, y), third(k), fontsize=9)
    doc.save(path)
    return layout_of(path)


def test_short_index_entries_stay_a_text_column(tmp_path):
    layout, violations = index_page(tmp_path / "index.pdf", lambda k: f"variable {k + 7}")
    assert violations["I7"] == []
    (band,) = [b for b in layout.bands if len(b.lanes) > 1]
    assert [lane.kind for lane in band.lanes] == ["column"] * 3


def test_a_lane_of_bare_page_numbers_joins_its_text_lane(tmp_path):
    layout, violations = index_page(tmp_path / "toc.pdf", lambda k: f"{3 * k + 11}")
    assert violations["I7"] == []
    (band,) = [b for b in layout.bands if len(b.lanes) > 1]
    assert len(band.lanes) == 2


@pytest.mark.parametrize(
    "text,expected",
    [("45", True), ("45-47", True), ("12, 15", True), ("xvii 4", True), ("p. 45", True),
     ("(pág. 137)", True), ("variable 7", False), ("6. Malignant lesions", False),
     ("Z", False), ("ear 45", False), ("(pág. HT19)", True), ("A-12", True),
     ("HT19, HT20", True), ("anatomy 12a", False), ("variable V3", False)],
)  # fmt: skip
def test_a_locator_cell_holds_locators_only(text, expected):
    assert locator_cell(text) is expected


def test_touching_gutters_are_one_cut():
    def gutter(x0, x1, y0):
        return Gutter(x0=x0, x1=x1, y0=y0, y1=y0 + 50, left_items=1, right_items=1,
                      ink_fraction=0, confidence=0.9, reasons=["test"])  # fmt: skip

    (merged,) = merge_gutters([gutter(420.0, 441.5, 100), gutter(441.5, 460.0, 160)])
    assert (merged.x0, merged.x1, merged.y0, merged.y1) == (441.5, 441.5, 100, 210)
    assert len(merge_gutters([gutter(420.0, 441.0, 100), gutter(441.5, 460.0, 160)])) == 2


def test_a_band_with_touching_gutters_opens_no_zero_width_lane():
    # The hold-out case: four gutters, the third and fourth meeting at x=441.5; before the
    # fix, lane 3 ran from 441.5 to 441.5 and the band failed validation.
    def gutter(x0, x1):
        return Gutter(x0=x0, x1=x1, y0=100, y1=300, left_items=1, right_items=1,
                      ink_fraction=0, confidence=0.9, reasons=["test"])  # fmt: skip

    def line(name, x0, x1, y):
        return Element(id=name, bbox=BBox(x0=x0, y0=y, x1=x1, y1=y + 10), kind="line")

    columns = [(50, 100), (120, 200), (220, 420), (460, 560)]
    members = [line(f"l{c}{r}", x0, x1, 100 + 20 * r) for c, (x0, x1) in enumerate(columns)
               for r in range(10)]  # fmt: skip
    bbox = BBox(x0=50, y0=100, x1=560, y1=300)
    scope = SimpleNamespace(id="scope", bbox=bbox)
    gutters = [gutter(100, 120), gutter(200, 220), gutter(420, 441.5), gutter(441.5, 460)]
    band, _ = make_band(scope, members, gutters, bbox, set(), 20, [], set())
    assert [(lane.x0, lane.x1) for lane in band.lanes] == [
        (50, 100), (120, 200), (220, 441.5), (441.5, 560)
    ]
    assert all(lane.x0 < lane.x1 for lane in band.lanes)
