"""Run the optional independent visual OCR-eligibility screen on an explicit page."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_core.cache_store import read_model
from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.objects.models import NativeObjectPage
from book_core.ocr.detection import detect_ocr_regions
from book_core.ocr.engines import PpOcrV5Engine
from book_core.ocr.visual_checks import LearnedVisualTextChecks
from book_core.run_context import source_session
from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=tuple(BOOKS), required=True)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "experiments/out/step16/detection/visual"
    )
    args = parser.parse_args()
    record = json.loads(
        (
            ROOT / "experiments/out/step15/final/performance" / f"{args.book}.json"
        ).read_text("utf-8")
    )["run"]
    key = record["cache_keys"]["native"]
    native = read_model(
        CACHE / "native" / key / f"{args.page}.json", NativeObjectPage, key
    )
    manifest = json.loads(
        (ROOT / "experiments/out/step16/dependencies/ppocr_manifest.json").read_text(
            "utf-8"
        )
    )
    spec = next(m for m in manifest["models"] if "server_det" in m["id"])
    text_detector = PpOcrV5Engine(ROOT / spec["local_directory"], spec["revision"], ())
    extractor = PyMuPDFExtractor("auto")
    detectors = [
        kind(cache_dir=ROOT / ".cache/huggingface", local_files_only=True)
        for kind in (HeronDetector, PPDocLayoutV3Detector)
    ]
    source = reference_path(BOOKS[args.book][0])
    callback = LearnedVisualTextChecks(
        source, extractor, detectors, text_detector, CACHE, args.out / "evidence"
    )
    with source_session(source):
        raster = extractor.render_page(source, args.page, 300)
        screen = detect_ocr_regions(native)
        checks = callback(native, raster, screen)
        final = detect_ocr_regions(native, render_checks=checks)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.book}_{args.page}.json"
    path.write_text(final.model_dump_json(indent=2), "utf-8", newline="\n")
    print(
        json.dumps(
            {
                "book": args.book,
                "page": args.page,
                "checks": len(checks),
                "decision": final.decision,
                "output": str(path),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
