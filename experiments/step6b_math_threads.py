"""Read-only per-page Heron CPU thread diagnostic, independent of the active scan."""

import argparse
import os
import statistics
import time
from pathlib import Path

from reference_paths import reference_path

from book_core.detection.models import DetectionInput
from book_core.detection.transformers import HeronDetector
from book_core.extraction.cache import atomic_json
from book_core.extraction.fingerprints import source_digest
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

ROOT = Path(__file__).resolve().parents[1]


def main():
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=int, required=True)
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 4, 8])
    args = parser.parse_args()
    source = reference_path("science_pdf")
    extractor = PyMuPDFExtractor(device="cpu")
    raster = extractor.render_page(source, args.page, dpi=72)
    page = DetectionInput.from_raster(source_digest(source), args.page, raster)
    detector = HeronDetector(
        device="cpu", cache_dir=ROOT / ".cache/huggingface", local_files_only=True
    )
    original_threads = torch.get_num_threads()
    rows = []
    for threads in args.threads:
        torch.set_num_threads(threads)
        detector.detect(page)
        timings = []
        results = []
        for _ in range(2):
            started = time.perf_counter()
            result = detector.detect(page)
            timings.append(time.perf_counter() - started)
            results.append(
                {
                    "labels": [item.raw_label for item in result.regions],
                    "scores": [item.confidence for item in result.regions],
                    "boxes": [item.bbox.model_dump() for item in result.regions],
                }
            )
        row = {
            "threads": threads,
            "seconds": timings,
            "median_seconds": statistics.median(timings),
            "results": results,
        }
        rows.append(row)
        print(f"threads={threads}, median={row['median_seconds']:.3f}s", flush=True)
    atomic_json(
        ROOT / "experiments/out/step6b/math_threads.json",
        {
            "source_sha256": page.source_sha256,
            "page": args.page,
            "original_threads": original_threads,
            "cpu_count": os.cpu_count(),
            "rows": rows,
            "caveat": "Concurrent with the full CPU scan; timings are contended diagnostics.",
        },
    )


if __name__ == "__main__":
    main()
