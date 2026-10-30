"""Step 19 layout-only pass: every page's native, analysis and layout stage, as a book run does
them (same page job, same OCR input, same cache keys), with I1-I7 per page. Optionally compares
each page's layout with the layout of a previous run (another layout key in the same cache).

Every page failure is recorded; the pass never stops at the first. Run from the source tree
whose code is being checked.

usage: layout_only.py BOOK CACHE OUT_JSON [--workers N] [--compare-key OLD_LAYOUT_KEY]
"""

import argparse
import hashlib
import json
import multiprocessing
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

TREE = Path.cwd()
sys.path[:0] = [str(TREE / "experiments"), str(TREE / "backend/src")]


def page(book, cache, number, ocr, compare_key):
    from book_core.book_run import _page_job
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.layout.invariants import check
    from book_core.layout.models import PageLayout
    from book_core.layout.pipeline import analyze_layout, layout_fingerprint
    from book_core.objects.analysis import (
        cached_repetition,
        fingerprints,
        verified_read,
    )
    from book_core.ocr.extractor import OcrExtractor
    from book_core.run_context import source_session
    from reference_paths import reference_path
    from step19_run import BOOKS

    source = reference_path(BOOKS[book])
    result = {"page": number}
    try:
        with source_session(source) as snapshot:
            extractor = PyMuPDFExtractor("cpu")
            if ocr is not None:
                extractor = OcrExtractor(extractor, ocr)
            repetition = cached_repetition(source, extractor, cache)
            _page_job(snapshot, number, cache, repetition, "cpu", ocr)
            layout, analysis = analyze_layout(source, number, extractor, repetition, cache)
            violations = check(layout, analysis)
            result["violations"] = {k: len(v) for k, v in violations.items() if v}
            _, analysis_key = fingerprints(snapshot.digest, extractor, repetition)
            key = layout_fingerprint(analysis_key, extractor.device.resolved)
            result["layout_key"] = key
            new = layout.model_dump_json()
            result["layout_sha256"] = hashlib.sha256(new.encode()).hexdigest()
            if compare_key:
                old_path = Path(cache) / "layout" / compare_key / f"{number}.json"
                old = verified_read(old_path, PageLayout, compare_key).model_dump_json()
                result["old_layout_sha256"] = hashlib.sha256(old.encode()).hexdigest()
                result["identical"] = old == new
    except Exception as error:  # noqa: BLE001 - every page failure is recorded
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()[-3000:]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("book")
    parser.add_argument("cache")
    parser.add_argument("out")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--compare-key")
    args = parser.parse_args()
    import pymupdf
    import step19_run
    from book_core.ocr.prepare import prepare_book
    from reference_paths import reference_path
    from step16_benchmark import make_engines
    from step16_downstream import visual_checks

    source = reference_path(step19_run.BOOKS[args.book])
    cache = Path(args.cache)
    config_path = Path(sys.argv[0]).resolve().parent.parent / "ocr_config_linux.json"
    config = {**json.loads(config_path.read_text("utf-8")), "device": "cpu"}
    settings = step19_run.ocr_settings(config)
    primary, secondary = make_engines(config)
    ocr = prepare_book(source, cache / "o", settings, primary, secondary,
                       visual_checks=visual_checks(source, cache / "o"))  # fmt: skip
    with pymupdf.open(source) as document:
        total = document.page_count
    tick, results = time.perf_counter(), []
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=context) as pool:
        futures = [
            pool.submit(page, args.book, cache, n, ocr, args.compare_key)
            for n in range(1, total + 1)
        ]
        for done, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if "error" in results[-1]:
                print("FAILED", results[-1]["page"], results[-1]["error"][:300], flush=True)
            if done % 100 == 0 or done == total:
                print(args.book, "layout", done, total, flush=True)
    results.sort(key=lambda r: r["page"])
    failed = [r["page"] for r in results if "error" in r]
    totals = {}
    for r in results:
        for k, v in r.get("violations", {}).items():
            totals[k] = totals.get(k, 0) + v
    summary = {
        "book": args.book,
        "source_tree": str(TREE),
        "cache": str(cache),
        "pages": total,
        "failed_pages": failed,
        "invariant_totals": totals,
        "layout_keys": sorted({r["layout_key"] for r in results if "layout_key" in r}),
        "seconds": round(time.perf_counter() - tick),
    }
    if args.compare_key:
        summary["compare_key"] = args.compare_key
        summary["changed_pages"] = [r["page"] for r in results if r.get("identical") is False]
        summary["all_identical"] = not failed and not summary["changed_pages"]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"summary": summary, "pages": results}, indent=1))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
