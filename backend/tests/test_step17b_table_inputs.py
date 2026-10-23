"""The bounded audit reader must preserve the ordinary table-stage evidence."""
import pymupdf
import pytest
from step17b_table_inputs import TableObjects

from book_core.cache_store import read_json, write_json, write_model
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.objects.analysis import write_analysis
from book_core.objects.models import AssetLedger, CompoundVisual, ObjectAnalysis
from book_core.tables.rulings import freeform, page_rules


@pytest.fixture
def input_pair(tmp_path):
    pdf = tmp_path / "objects.pdf"
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), 'River [a] {b} "quoted"')
        page.draw_rect((30, 60, 160, 120), fill=(.2, .4, .8))
        page.draw_rect((50, 80, 100, 100), fill=(1, 1, 1))
        page.draw_polyline([(40, 150), (100, 160), (180, 145)], closePath=False)
        page.draw_bezier((40, 190), (80, 180), (130, 210), (180, 190))
        page.draw_line((40, 230), (180, 230))
        doc.save(pdf)
    native = PyMuPDFExtractor("cpu").extract_object_page(pdf, 1)
    drawing = next(o for o in native.objects if o.kind == "drawing")
    compound = CompoundVisual(**{**drawing.model_dump(), "id": "compound",
                                  "kind": "compound", "member_ids": [drawing.id],
                                  "evidence_notes": ['escaped \\ "quoted" [braces] {x}']})
    analysis = ObjectAnalysis(native=native, compounds=[compound],
                              asset_ledger=AssetLedger(records=[]))
    native_path, analysis_path = tmp_path / "native.json", tmp_path / "analysis.json"
    native_key, analysis_key = "a" * 64, "b" * 64
    write_model(native_path, native, native_key)
    write_analysis(analysis_path, analysis, analysis_key, native_key)
    return native, analysis, native_path, native_key, analysis_path, analysis_key


def features(objects):
    return (page_rules(objects, 10), freeform(objects),
            {o.id: o.kind for o in objects if o.kind in {"drawing", "image", "compound"}},
            {o.id: o.member_ids for o in objects if o.kind == "compound"})


def test_bounded_native_reader_preserves_table_evidence(input_pair):
    native, analysis, *args = input_pair
    ordinary = [*native.objects, *analysis.compounds]
    bounded = TableObjects(*args)
    assert features(bounded) == features(ordinary)
    # Repeated table passes must see the entire same paths, including lengths.
    assert features(bounded) == features(ordinary)
    assert [(o.id, list(o.path_items)) for o in bounded] == [
        (o.id, o.path_items) for o in ordinary]


@pytest.mark.parametrize("field", ["fingerprint", "sha256"])
def test_bounded_native_reader_rejects_changed_cache_identity(input_pair, field):
    _, _, *args = input_pair
    entry = read_json(args[0])
    entry[field] = "0" * 64
    write_json(args[0], entry)
    with pytest.raises(AssertionError):
        TableObjects(*args)
