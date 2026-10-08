"""Cache configuration, source invalidation, corruption and CPU-recovery gates."""

import json
import shutil

import pytest

from book_core import caching
from book_core.detection.cache import detect_cached, detection_fingerprint
from book_core.detection.models import DetectionInput, DetectionResult
from book_core.device import DeviceResolution
from book_core.extraction.rasters import RasterPage
from book_core.model.common import Provenance


class FakeDetector:
    name = "fake"
    repo_id = "tests/fake"
    revision = "b" * 40
    threshold = 0.5
    dependency_versions = {"test-runtime": "1"}
    producer_source_sha256 = "d" * 64

    def __init__(self, fallback=False):
        self.calls = 0
        self.fallback = fallback
        self.device = DeviceResolution(requested="auto", resolved="cuda" if fallback else "cpu")

    def detect(self, page):
        self.calls += 1
        if self.fallback:
            self.device = DeviceResolution(requested="auto", fallback_reason="test GPU failure")
        return DetectionResult(
            source_sha256=page.source_sha256,
            page=page.page,
            detector=self.name,
            repo_id=self.repo_id,
            revision=self.revision,
            threshold=self.threshold,
            dependency_versions=self.dependency_versions,
            device=self.device,
            provenance=Provenance(
                source_sha256=page.source_sha256,
                method="derived",
                resolved_device=self.device.resolved,
                execution_device=self.device.resolved,
            ),
        )


@pytest.fixture
def page():
    raster = RasterPage(
        png=b"render evidence", width=100, height=200, page_width=100, page_height=200
    )
    return DetectionInput.from_raster("a" * 64, 1, raster)


def test_per_page_cache_reuses_valid_evidence(page, tmp_path):
    detector = FakeDetector()
    result = detect_cached(page, detector, tmp_path)
    assert detect_cached(page, detector, tmp_path) == result
    assert detector.calls == 1
    other = page.model_copy(update={"page": 2})
    detect_cached(other, detector, tmp_path)
    assert detector.calls == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("threshold", 0.6),
        ("revision", "c" * 40),
        ("dependency_versions", {"test-runtime": "2"}),
        ("producer_source_sha256", "e" * 64),
    ],
)
def test_configuration_changes_cache_key(page, field, value):
    detector = FakeDetector()
    original = detection_fingerprint(page, detector)
    setattr(detector, field, value)
    assert detection_fingerprint(page, detector) != original


def test_render_and_device_change_cache_key(page):
    detector = FakeDetector()
    original = detection_fingerprint(page, detector)
    raster = page.raster.model_copy(update={"png": b"changed pixels"})
    assert detection_fingerprint(page.model_copy(update={"raster": raster}), detector) != original
    assert detection_fingerprint(page, detector, "cuda") != original


def test_source_edit_changes_real_model_cache_key(page, tmp_path, monkeypatch):
    copy = tmp_path / "book_core"
    shutil.copytree(caching.PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(caching, "PACKAGE", copy)
    detector = FakeDetector()
    original = detection_fingerprint(page, detector)
    source = copy / "detection" / "transformers.py"
    source.write_bytes(source.read_bytes() + b"\n# source changed\n")
    assert detection_fingerprint(page, detector) != original


def test_gpu_recovery_is_never_cached_under_cuda(page, tmp_path):
    detector = FakeDetector(fallback=True)
    gpu_key = detection_fingerprint(page, detector)
    result = detect_cached(page, detector, tmp_path)
    assert result.device.resolved == "cpu"
    assert not (tmp_path / "detections" / gpu_key).exists()
    cpu_key = detection_fingerprint(page, detector)
    assert (tmp_path / "detections" / cpu_key / "1.json").exists()
    assert detect_cached(page, detector, tmp_path) == result
    assert detector.calls == 1


def test_corrupt_cache_fails_instead_of_silently_reusing_it(page, tmp_path):
    detector = FakeDetector()
    detect_cached(page, detector, tmp_path)
    target = tmp_path / "detections" / detection_fingerprint(page, detector) / "1.json"
    entry = json.loads(target.read_text("utf8"))
    entry["payload"] = entry["payload"].replace('"threshold":0.5', '"threshold":0.6')
    target.write_text(json.dumps(entry), "utf8")
    with pytest.raises(ValueError, match="Corrupt"):
        detect_cached(page, detector, tmp_path)
