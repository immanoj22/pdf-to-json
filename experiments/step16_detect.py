"""Read-only OCR screen of the five authorized Step 15 books.

Native evidence and figure records are checksum-verified reads of their Step 15 keys.
No pipeline stage, reference, archive or ledger is rewritten; no OCR reader runs here.
Valid Unicode is not asserted to match a render: unmeasured checks stay explicit.
"""

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_core.cache_store import read_model
from book_core.figures.cache import load_page as figure_page
from book_core.objects.models import NativeObjectPage
from book_core.ocr import detection
from book_core.ocr.detection import RenderTextCheck, detect_ocr_regions
from book_core.run_context import source_session
from reference_paths import reference_path
from step7_layouts import CACHE
from step13_books import BOOKS

DETECTOR_SHA256 = hashlib.sha256(Path(detection.__file__).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8", newline="\n"
    )


def run(book, capture, output, adjudications):
    started = time.perf_counter()
    record = json.loads((capture / "performance" / f"{book}.json").read_text("utf-8"))[
        "run"
    ]
    keys = record["cache_keys"]
    decisions = Counter()
    pages, totals = [], Counter()
    with source_session(reference_path(BOOKS[book][0])) as snapshot:
        for number in range(1, record["pages"] + 1):
            native = read_model(
                CACHE / "native" / keys["native"] / f"{number}.json",
                NativeObjectPage,
                keys["native"],
            )
            if (
                native.page.source_sha256 != snapshot.digest
                or native.page.geometry.page != number
            ):
                raise ValueError(
                    "Step 15 native cache does not match the configured source"
                )
            figures = figure_page(CACHE, keys["figures"], number)
            if figures.source_sha256 != snapshot.digest or figures.page != number:
                raise ValueError(
                    "Step 15 figure cache does not match the configured source"
                )
            checks = [
                RenderTextCheck.model_validate(row)
                for row in adjudications.get(book, {}).get(str(number), [])
            ]
            result = detect_ocr_regions(
                native,
                figure_boxes=[f.bbox for f in figures.figures],
                render_checks=checks,
            )
            write(
                output / "pages" / book / f"{number:06d}.json",
                result.model_dump(mode="json"),
            )
            decisions[result.decision] += 1
            for field in (
                "native_characters",
                "unusable_characters",
                "invisible_glyphs",
                "missing_unicode_glyphs",
            ):
                totals[field] += getattr(result, field)
            pages.append(
                {
                    "page": number,
                    "decision": result.decision,
                    "native_characters": result.native_characters,
                    "unusable_characters": result.unusable_characters,
                    "invisible_glyphs": result.invisible_glyphs,
                    "raster_coverage": result.raster_coverage,
                    "excluded_figure_images": len(result.excluded_figure_image_ids),
                    "reasons": [r for region in result.regions for r in region.reasons],
                    "unmeasured_checks": result.unmeasured_checks,
                }
            )
            if number % 100 == 0:
                print(f"{book}: {number}/{record['pages']}", flush=True)
    report = {
        "book": book,
        "pages": record["pages"],
        "source_sha256": snapshot.digest,
        "native_key": keys["native"],
        "figure_key": keys["figures"],
        "detector_version": detection.VERSION,
        "detector_sha256": DETECTOR_SHA256,
        "large_raster_share": 0.70,
        "decisions": dict(decisions),
        "counts": dict(totals),
        "ocr_pages": [p["page"] for p in pages if p["decision"] == "ocr"],
        "compare_only_pages": [
            p["page"] for p in pages if p["decision"] == "compare_only"
        ],
        "review_pages": [p["page"] for p in pages if p["decision"] == "review"],
        "unusable_unicode_pages": [
            p["page"] for p in pages if p["unusable_characters"]
        ],
        "unmeasured_render_comparison_pages": [
            p["page"] for p in pages if p["unmeasured_checks"]
        ],
        "native_inputs_loaded": record["pages"],
        "source_extractions": 0,
        "ocr_readers_invoked": 0,
        "native_modified": False,
        "wall_seconds": round(time.perf_counter() - started, 3),
        "page_results": pages,
    }
    if (
        hashlib.sha256(Path(detection.__file__).read_bytes()).hexdigest()
        != DETECTOR_SHA256
    ):
        raise ValueError("Detector changed during measurement; do not accept this run")
    write(output / f"{book}.json", report)
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("book", "pages", "decisions", "counts", "wall_seconds")
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=tuple(BOOKS), nargs="+", default=list(BOOKS))
    parser.add_argument(
        "--capture", type=Path, default=ROOT / "experiments/out/step15/final"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "experiments/out/step16/detection"
    )
    parser.add_argument("--adjudications", type=Path)
    args = parser.parse_args()
    adjudications = (
        json.loads(args.adjudications.read_text("utf-8")) if args.adjudications else {}
    )
    for book in args.book:
        run(book, args.capture, args.out, adjudications)


if __name__ == "__main__":
    main()
