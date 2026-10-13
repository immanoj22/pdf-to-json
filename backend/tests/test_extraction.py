"""Native extraction boundaries, stability and validated per-page cache."""

import json

import pymupdf
import pytest
from conftest import ROOT

from book_core.cache_store import read_json
from book_core.extraction.cache import CachedExtractor
from book_core.extraction.interfaces import Extractor
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.ingestion.provisional import provision_page
from book_core.ledger.accounting import check


class CountingExtractor:
    def __init__(self):
        self.backend = PyMuPDFExtractor()
        self.calls = 0

    @property
    def identity(self):
        return self.backend.identity

    def extract_pages(self, source):
        self.calls += 1
        yield from self.backend.extract_pages(source)


def test_cache_hits_stable_ids_and_corruption_rejected(tmp_path):
    source = ROOT / "experiments/fixtures/column_26.pdf"
    backend = CountingExtractor()
    assert isinstance(backend, Extractor)
    cached = CachedExtractor(backend, tmp_path)
    first = list(cached.extract_pages(source))
    second = list(cached.extract_pages(source))
    assert first == second
    assert provision_page(first[0])[0].id == provision_page(second[0])[0].id
    assert backend.calls == 1 and cached.cache_hits == cached.cache_misses == 1
    assert list(PyMuPDFExtractor().extract_pages(source)) == first
    page_path = next(tmp_path.glob("*/page_*.json"))
    entry = read_json(page_path)
    entry["payload"]["geometry"]["rotation"] = 90
    page_path.write_text(json.dumps(entry), "utf-8")
    with pytest.raises(ValueError, match="Corrupt"):
        list(cached.extract_pages(source))


def test_incomplete_cache_has_no_completed_manifest(tmp_path):
    source = ROOT / "experiments/fixtures/column_26.pdf"
    cached = CachedExtractor(PyMuPDFExtractor(), tmp_path)
    iterator = cached.extract_pages(source)
    next(iterator)
    iterator.close()
    assert not list(tmp_path.glob("*/manifest.json"))
    list(cached.extract_pages(source))
    assert len(list(tmp_path.glob("*/manifest.json"))) == 1


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_nonzero_cropbox_and_rotation_use_same_native_frame(tmp_path, rotation):
    source = tmp_path / "geometry.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=400, height=400)
        page.insert_text((120, 120), "retained words")
        page.insert_text((120, 260), "excluded words")
        page.set_cropbox(pymupdf.Rect(100, 100, 350, 350))
        page.set_trimbox(pymupdf.Rect(110, 110, 330, 230))
        page.set_rotation(rotation)
        pdf.save(source)
    extracted = list(PyMuPDFExtractor().extract_pages(source))[0]
    assert extracted.geometry.content_bbox.model_dump() == {
        "x0": 10.0,
        "y0": 10.0,
        "x1": 230.0,
        "y1": 130.0,
    }
    document, ledger = provision_page(extracted)
    report = check(document, ledger)
    assert report.passing
    assert report.node_token_count == report.discard_token_count == 2
    assert extracted.geometry.rotation == rotation
