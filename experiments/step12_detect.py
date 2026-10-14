"""Step 12: cache Heron and PP-DocLayoutV3 region evidence for every page of one book.

Uses the unchanged Step 4b adapters and cache (``.cache/models/detections``) at the Phase 0
render (72 dpi, 0.5 threshold) on CPU. Evidence only; nothing in the pipeline reads it.

Usage: python step12_detect.py --book spanish_us_history [--pages 1-5 | --figure-pages]

``--figure-pages`` runs the pages that hold one of our figures or a reference image
(``detection/pages.json``); timing is recorded per model and split by our-figure pages.
"""

# ruff: noqa: E402
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import BOOKS

from book_core.detection.cache import detect_page
from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

CACHE = ROOT / ".cache/models"
OUT = ROOT / "experiments/out/step12/detection"
MODELS = ROOT / ".cache/huggingface"


def detectors():
    return [
        HeronDetector(device="cpu", cache_dir=MODELS, local_files_only=True),
        PPDocLayoutV3Detector(device="cpu", cache_dir=MODELS, local_files_only=True),
    ]


def run(book, pages=None):
    source = reference_path(BOOKS[book][0])
    extractor = PyMuPDFExtractor("cpu")
    total = extractor.page_count(source)
    numbers = pages or range(1, total + 1)
    seconds = {}
    for detector in detectors():
        started = time.perf_counter()
        for number in numbers:
            detect_page(source, number, extractor, detector, CACHE)
            if number % 50 == 0:
                print(book, detector.name, number, flush=True)
        seconds[detector.name] = round(time.perf_counter() - started, 1)
    row = {"book": book, "pages": len(list(numbers)), "seconds": seconds}
    OUT.mkdir(parents=True, exist_ok=True)
    if pages is None or not isinstance(pages, range):
        (OUT / f"timing_{book}.json").write_text(json.dumps(row, indent=1) + "\n", "utf-8")
    print(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--pages")
    parser.add_argument("--figure-pages", action="store_true")
    args = parser.parse_args()
    span = None
    if args.figure_pages:
        span = json.loads((OUT / "pages.json").read_text("utf-8"))[args.book]
    if args.pages:
        first, last = (int(v) for v in args.pages.split("-"))
        span = range(first, last + 1)
    run(args.book, span)
