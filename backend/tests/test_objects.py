"""Native object evidence, critical role protections and unchanged text conservation."""

import json
from collections import Counter

import cv2
import numpy as np
import pymupdf
import pytest
from conftest import ROOT

from book_core.cli import main
from book_core.device import DeviceResolution, resolve_device, run_with_device
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check
from book_core.ledger.tokenization import token_counter
from book_core.model.common import BBox, Provenance, SpanRef
from book_core.objects.analysis import analyze_page, cached_repetition, verify_asset_ledger
from book_core.objects.models import ObjectAnalysis, PageObject
from book_core.objects.spatial import build_graph
from book_core.settings import Settings

FIXTURES = sorted(source.stem for source in (ROOT / "experiments/fixtures").glob("*.pdf"))


@pytest.fixture(scope="module")
def analyses():
    backend = PyMuPDFExtractor()
    return {
        name: analyze_page(
            ROOT / "experiments/fixtures" / f"{name}.pdf",
            1,
            backend,
            cache_dir=ROOT / ".cache/objects",
        )
        for name in FIXTURES
    }


@pytest.mark.parametrize("name", FIXTURES)
def test_asset_and_text_conservation(name, analyses):
    analysis = analyses[name]
    assert verify_asset_ledger(analysis)["missing"] == 0
    assert analysis.graph_complete
    native = analysis.native
    ordinary = list(
        PyMuPDFExtractor().extract_pages(ROOT / "experiments/fixtures" / f"{name}.pdf")
    )[0]
    assert native.page == ordinary
    document, ledger = provision_page(native.page)
    report = check(document, ledger)
    assert report.passing and report.missing_token_count == report.extra_token_count == 0
    assert ObjectAnalysis.model_validate_json(analysis.model_dump_json()) == analysis
    assert {obj.id for obj in native.objects if obj.kind == "text"} == set(native.page.store.spans)
    assert all(
        record.reasons and (record.role != "unknown" or record.review_required)
        for record in analysis.asset_ledger.records
    )


@pytest.mark.parametrize("name", ["science_dissolving", "science_fission"])
def test_science_members_and_labels_retained(name, analyses):
    analysis = analyses[name]
    assert analysis.compounds
    native = {obj.id: obj for obj in analysis.native.objects}
    shade_compounds = [
        obj
        for obj in analysis.compounds
        if all(native[member].kind == "shading" for member in obj.member_ids)
    ]
    assert max(len(obj.member_ids) for obj in shade_compounds) >= 100
    linked = {
        (edge.source, edge.target) for edge in analysis.relations if "member_of" in edge.kinds
    }
    assert all(
        (member, obj.id) in linked for obj in analysis.compounds for member in obj.member_ids
    )
    document, ledger = provision_page(analysis.native.page)
    before = Counter()
    for line in analysis.native.page.store.lines:
        if analysis.native.page.geometry.content_bbox.contains_center(line.bbox):
            before.update(token_counter(analysis.native.page.store.raw_line_text(line)))
    result = check(document, ledger, before)
    assert result.passing
    # These native labels must remain represented, even when they overlap visual compounds.
    label = "Step" if name == "science_dissolving" else "neutron"
    assert before[label] > 0
    assert any(
        token_counter(document.span_store.resolve_content(node.content))[label]
        for node in document.iter_nodes()
    )


@pytest.mark.parametrize("name", ["background_worksheet", "colored_box"])
def test_background_objects_cannot_be_content_or_figures(name, analyses):
    gold = json.loads((ROOT / "backend/tests/gold" / f"roles_{name}.json").read_text("utf-8"))
    records = {record.object_id: record for record in analyses[name].asset_ledger.records}
    protected = [obj for obj in gold["objects"] if obj.get("protect_backdrop")]
    assert protected
    for obj in protected:
        assert records[obj["object_id"]].role not in {"figure_part", "content_image"}
    if name == "background_worksheet":
        assert any(records[obj["object_id"]].role == "background" for obj in protected)
    else:
        assert any(records[obj["object_id"]].role == "container" for obj in protected)


def png_bytes():
    array = np.full((150, 200, 3), 215, dtype=np.uint8)
    cv2.line(array, (0, 0), (199, 149), (35, 35, 35), 3)
    return cv2.imencode(".png", array)[1].tobytes()


def test_synthetic_scan_layer_invisible_text(tmp_path):
    source = tmp_path / "scan.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=200, height=150)
        page.insert_image(page.rect, stream=png_bytes())
        page.insert_text((20, 40), "invisible original", render_mode=3)
        page.insert_text((20, 70), "other scan words", render_mode=3)
        pdf.save(source)
    analysis = analyze_page(source, 1, PyMuPDFExtractor())
    roles = {record.object_id: record.role for record in analysis.asset_ledger.records}
    image = next(obj for obj in analysis.native.objects if obj.kind == "image")
    assert roles[image.id] == "scan_layer"
    assert all(
        info.render_type == 3
        for obj in analysis.native.objects
        if obj.kind == "text"
        for info in obj.render_info
    )
    assert check(*provision_page(analysis.native.page)).passing


def test_synthetic_repeated_digest_and_cache(tmp_path):
    source = tmp_path / "repeated.pdf"
    with pymupdf.open() as pdf:
        for rotation in [0, 90, 180, 270]:
            page = pdf.new_page(width=200, height=150)
            page.insert_image(pymupdf.Rect(10, 10, 40, 30), stream=png_bytes())
            page.insert_text((60, 70), "ordinary retained text")
            page.set_rotation(rotation)
        pdf.save(source)
    backend = PyMuPDFExtractor()
    repetition = cached_repetition(source, backend, tmp_path / "cache")
    analysis = analyze_page(source, 1, backend, repetition, tmp_path / "cache")
    image = next(obj for obj in analysis.native.objects if obj.kind == "image")
    assert repetition.images[image.image_digest].page_numbers == [1, 2, 3, 4]
    assert (
        next(
            record.role for record in analysis.asset_ledger.records if record.object_id == image.id
        )
        == "repeated_artifact"
    )
    assert cached_repetition(source, backend, tmp_path / "cache") == repetition


def test_cache_corruption_rejected_and_resolved_device_fingerprinted(tmp_path):
    source = ROOT / "experiments/fixtures/column_100.pdf"
    backend = PyMuPDFExtractor("cpu")
    first = analyze_page(source, 1, backend, cache_dir=tmp_path)
    assert first == analyze_page(source, 1, backend, cache_dir=tmp_path)
    path = next((tmp_path / "analysis").glob("*/*.json"))
    entry = json.loads(path.read_text("utf-8"))
    entry["payload"] = entry["payload"].replace('"graph_complete":true', '"graph_complete":false')
    path.write_text(json.dumps(entry), "utf-8")
    with pytest.raises(ValueError, match="Corrupt"):
        analyze_page(source, 1, backend, cache_dir=tmp_path)
    backend.device = DeviceResolution(requested="auto", resolved="cuda")
    second = analyze_page(source, 1, backend, cache_dir=tmp_path)
    assert len(list((tmp_path / "analysis").glob("*/*.json"))) == 2
    assert set(first.native.page.store.spans) == set(second.native.page.store.spans)
    assert second.native.objects[0].provenance.resolved_device == "cuda"
    assert second.native.objects[0].provenance.execution_device == "cpu"


def test_dense_map_keeps_path_items_and_uses_index(analyses):
    analysis = analyses["complex_map"]
    assert sum(len(obj.path_items) for obj in analysis.native.objects) >= 100_000
    assert analysis.candidate_pairs_checked < 100_000
    _, _, complete, notes, _ = build_graph(
        analysis.all_objects(), analysis.compounds, candidate_limit=10
    )
    assert not complete and notes
    assert verify_asset_ledger(analysis)["missing"] == 0


def test_spatial_relations_preserve_multiple_kinds():
    evidence = Provenance()
    objects = [
        PageObject(
            id="outer",
            kind="drawing",
            source_page=1,
            bbox=BBox(x0=0, y0=0, x1=10, y1=10),
            paint_sequences=[1],
            provenance=evidence,
        ),
        PageObject(
            id="inner",
            kind="image",
            source_page=1,
            bbox=BBox(x0=2, y0=2, x1=4, y1=4),
            paint_sequences=[2],
            provenance=evidence,
        ),
        PageObject(
            id="touch",
            kind="drawing",
            source_page=1,
            bbox=BBox(x0=10, y0=0, x1=12, y1=5),
            paint_sequences=[3],
            provenance=evidence,
        ),
    ]
    graph, _, complete, _, _ = build_graph(objects, [])
    assert complete and "contains" in graph["outer"]["inner"]["kinds"]
    assert "drawn_above" in graph["inner"]["outer"]["kinds"]
    assert "touches" in graph["touch"]["outer"]["kinds"]


def test_device_policy_and_recovery():
    assert Settings().device == "auto"
    assert resolve_device("auto", probe=lambda: True).resolved == "cuda"

    def bad_probe():
        raise RuntimeError("unusable driver")

    assert resolve_device("cuda", probe=bad_probe).resolved == "cpu"
    calls = []

    def operation(device):
        calls.append(device)
        if device == "cuda":
            raise MemoryError("GPU allocation failed")
        return "done"

    value, resolved = run_with_device(operation, DeviceResolution(resolved="cuda"))
    assert value == "done" and calls == ["cuda", "cpu"] and resolved.resolved == "cpu"
    assert resolved.fallback_reason
    with pytest.raises(RuntimeError):
        run_with_device(lambda device: bad_probe(), DeviceResolution())


def test_range_roundtrip_and_source_resolution(make_page):
    store = make_page(parts=("first second",)).store
    ref = SpanRef(span_id="span-0", start=6, end=12)
    assert SpanRef.model_validate_json(ref.model_dump_json()) == ref
    assert store.resolve_content([ref]) == "second"
    assert store.resolve_content([SpanRef(span_id="span-0")]) == "first second"
    with pytest.raises(ValueError):
        SpanRef(span_id="span-0", start=6)
    with pytest.raises(ValueError):
        store.resolve_content([SpanRef(span_id="span-0", start=0, end=99)])


def test_overlay_cli(tmp_path):
    output = tmp_path / "overlay.png"
    assert (
        main(
            [
                "overlay",
                str(ROOT / "experiments/fixtures/colored_box.pdf"),
                "--page",
                "1",
                "--out",
                str(output),
                "--cache-dir",
                str(tmp_path / "cache"),
            ]
        )
        == 0
    )
    assert (
        cv2.imdecode(np.frombuffer(output.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        is not None
    )
    assert ObjectAnalysis.model_validate_json(output.with_suffix(".json").read_text("utf-8"))


def test_typed_render_contract_roundtrip():
    from book_core.extraction.interfaces import ObjectExtractor
    from book_core.extraction.rasters import RasterPage

    backend = PyMuPDFExtractor()
    assert isinstance(backend, ObjectExtractor)
    raster = backend.render_page(ROOT / "experiments/fixtures/colored_box.pdf", 1, dpi=72)
    assert RasterPage.model_validate_json(raster.model_dump_json()) == raster
