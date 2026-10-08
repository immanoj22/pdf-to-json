"""Validated per-page model evidence cache; no text-store or ledger input."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.detection.interfaces import RegionDetector
from book_core.detection.models import DetectionInput, DetectionResult
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.layout.pipeline import LAYOUT_VERSION
from book_core.objects.analysis import atomic_write, verified_read

DETECTION_CACHE_VERSION = "region-evidence-1"
MODEL_RENDER_DPI = 72  # Phase 0: one pixel per PDF point, full unrotated crop.
LOADED_CODE_DIGEST = code_digest("detection")


def detection_fingerprint(page: DetectionInput, detector: RegionDetector, resolved_device=None):
    """All producing code, render/configuration and actual device identify a result."""
    device = resolved_device or detector.device.resolved
    dependencies = {
        **runtime_versions(),
        **detector.dependency_versions,
        **{name: version(name) for name in ("pymupdf", "pydantic", "shapely", "regex")},
    }
    identity = {
        "source_sha256": page.source_sha256,
        "page": page.page,
        "render_sha256": hashlib.sha256(page.raster.png).hexdigest(),
        "render_dimensions": [page.raster.width, page.raster.height],
        "page_bbox": page.page_bbox.model_dump(),
        "page_dimensions": [page.raster.page_width, page.raster.page_height],
        "layout_version": LAYOUT_VERSION,
        "cache_version": DETECTION_CACHE_VERSION,
        "producer_sha256": code_digest("detection"),
        "detector_producer_sha256": detector.producer_source_sha256,
        "detector": detector.name,
        "repo_id": detector.repo_id,
        "revision": detector.revision,
        "threshold": detector.threshold,
        "dependencies": dependencies,
        "requested_device": detector.device.requested,
        "resolved_device": device,
    }
    return stable_id(json.dumps(identity, sort_keys=True, separators=(",", ":")))


def validate_result(result, page, detector, device):
    expected = (
        page.source_sha256,
        page.page,
        detector.name,
        detector.repo_id,
        detector.revision,
        detector.threshold,
        device,
        detector.device.requested,
    )
    actual = (
        result.source_sha256,
        result.page,
        result.detector,
        result.repo_id,
        result.revision,
        result.threshold,
        result.device.resolved,
        result.device.requested,
    )
    if expected != actual or result.dependency_versions != detector.dependency_versions:
        raise ValueError("Detector cache identity/configuration/device mismatch")


def detect_cached(page: DetectionInput, detector: RegionDetector, cache_dir=None):
    """Cache successful evidence under its execution device, including CPU recovery."""
    assert_producer_unchanged("detection", LOADED_CODE_DIGEST)
    fingerprint = detection_fingerprint(page, detector)
    root = Path(cache_dir) / "detections" if cache_dir is not None else None
    path = root / fingerprint / f"{page.page}.json" if root is not None else None
    if path is not None and path.exists():
        result = verified_read(path, DetectionResult, fingerprint)
        validate_result(result, page, detector, detector.device.resolved)
        return result
    result = detector.detect(page)
    assert_producer_unchanged("detection", LOADED_CODE_DIGEST)
    validate_result(result, page, detector, result.device.resolved)
    # The adapter records any GPU failure and retries the full operation on CPU.
    fingerprint = detection_fingerprint(page, detector, result.device.resolved)
    if root is not None:
        atomic_write(root / fingerprint / f"{page.page}.json", result, fingerprint)
    return result


def detect_page(source, page_number, extractor, detector, cache_dir=None, *, dpi=MODEL_RENDER_DPI):
    """Rendering goes through ObjectExtractor; models receive pixels only."""
    source = Path(source)
    before = source.stat()
    digest = source_digest(source)
    raster = extractor.render_page(source, page_number, dpi=dpi)
    page = DetectionInput.from_raster(digest, page_number, raster)
    result = detect_cached(page, detector, cache_dir)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during model evidence detection")
    return result
