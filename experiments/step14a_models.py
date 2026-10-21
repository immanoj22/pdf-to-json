"""Step 14a: page-level table detections from the learned detectors, for every page.

TATR detection (new, cached under .cache/models/detections) and the Heron / PP-DocLayoutV3
detections cached by Steps 12-13 (read from the same cache; a page without a cached
result is run). Writes experiments/out/step14a/models/<book>.json:
{page: {model: [[x0, y0, x1, y1, score, raw label], ...]}} for table labels only, plus
timing. Detections are evidence only.

Usage: python step14a_models.py --book NAME [--dpi 100]
"""

# ruff: noqa: E402
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

from book_core.detection.cache import detect_page
from book_core.detection.transformers import HeronDetector, PPDocLayoutV3Detector
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.run_context import source_session
from book_core.tables.recognizers import TATRDetector

TATR_DPI = 100
MODELS = ROOT / ".cache/huggingface"
DETECTIONS = ROOT / ".cache/models"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=common.BOOK_ORDER)
    args = parser.parse_args()
    book = args.book
    detectors = {
        "heron": HeronDetector(device="cpu", cache_dir=MODELS),
        "pp": PPDocLayoutV3Detector(device="cpu", cache_dir=MODELS),
        "tatr": TATRDetector(device="cpu", cache_dir=MODELS),
    }
    target = common.OUT / "models" / f"{book}.json"
    result = common.read(target) if target.exists() else {"pages": {}, "seconds": {}}
    started = time.perf_counter()
    seconds = {name: 0.0 for name in detectors}
    with source_session(common.source(book)) as snapshot:
        extractor = PyMuPDFExtractor("cpu")
        for number in range(1, common.pages(book) + 1):
            row = {}
            for name, detector in detectors.items():
                begun = time.perf_counter()
                found = detect_page(
                    snapshot.path,
                    number,
                    extractor,
                    detector,
                    DETECTIONS,
                    **({"dpi": TATR_DPI} if name == "tatr" else {}),
                )
                seconds[name] += time.perf_counter() - begun
                row[name] = [
                    [
                        r.bbox.x0,
                        r.bbox.y0,
                        r.bbox.x1,
                        r.bbox.y1,
                        round(r.confidence, 4),
                        r.raw_label,
                    ]
                    for r in found.regions
                    if r.raw_label.lower().startswith("table")
                ]
            result["pages"][str(number)] = row
            if number % 50 == 0:
                print(book, number, {k: round(v) for k, v in seconds.items()}, flush=True)
    result["seconds"] = {k: round(v, 1) for k, v in seconds.items()}
    result["total_seconds"] = round(time.perf_counter() - started, 1)
    result["identity"] = {
        name: {"repo": d.repo_id, "revision": d.revision, "threshold": d.threshold}
        for name, d in detectors.items()
    }
    result["tatr_dpi"] = TATR_DPI
    common.write(target, result)
    print(book, "done", result["seconds"], flush=True)


if __name__ == "__main__":
    main()
