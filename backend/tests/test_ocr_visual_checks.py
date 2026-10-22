"""Independent detector agreement cannot silently authorize text inside figures."""

from types import SimpleNamespace

from book_core.model.common import BBox
from book_core.objects.models import NativeObjectPage, PageObject
from book_core.ocr.detection import detect_ocr_regions
from book_core.ocr.visual_checks import agreed_text_checks


def result(page, name, rows):
    return SimpleNamespace(
        source_sha256=page.page.source_sha256,
        page=1,
        detector=name,
        regions=[SimpleNamespace(type=kind, bbox=box) for kind, box in rows],
    )


def scan(make_page, parts=()):
    source = make_page(parts)
    objects = [
        PageObject(
            id=s.id,
            kind="text",
            source_page=1,
            bbox=s.bbox,
            source_spans=[s.id],
            provenance=s.provenance,
        )
        for s in source.store.spans.values()
    ]
    objects.append(
        PageObject(
            id="raster",
            kind="image",
            source_page=1,
            bbox=source.geometry.content_bbox,
            provenance=source.store.spans[next(iter(source.store.spans))].provenance
            if source.store.spans
            else {},
        )
    )
    return NativeObjectPage(page=source, objects=objects, paint_commands=[])


def test_agreed_text_is_qualified_and_photograph_text_is_masked(make_page):
    page = scan(make_page)
    text = BBox(x0=10, y0=10, x1=90, y1=30)
    figure = BBox(x0=0, y0=40, x1=100, y1=90)
    jersey = BBox(x0=45, y0=60, x1=55, y1=70)
    first = result(page, "heron", [("title_candidate", text), ("figure", figure)])
    second = result(page, "pp", [("main_text", text), ("main_text", jersey)])
    initial = detect_ocr_regions(page)
    checks = agreed_text_checks(page, initial, first, second, [text, jersey], evidence=["proof"])
    assert len(checks) == 1 and checks[0].bbox == text
    assert checks[0].excluded_figure_boxes == [figure]
    qualified = detect_ocr_regions(page, render_checks=checks)
    assert qualified.decision == "ocr"
    approved = [r for r in qualified.regions if r.action == "ocr"]
    assert len(approved) == 1 and approved[0].bbox.y1 < figure.y0


def test_one_reader_text_and_no_text_detector_support_do_not_qualify(make_page):
    page = scan(make_page)
    box = BBox(x0=10, y0=10, x1=90, y1=30)
    first = result(page, "heron", [("main_text", box)])
    second = result(page, "pp", [("figure", box)])
    initial = detect_ocr_regions(page)
    assert not agreed_text_checks(page, initial, first, second, [box], evidence=["proof"])
    second = result(page, "pp", [("main_text", box)])
    assert not agreed_text_checks(page, initial, first, second, [], evidence=["proof"])


def test_usable_native_text_never_becomes_ocr_and_overlaps_are_one_region(make_page):
    page = scan(make_page, ("Native words",))
    box = BBox(x0=10, y0=10, x1=90, y1=30)
    initial = detect_ocr_regions(page)
    first = result(page, "heron", [("main_text", box)])
    second = result(page, "pp", [("main_text", box), ("heading_candidate", box)])
    assert not agreed_text_checks(page, initial, first, second, [box], evidence=["proof"])
    page = scan(make_page)
    initial = detect_ocr_regions(page)
    checks = agreed_text_checks(page, initial, first, second, [box], evidence=["proof"])
    assert len(checks) == 1
