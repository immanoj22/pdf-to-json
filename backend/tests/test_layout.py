"""Step 4a layout proposals: lines, per-band columns, regions, gold and review policy."""

import json
import unicodedata

import cv2
import numpy as np
import pymupdf
import pytest
from conftest import ROOT

from book_core.cli import main
from book_core.evaluation.layout_gold import evaluate, passes
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.layout.lines import build_lines
from book_core.layout.models import PageLayout, VisualLine
from book_core.layout.pipeline import analyze_layout
from book_core.ledger.accounting import check
from book_core.model.common import BBox, Provenance
from book_core.model.spans import (
    ExtractedPage,
    ExtractorIdentity,
    PageGeometry,
    SourceLine,
    SpanStore,
    TextSpan,
)
from book_core.objects.models import NativeObjectPage, PageObject, SpanGeometry

GOLD = sorted((ROOT / "backend/tests/gold").glob("columns_*.json"))
CACHE = ROOT / ".cache/objects"


@pytest.fixture(scope="module")
def layouts():
    backend = PyMuPDFExtractor()
    result = {}
    for path in GOLD:
        name = json.loads(path.read_text("utf-8"))["fixture"]
        source = ROOT / "experiments/fixtures" / f"{name}.pdf"
        result[name] = analyze_layout(source, 1, backend, cache_dir=CACHE)
    return result


@pytest.mark.parametrize("path", GOLD, ids=[path.stem for path in GOLD])
def test_bands_and_columns_match_gold(path, layouts):
    gold = json.loads(path.read_text("utf-8"))
    layout, analysis = layouts[gold["fixture"]]
    assert gold["source_sha256"] == layout.source_sha256 == analysis.native.page.source_sha256
    assert gold["human_approved"] is False
    result = evaluate(layout, gold)
    failures = [b for b in result["bands"] if not b["uncertain"] and not b["columns_match"]]
    assert passes(result), (failures, result["extra_bands"])


@pytest.mark.parametrize("path", GOLD, ids=[path.stem for path in GOLD])
def test_lines_own_every_span_and_ledger_unchanged(path, layouts):
    layout, analysis = layouts[json.loads(path.read_text("utf-8"))["fixture"]]
    store = analysis.native.page.store
    owned = [sid for line in layout.lines for sid in line.span_ids]
    assert sorted(owned) == sorted(store.spans)
    assert "text" not in VisualLine.model_fields and "raw_text" not in VisualLine.model_fields
    assert PageLayout.model_validate_json(layout.model_dump_json()) == layout
    report = check(*provision_page(analysis.native.page))
    assert report.passing and report.missing_token_count == report.extra_token_count == 0


def test_unknown_visual_objects_are_flagged_never_blocking(layouts):
    for layout, analysis in layouts.values():
        unknown = {r.object_id for r in analysis.asset_ledger.records if r.role == "unknown"}
        flagged = {f.subject_id for f in layout.review_flags if f.subject_kind == "visual_object"}
        assert unknown == flagged
        assert all(flag.blocking is False for flag in layout.review_flags)
        assert all(r.review_required for r in layout.regions if r.type == "unknown")


def test_rotated_credit_stays_a_separate_line(layouts):
    layout, _ = layouts["column_26"]
    rotated = [line for line in layout.lines if not line.horizontal and not line.blank]
    assert rotated and all(abs(line.rotation - 90) < 1 for line in rotated)
    regions = {lid: r.type for r in layout.regions for lid in r.line_ids}
    assert {regions[line.id] for line in rotated} == {"credit_candidate"}


def test_figure_lane_and_inset_are_not_columns(layouts):
    science, _ = layouts["science_dissolving"]
    body = max(science.bands, key=lambda b: b.bbox.y1 - b.bbox.y0)
    assert [lane.kind for lane in body.lanes] == ["column", "figure"] and body.column_count == 1
    pull_quote, _ = layouts["column_26"]
    two = next(b for b in pull_quote.bands if b.column_count == 2)
    assert two.inset_block_ids and len(two.lanes) == 2


def write_columns(path, columns, *, title=False, image_band=None, top=100, bottom=700):
    words = (
        "La historia explora cómo cambian las sociedades y por qué permanecen iguales "
        "a lo largo del tiempo en distintas regiones del mundo "
    ) * 5
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        if title:
            page.insert_text((50, 70), "Título de prueba que cruza toda la página", fontsize=22)
        width = (512 - 16 * (columns - 1)) / columns
        bands = (
            [(top, bottom)]
            if image_band is None
            else [(top, image_band[0] - 12), (image_band[1] + 12, bottom)]
        )
        for y0, y1 in bands:
            for i in range(columns):
                x0 = 50 + i * (width + 16)
                rect = pymupdf.Rect(x0, y0, x0 + width, y1)
                # insert_textbox writes nothing on overflow; trim until the text fits.
                text = words
                while page.insert_textbox(rect, text, fontsize=10) < 0:
                    text = text[: int(len(text) * 0.8)]
        if image_band is not None:
            array = np.full((120, 400, 3), 90, dtype=np.uint8)
            cv2.circle(array, (200, 60), 50, (20, 160, 220), -1)
            png = cv2.imencode(".png", array)[1].tobytes()
            page.insert_image(pymupdf.Rect(50, image_band[0], 562, image_band[1]), stream=png)
        pdf.save(path)


def page_bands(layout):
    page = next(scope.id for scope in layout.scopes if scope.kind == "page")
    return sorted((b for b in layout.bands if b.scope_id == page), key=lambda b: b.bbox.y0)


@pytest.mark.parametrize("columns", [1, 2, 3])
def test_synthetic_column_count_is_measured_not_assumed(tmp_path, columns):
    source = tmp_path / f"columns_{columns}.pdf"
    write_columns(source, columns)
    layout, _ = analyze_layout(source, 1, PyMuPDFExtractor())
    bands = page_bands(layout)
    assert [b.column_count for b in bands] == [columns]


def test_synthetic_bands_change_where_structure_changes(tmp_path):
    source = tmp_path / "bands.pdf"
    write_columns(source, 2, title=True, image_band=(330, 450))
    layout, _ = analyze_layout(source, 1, PyMuPDFExtractor())
    bands = page_bands(layout)
    assert [b.column_count for b in bands] == [1, 2, 0, 2]
    assert [lane.kind for lane in bands[2].lanes] == ["figure"]


def synthetic_native(texts, direction=(1.0, 0.0), mode="horizontal"):
    provenance = Provenance(source_sha256="b" * 64)
    spans, objects, geometry = {}, [], {}
    lines = []
    for i, text in enumerate(texts):
        sid, lid = f"span-{i}", f"line-{i}"
        x0 = 20 + i * 60
        bbox = BBox(x0=x0, y0=40, x1=x0 + 50, y1=52)
        spans[sid] = TextSpan(
            id=sid,
            line_id=lid,
            page=1,
            raw_text=text,
            text=unicodedata.normalize("NFKC", text),
            bbox=bbox,
            font="test",
            size=10,
            color=0,
            flags=0,
            provenance=provenance,
        )
        lines.append(SourceLine(id=lid, page=1, bbox=bbox, span_ids=[sid]))
        objects.append(
            PageObject(
                id=sid,
                kind="text",
                bbox=bbox,
                source_page=1,
                source_spans=[sid],
                provenance=provenance,
            )
        )
        geometry[sid] = SpanGeometry(
            origin=(x0, 50), direction=direction, writing_mode=mode, ascender=0.9, descender=-0.2
        )
    page = ExtractedPage(
        source_sha256="b" * 64,
        extractor=ExtractorIdentity(name="test", version="1", configuration={}),
        geometry=PageGeometry(
            page=1, width=300, height=100, rotation=0, content_bbox=BBox(x0=0, y0=0, x1=300, y1=100)
        ),
        store=SpanStore(spans=spans, lines=lines),
    )
    return NativeObjectPage(page=page, objects=objects, paint_commands=[], span_geometry=geometry)


def test_direction_comes_from_unicode_not_assumed():
    rtl = build_lines(synthetic_native(["שלום", "עולם"]))
    assert len(rtl) == 1 and rtl[0].text_direction == "rtl"
    assert rtl[0].span_ids == ["span-0", "span-1"]
    neutral = build_lines(synthetic_native(["123", "456"]))
    assert neutral[0].text_direction is None
    vertical = build_lines(synthetic_native(["縦書き"], direction=(0.0, 1.0), mode="vertical"))
    assert vertical[0].writing_mode == "vertical" and vertical[0].text_direction == "ttb"
    assert abs(vertical[0].rotation - 270) < 1e-6


def test_layout_cache_roundtrip_and_corruption(tmp_path):
    source = ROOT / "experiments/fixtures/column_100.pdf"
    backend = PyMuPDFExtractor("cpu")
    first, _ = analyze_layout(source, 1, backend, cache_dir=tmp_path)
    assert first == analyze_layout(source, 1, backend, cache_dir=tmp_path)[0]
    assert first.provenance.resolved_device == "cpu" and first.provenance.execution_device == "cpu"
    path = next((tmp_path / "layout").glob("*/*.json"))
    entry = json.loads(path.read_text("utf-8"))
    entry["payload"] = entry["payload"].replace('"column_count":2', '"column_count":3', 1)
    path.write_text(json.dumps(entry), "utf-8")
    with pytest.raises(ValueError, match="Corrupt"):
        analyze_layout(source, 1, backend, cache_dir=tmp_path)


def test_regions_overlay_cli(tmp_path):
    output = tmp_path / "regions.png"
    arguments = [
        "overlay",
        str(ROOT / "experiments/fixtures/complex_cards.pdf"),
        "--page",
        "1",
        "--regions",
        "--out",
        str(output),
        "--cache-dir",
        str(tmp_path / "cache"),
    ]
    assert main(arguments) == 0
    image = cv2.imdecode(np.frombuffer(output.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image is not None
    layout = PageLayout.model_validate_json(output.with_suffix(".json").read_text("utf-8"))
    assert any(lane.kind == "card" for band in layout.bands for lane in band.lanes)
