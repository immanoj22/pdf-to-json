"""Step 6b science-book math evidence; native extraction and pixels use Extractor only."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from reference_paths import reference_path

from book_core.caching import code_digest, runtime_versions
from book_core.detection.cache import detect_cached
from book_core.detection.models import DetectionInput
from book_core.detection.transformers import HeronDetector
from book_core.extraction.cache import CachedExtractor, atomic_json, payload_digest
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments/out/step6b/math"
WEIGHTS = ROOT / ".cache/huggingface"
CACHE = ROOT / ".cache/step6b"


def weight_identity(detector):
    snapshot = (
        WEIGHTS
        / ("models--" + detector.repo_id.replace("/", "--"))
        / "snapshots"
        / detector.revision
    )
    records = []
    for path in sorted(snapshot.glob("*")):
        if path.is_file():
            records.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": source_digest(path)}
            )
    if not any(row["file"] == "model.safetensors" for row in records):
        raise ValueError("Audited local Heron model weights are unavailable")
    return records


def run_detection(args):
    source = reference_path(args.source_key)
    before = source.stat()
    digest = source_digest(source)
    native = PyMuPDFExtractor(device="cpu")
    extractor = CachedExtractor(native, CACHE / "science_native")
    detector = HeronDetector(
        device=args.device,
        threshold=args.threshold,
        cache_dir=WEIGHTS,
        local_files_only=True,
    )
    weights = weight_identity(detector)
    started = time.perf_counter()
    manifest = {
        "stage": "detector_only",
        "status": "started",
        "source_key": args.source_key,
        "source_sha256": digest,
        "script_sha256": source_digest(Path(__file__)),
        "native_producer_sha256": code_digest("extraction"),
        "detector_producer_sha256": code_digest("detection"),
        "runtime": runtime_versions(),
        "model": {
            "repo_id": detector.repo_id,
            "revision": detector.revision,
            "weights": weights,
            "code_license": "Apache-2.0",
            "weight_license": "Apache-2.0",
            "license_source": (
                "https://huggingface.co/docling-project/docling-layout-heron/blob/"
                + detector.revision
                + "/README.md"
            ),
        },
        "configuration": {
            "threshold": args.threshold,
            "render_dpi": args.dpi,
            "requested_device": args.device,
            "max_pages": args.max_pages,
        },
        "pages": [],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    atomic_json(args.out / "detection_manifest.json", manifest)
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        raster = native.render_page(source, number, dpi=args.dpi)
        result = detect_cached(
            DetectionInput.from_raster(digest, number, raster), detector, CACHE / "math_models"
        )
        path = args.out / "detections" / f"page_{number:06d}.json"
        atomic_json(path, result.model_dump(mode="json"))
        formula = [row for row in result.regions if row.raw_label.casefold() == "formula"]
        manifest["pages"].append(
            {
                "page": number,
                "native_payload_sha256": payload_digest(page.model_dump(mode="json")),
                "detection_sha256": source_digest(path),
                "detection_path": path.relative_to(ROOT).as_posix(),
                "formula_regions": len(formula),
                "device": result.device.model_dump(),
            }
        )
        manifest["wall_seconds"] = time.perf_counter() - started
        atomic_json(args.out / "detection_manifest.json", manifest)
        print(f"math detection {number}: {len(formula)} formula candidates", flush=True)
        if args.max_pages is not None and number >= args.max_pages:
            break
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Science source changed during detection")
    manifest["status"] = "completed" if args.max_pages is None else "partial_probe"
    manifest["native_cache_hits"] = extractor.cache_hits
    manifest["native_cache_misses"] = extractor.cache_misses
    manifest["page_count"] = len(manifest["pages"])
    manifest["wall_seconds"] = time.perf_counter() - started
    atomic_json(args.out / "detection_manifest.json", manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", default="science_pdf")
    parser.add_argument("--device", choices=["cpu", "auto", "cuda"], default="cpu")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--dpi", type=int, default=72)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--detect-only", action="store_true")
    args = parser.parse_args()
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be positive")
    if args.dpi < 1:
        parser.error("--dpi must be positive")
    if not args.detect_only:
        parser.error("Evidence analysis phase is not configured yet; use --detect-only")
    run_detection(args)


if __name__ == "__main__":
    main()
