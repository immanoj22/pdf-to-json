"""Step 19: rebuild the Step 7/8 inputs of ``tests/test_furniture_books.py`` with the current
code, into a separate folder (default ``.cache/s19/furniture``), never over the archived
Step 7/8 caches or evidence.

Writes ``<root>/step7`` (object repetition, page layouts, the casefolded vocabulary
``step7_vocabulary*.json`` as experiments/step7_run.py names it) and ``<root>/step8`` (page
label metadata and the book furniture decision, as experiments/step8_run.py computes it).
No evaluation output is written. The tests read the folder from
``BOOK_CONVERTER_FURNITURE_CACHE``.

Usage: python step19_furniture_caches.py --book spanish_us_history [--workers 2]
"""

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

BOOKS = {"spanish_us_history": "spanish_pdf", "immigrant_children": "small_pdf"}


def vocabulary_name(book):
    return (
        "step7_vocabulary.json" if book == "spanish_us_history" else f"step7_vocabulary_{book}.json"
    )


def _vocabulary(source, pages, step7):
    """Casefolded Step 6 vocabulary counts for some pages (per-page counts add up exactly)."""
    from book_core.document_analysis.vocabulary import build_vocabulary
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.layout.pipeline import analyze_layout
    from book_core.objects.analysis import cached_repetition

    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, step7)
    counts = Counter()
    for page in pages:
        native = analyze_layout(source, page, extractor, repetition, step7)[1].native.page
        counts.update(build_vocabulary([native])["casefold_frequencies"])
    return counts


def main():
    import pymupdf
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import analyze_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition
    from reference_paths import reference_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True, choices=BOOKS)
    parser.add_argument("--root", type=Path, default=ROOT / ".cache/s19/furniture")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    step7, step8 = args.root / "step7", args.root / "step8"
    step7.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source = reference_path(BOOKS[args.book])
    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, step7)
    with pymupdf.open(source) as document:
        total = document.page_count
    target = step7 / vocabulary_name(args.book)
    if target.exists():
        vocabulary = json.loads(target.read_text("utf-8"))
    else:
        chunks = [list(range(s, total + 1, args.workers)) for s in range(1, args.workers + 1)]
        with ProcessPoolExecutor(args.workers) as pool:
            parts = pool.map(_vocabulary, [source] * len(chunks), chunks, [step7] * len(chunks))
            vocabulary = dict(sum(parts, Counter()))
        target.write_text(json.dumps(vocabulary, ensure_ascii=False), "utf-8")
    print(f"{args.book} vocabulary {len(vocabulary)} forms "
          f"{time.perf_counter() - started:.0f}s", flush=True)  # fmt: skip
    inputs = PageInputs(source, extractor, repetition, step7, vocabulary)
    metadata = cached_metadata(source, extractor, step8 / "metadata")
    _, key, hit = analyze_book_furniture(extractor.extract_pages(source), inputs, metadata, step8)
    print(f"{args.book} furniture decision {key[:16]} (cache hit {hit}) "
          f"{time.perf_counter() - started:.0f}s", flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
