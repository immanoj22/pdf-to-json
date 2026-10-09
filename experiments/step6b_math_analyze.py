"""Analyze cached whole-science-book math candidates and produce five evidence overlays.

This phase can follow the detector manifest while it grows. Full native/detector/math
payloads remain in the active project's ignored cache. Summaries contain no source text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from collections import Counter
from pathlib import Path

import cv2
from reference_paths import reference_path

from book_core.accuracy.cache import canonical_digest
from book_core.accuracy.math_evidence import (
    MathEvidenceConfig,
    analyze_math_page,
    glyph_evidence,
    has_math_evidence,
)
from book_core.caching import code_digest, runtime_versions
from book_core.detection.models import DetectionResult
from book_core.extraction.cache import CACHE_VERSION, payload_digest
from book_core.extraction.cache import atomic_json as _atomic_json
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.extraction.rasters import RasterPage
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import atomic_write as _atomic_write
from book_core.objects.analysis import verified_read
from book_core.objects.models import NativeObjectPage
from book_core.objects.roles import raster_array

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/step6b"
OUT = ROOT / "experiments/out/step6b/math"


def _retry_write(operation, path, *args):
    for attempt in range(20):
        try:
            return operation(path, *args)
        except PermissionError:
            if attempt == 19:
                raise
            print(
                f"transient_atomic_retry target={path.name} attempt={attempt + 1}",
                flush=True,
            )
            time.sleep(0.1)


def atomic_json(path, value):
    return _retry_write(_atomic_json, path, value)


def atomic_write(path, value, fingerprint):
    return _retry_write(_atomic_write, path, value, fingerprint)


def checked_local(path):
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("Derived math artifacts must stay in the active workspace")
    return resolved


def native_directory(source_sha256, extractor, phase):
    if code_digest("extraction") != phase["native_producer_sha256"]:
        raise ValueError("Native producer differs from the detector phase")
    namespace = stable_id(
        source_sha256,
        CACHE_VERSION,
        json.dumps(
            extractor.identity.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ),
        code_digest("extraction"),
        json.dumps(runtime_versions(), sort_keys=True),
    )
    return CACHE / "science_native" / namespace


def read_native_page(directory, row, source_sha256):
    entry = json.loads((directory / f"page_{row['page']:06d}.json").read_text("utf-8"))
    digest = payload_digest(entry["payload"])
    if digest != entry["payload_sha256"] or digest != row["native_payload_sha256"]:
        raise ValueError("Native page checksum differs from the detector manifest")
    page = ExtractedPage.model_validate(entry["payload"])
    if page.source_sha256 != source_sha256 or page.geometry.page != row["page"]:
        raise ValueError("Native cache belongs to another source page")
    return page


def cached_raster(source, extractor, source_sha256, page, dpi):
    key = canonical_digest(
        {
            "source_sha256": source_sha256,
            "extractor": extractor.identity.model_dump(mode="json"),
            "producer_sha256": code_digest("extraction"),
            "runtime": runtime_versions(),
            "dpi": dpi,
        }
    )
    path = CACHE / "math_rasters" / key / f"{page}.json"
    if path.exists():
        return verified_read(path, RasterPage, key)
    raster = extractor.render_page(source, page, dpi=dpi)
    atomic_write(path, raster, key)
    return raster


def cached_objects(source, extractor, page):
    key = canonical_digest(
        {
            "source_sha256": page.source_sha256,
            "extractor": extractor.identity.model_dump(mode="json"),
            "producer_sha256": code_digest("extraction"),
            "runtime": runtime_versions(),
        }
    )
    path = CACHE / "math_objects" / key / f"{page.geometry.page}.json"
    if path.exists():
        native = verified_read(path, NativeObjectPage, key)
    else:
        native = extractor.extract_object_page(source, page.geometry.page)
        if native.page != page:
            raise ValueError("Object extraction changed the cached source-text evidence")
        atomic_write(path, native, key)
    if native.page != page:
        raise ValueError("Object extraction changed the cached source-text evidence")
    return native


def cached_detection(row, raw_key):
    original = checked_local(ROOT / row["detection_path"])
    cached = CACHE / "math_raw" / raw_key / f"page_{row['page']:06d}.json"
    path = cached if cached.exists() else original
    if source_digest(path) != row["detection_sha256"]:
        raise ValueError("Detector payload differs from its recorded checksum")
    if not cached.exists():
        cached.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, cached)
    return DetectionResult.model_validate_json(cached.read_text("utf-8")), cached


def page_summary(page, detection, raster, native, model_sha256, config, cache_key, input_key):
    glyph_lines = [
        line
        for line in page.store.lines
        if page.geometry.content_bbox.contains_center(line.bbox)
        and has_math_evidence(glyph_evidence(page.store.raw_line_text(line)))
    ]
    formula_count = sum(
        region.raw_label.casefold() == "formula"
        and page.geometry.content_bbox.contains_center(region.bbox)
        for region in detection.regions
    )
    evidence = None
    if native is not None:
        evidence = analyze_math_page(
            native,
            detection,
            render_sha256=hashlib.sha256(raster.png).hexdigest(),
            model_sha256=model_sha256,
            config=config,
        )
        path = CACHE / "math_evidence" / evidence.cache_key / f"{page.geometry.page}.json"
        atomic_write(path, evidence, evidence.cache_key)
    else:
        path = CACHE / "math_evidence" / input_key / f"{page.geometry.page}.json"
        atomic_json(
            path,
            {
                "source_sha256": page.source_sha256,
                "page": page.geometry.page,
                "cache_key": input_key,
                "status": "screened_no_candidate",
                "native_payload_sha256": payload_digest(page.model_dump(mode="json")),
                "detector_sha256": canonical_digest(detection.model_dump(mode="json")),
                "render_sha256": hashlib.sha256(raster.png).hexdigest(),
                "model_sha256": model_sha256,
                "configuration": config.model_dump(),
                "producer_sha256": code_digest("accuracy"),
                "detector_producer_sha256": code_digest("detection"),
                "runtime": runtime_versions(),
            },
        )
    candidates = evidence.candidates if evidence is not None else []
    row = {
        "page": page.geometry.page,
        "math_cache_key": evidence.cache_key if evidence else input_key,
        "evidence_path": path.relative_to(ROOT).as_posix(),
        "native_glyph_line_candidates": len(glyph_lines),
        "detector_formula_regions": formula_count,
        "candidate_count": len(candidates),
        "source_types": dict(Counter(item.source_type for item in candidates)),
        "presentations": dict(Counter(item.presentation for item in candidates)),
        "basis": dict(Counter(basis for item in candidates for basis in item.basis)),
        "max_confidence": max((item.confidence for item in candidates), default=0),
        "screened_only": evidence is None,
    }
    if candidates:
        cache_key[page.geometry.page] = (raster, candidates)
    return row


def choose_samples(rows, number):
    choices = [row for row in rows if row["candidate_count"]]
    ranked = sorted(
        choices, key=lambda row: (-row["max_confidence"], -row["candidate_count"], row["page"])
    )
    selected = []
    covered = set()
    for row in ranked:
        categories = {
            *(("source", value) for value in row["source_types"]),
            *(("presentation", value) for value in row["presentations"]),
            *(("basis", value) for value in row["basis"]),
        }
        if categories - covered:
            selected.append(row["page"])
            covered.update(categories)
        if len(selected) == number:
            return selected
    for row in ranked:
        if row["page"] not in selected:
            selected.append(row["page"])
        if len(selected) == number:
            break
    return selected


def overlay(raster, candidates, page, target):
    canvas = raster_array(raster).copy()
    colors = {
        "digital": (230, 90, 0),
        "image": (30, 150, 30),
        "mixed": (180, 0, 180),
        "uncertain": (90, 90, 90),
    }
    sx, sy = raster.width / raster.page_width, raster.height / raster.page_height
    for index, item in enumerate(candidates, 1):
        left = round(item.bbox.x0 * sx), round(item.bbox.y0 * sy)
        right = round(item.bbox.x1 * sx), round(item.bbox.y1 * sy)
        color = colors[item.source_type]
        cv2.rectangle(canvas, left, right, color, 2)
        label = f"M{index} {item.source_type}/{item.presentation} {item.confidence:.2f}"
        cv2.putText(
            canvas,
            label,
            (left[0], max(12, left[1] - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.3,
            color,
            1,
            cv2.LINE_AA,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(target), canvas):
        raise OSError("Math overlay could not be written")
    return {
        "page": page,
        "overlay": target.relative_to(ROOT).as_posix(),
        "candidate_ids": [item.id for item in candidates],
        "source_types": dict(Counter(item.source_type for item in candidates)),
        "presentations": dict(Counter(item.presentation for item in candidates)),
    }


def totals(rows):
    output = {}
    for key in ("source_types", "presentations", "basis"):
        counter = Counter()
        for row in rows:
            counter.update(row[key])
        output[key] = dict(counter)
    return {
        **output,
        "pages_screened": len(rows),
        "pages_with_candidates": sum(row["candidate_count"] > 0 for row in rows),
        "candidates": sum(row["candidate_count"] for row in rows),
        "native_glyph_line_candidates": sum(row["native_glyph_line_candidates"] for row in rows),
        "detector_formula_regions": sum(row["detector_formula_regions"] for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", default="science_pdf")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--follow", action="store_true")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()
    args.out = checked_local(args.out)
    if args.samples < 1:
        parser.error("--samples must be positive")
    manifest_path = args.out / "detection_manifest.json"
    phase = json.loads(manifest_path.read_text("utf-8"))
    if phase["source_key"] != args.source_key:
        raise ValueError("Detector and analysis source keys differ")
    source = reference_path(args.source_key)
    before = source.stat()
    if source_digest(source) != phase["source_sha256"]:
        raise ValueError("Science source checksum differs from the detector phase")
    source_sha256 = phase["source_sha256"]
    extractor = PyMuPDFExtractor(device="cpu")
    directory = native_directory(source_sha256, extractor, phase)
    model_sha256 = next(
        row["sha256"] for row in phase["model"]["weights"] if row["file"] == "model.safetensors"
    )
    raw_key = canonical_digest(
        {
            "source_sha256": source_sha256,
            "model": phase["model"],
            "configuration": phase["configuration"],
            "producer_sha256": phase["detector_producer_sha256"],
            "runtime": phase["runtime"],
        }
    )
    config = MathEvidenceConfig()
    input_key = canonical_digest(
        {
            "source_sha256": source_sha256,
            "configuration": config.model_dump(),
            "producer_sha256": code_digest("accuracy"),
            "detector_producer_sha256": code_digest("detection"),
            "model_sha256": model_sha256,
            "model": phase["model"],
            "detector_configuration": phase["configuration"],
            "native_producer_sha256": phase["native_producer_sha256"],
            "runtime": {"analysis": runtime_versions(), "detection": phase["runtime"]},
            "script_sha256": source_digest(Path(__file__)),
        }
    )
    rows = []
    render_candidates = {}
    started = time.perf_counter()
    while True:
        phase = json.loads(manifest_path.read_text("utf-8"))
        if phase["source_sha256"] != source_sha256:
            raise ValueError("Detector manifest changed source during analysis")
        for row in phase["pages"][len(rows) :]:
            page = read_native_page(directory, row, source_sha256)
            detected, raw_path = cached_detection(row, raw_key)
            if (
                detected.source_sha256 != page.source_sha256
                or detected.page != page.geometry.page
                or detected.repo_id != phase["model"]["repo_id"]
                or detected.revision != phase["model"]["revision"]
                or detected.threshold != phase["configuration"]["threshold"]
            ):
                raise ValueError("Detector evidence differs from the recorded source or model")
            raster = cached_raster(
                source,
                extractor,
                source_sha256,
                page.geometry.page,
                phase["configuration"]["render_dpi"],
            )
            needs_native = any(
                region.raw_label.casefold() == "formula"
                and page.geometry.content_bbox.contains_center(region.bbox)
                for region in detected.regions
            ) or any(
                page.geometry.content_bbox.contains_center(line.bbox)
                and has_math_evidence(glyph_evidence(page.store.raw_line_text(line)))
                for line in page.store.lines
            )
            native = cached_objects(source, extractor, page) if needs_native else None
            per_page_key = canonical_digest(
                {
                    "input_key": input_key,
                    "execution_device": "cpu",
                    "page": row["page"],
                    "native_payload_sha256": row["native_payload_sha256"],
                    "detection_sha256": row["detection_sha256"],
                    "render_sha256": hashlib.sha256(raster.png).hexdigest(),
                }
            )
            summary = page_summary(
                page,
                detected,
                raster,
                native,
                model_sha256,
                config,
                render_candidates,
                per_page_key,
            )
            summary["detector_path"] = raw_path.relative_to(ROOT).as_posix()
            rows.append(summary)
            print(
                f"math analysis {page.geometry.page}: {summary['candidate_count']} candidates",
                flush=True,
            )
            atomic_json(
                args.out / "math_summary.json",
                {
                    "status": "started",
                    "source_key": args.source_key,
                    "source_sha256": source_sha256,
                    "input_key": input_key,
                    "execution_device": "cpu",
                    "producer_sha256": code_digest("accuracy"),
                    "detector_producer_sha256": phase["detector_producer_sha256"],
                    "configuration": config.model_dump(),
                    "model": phase["model"],
                    "totals": totals(rows),
                    "pages": rows,
                    "wall_seconds": time.perf_counter() - started,
                },
            )
        if phase["status"] != "started" or not args.follow:
            break
        time.sleep(2)
    if phase["status"] != "completed" or len(rows) != phase.get("page_count"):
        raise ValueError("Whole-book math analysis requires a completed full detector scan")
    overlays = []
    for page in choose_samples(rows, args.samples):
        raster, candidates = render_candidates[page]
        overlays.append(overlay(raster, candidates, page, args.out / f"math_p{page}.png"))
    if len(overlays) != args.samples:
        raise ValueError("Not enough mathematical candidate pages for requested sample overlays")
    # Archive completed derived payloads in the ignored cache, preserving recorded checksums.
    for row in phase["pages"]:
        original = checked_local(ROOT / row["detection_path"])
        cached = CACHE / "math_raw" / raw_key / f"page_{row['page']:06d}.json"
        if original != cached:
            if source_digest(cached) != row["detection_sha256"]:
                raise ValueError("Archived detector checksum differs")
            original.unlink()
            row["detection_path"] = cached.relative_to(ROOT).as_posix()
    atomic_json(manifest_path, phase)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Science source changed during mathematical evidence analysis")
    atomic_json(
        args.out / "math_summary.json",
        {
            "status": "completed",
            "source_key": args.source_key,
            "source_sha256": source_sha256,
            "book_key": canonical_digest(
                {"input": input_key, "pages": [item["math_cache_key"] for item in rows]}
            ),
            "execution_device": "cpu",
            "script_sha256": source_digest(Path(__file__)),
            "producer_sha256": code_digest("accuracy"),
            "detector_producer_sha256": phase["detector_producer_sha256"],
            "configuration": config.model_dump(),
            "model": phase["model"],
            "totals": totals(rows),
            "pages": rows,
            "sample_overlays": overlays,
            "wall_seconds": time.perf_counter() - started,
            "limitations": [
                "Model and Unicode candidates are unvalidated; no math truth metric is claimed.",
                "Prose, units, tables and footnote marks can be false candidates.",
                "Image evidence needs an image object; vector formulas can stay uncertain.",
                "Presentation is weak frame evidence; wraps and mixed baselines stay uncertain.",
                "Nothing converts formulas, calls OCR, copies source text or changes its ledger.",
            ],
        },
    )


if __name__ == "__main__":
    main()
