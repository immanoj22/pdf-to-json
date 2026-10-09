"""Step 7: precompute cached Step 4 layouts for every page of one approved book.

Layouts are unchanged Step 4 outputs (own geometry, no learned detector); they are cached under
``.cache/step7`` with the usual source/configuration/producer fingerprints. Hold-out books are
refused unless ``--holdout`` is passed (they run once, after the reading-order stage is frozen).

Usage: python step7_layouts.py --book spanish_us_history [--workers 4] [--holdout]
"""

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402

CACHE = ROOT / ".cache/step7"
OUT = ROOT / "experiments/out/step7"
BOOKS = {
    "spanish_us_history": ("spanish_pdf", "development"),
    "immigrant_children": ("small_pdf", "holdout"),
    "art_therapy_index": ("art_index_pdf", "holdout"),
}


def _pages(source):
    import pymupdf

    with pymupdf.open(source) as document:
        return document.page_count


def _run(source, pages):
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.layout.pipeline import analyze_layout
    from book_core.objects.analysis import cached_repetition

    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE)
    done = []
    for page in pages:
        started = time.perf_counter()
        layout, _ = analyze_layout(source, page, extractor, repetition, CACHE)
        done.append((page, len(layout.lines), round(time.perf_counter() - started, 2)))
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(BOOKS))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    key, split = BOOKS[args.book]
    if split == "holdout" and not args.holdout:
        raise SystemExit("Hold-out book: pass --holdout (runs once, after freezing)")
    source = reference_path(key)
    total = _pages(source)
    # Warm the book-level repetition cache once before workers start.
    _run(source, [])
    chunks = [list(range(start, total + 1, args.workers)) for start in range(1, args.workers + 1)]
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f"layouts_{args.book}.jsonl"
    started = time.perf_counter()
    with ProcessPoolExecutor(args.workers) as pool, log.open("a", encoding="utf-8") as handle:
        futures = [pool.submit(_run, source, chunk) for chunk in chunks if chunk]
        for future in as_completed(futures):
            for page, lines, seconds in future.result():
                handle.write(json.dumps({"page": page, "lines": lines, "seconds": seconds}) + "\n")
    print(f"{args.book}: {total} pages in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
