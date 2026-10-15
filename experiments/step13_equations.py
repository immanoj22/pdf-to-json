"""Step 13a development harness: the equations stage on a finished run's caches.

Reads the run's cache keys (performance record), loads text pages, layout, final units,
native objects and character evidence from the development caches, and runs
``analyze_book_equations`` into ``.cache/step13/equations`` with cached layout-model formula
evidence. Writes a per-book summary. Used while developing rules; the final run goes
through ``book_run``.

Usage: python step13_equations.py --book statistics --run before
       (--run names experiments/out/step13/<run>/performance/<book>.json, or ``step12`` for
       the Step 12 final run of books 1-4)
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
from step7_layouts import CACHE
from step11_run import CACHE11
from step13_books import BOOKS

from book_core.book_run import CachedTextPages
from book_core.characters.cache import load_page as character_page
from book_core.equations.cache import analyze_book_equations
from book_core.equations.evidence import DetectorFormulas
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.layout.models import PageLayout
from book_core.lists.cache import BookListsResult
from book_core.lists.cache import load_page as list_page
from book_core.objects.analysis import verified_read
from book_core.objects.models import NativeObjectPage
from book_core.run_context import source_session

OUT = ROOT / "experiments/out/step13"
DEV = CACHE  # the development page cache: the final run reuses these records


def performance(book, run):
    path = (
        ROOT / f"experiments/out/step12/final/performance/{book}.json"
        if run == "step12"
        else OUT / run / f"performance/{book}.json"
    )
    return json.loads(path.read_text("utf-8"))["run"]


def stage_inputs(book, run):
    record = performance(book, run)
    keys = record["cache_keys"]
    source = reference_path(BOOKS[book][0])
    extractor = PyMuPDFExtractor("cpu")
    total = record["pages"]
    lists = verified_read(
        CACHE11 / "lists/book" / f"{keys['lists']}.json", BookListsResult, keys["lists"]
    )
    text = CachedTextPages(extractor, CACHE, keys["native"], total, None)

    def pages():
        for number in range(1, total + 1):
            from book_core.cache_store import read_model
            from book_core.model.spans import ExtractedPage

            yield read_model(
                CACHE / "text" / keys["native"] / f"{number}.json", ExtractedPage, keys["native"]
            )

    def layout_of(page):
        number = page.geometry.page
        return verified_read(
            CACHE / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
        )

    def native_of(number):
        return verified_read(
            CACHE / "native" / keys["native"] / f"{number}.json", NativeObjectPage, keys["native"]
        )

    return {
        "source": source,
        "extractor": extractor,
        "total": total,
        "keys": keys,
        "pages": pages,
        "layout_of": layout_of,
        "units_of": lambda number: list_page(lists, number, CACHE11).units,
        "native_of": native_of,
        "characters_of": lambda number: character_page(CACHE, keys["characters"], number),
        "text": text,
    }


def formulas(source, extractor):
    import step12_detect

    return DetectorFormulas(source, extractor, step12_detect.detectors(), ROOT / ".cache/models")


def run(book, run_name, models=True, cache=DEV):
    inputs = stage_inputs(book, run_name)
    started = time.perf_counter()
    with source_session(inputs["source"]):
        key, summary = analyze_book_equations(
            inputs["source"],
            inputs["pages"],
            inputs["layout_of"],
            inputs["units_of"],
            inputs["native_of"],
            inputs["characters_of"],
            {k: inputs["keys"][k] for k in ("lists", "characters", "native")},
            cache,
            inputs["total"],
            formulas(inputs["source"], inputs["extractor"]) if models else None,
        )
    row = {
        "book": book,
        "run": run_name,
        "key": key,
        "seconds": round(time.perf_counter() - started, 1),
        "summary": summary.model_dump(mode="json", exclude={"font_evidence", "config"}),
    }
    target = OUT / "equations_dev" / f"{book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(row, indent=1) + "\n", "utf-8")
    print(json.dumps(row, indent=1))
    return key


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=BOOKS)
    parser.add_argument("--run", default="step12")
    parser.add_argument("--no-models", action="store_true")
    args = parser.parse_args()
    run(args.book, args.run, models=not args.no_models)
