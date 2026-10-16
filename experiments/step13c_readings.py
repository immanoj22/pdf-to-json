"""Step 13c development: image-path readings of every equation region of a book.

Fills the per-image formula reading cache (``.cache/models/formula_readings``) with the
production renderer and recognizer, so the final ``book_run`` reads them back; the stage
itself computes the same images and keys. Development only (resumable; cached images are
skipped).

Usage: python step13c_readings.py --book statistics [--dpi 300] [--limit N] [--pages 1-50]
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
from step13_books import BOOKS

from book_core.cache_store import read_model
from book_core.equations.models import PageEquations
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
from book_core.mathml.images import RegionImages, region_direction, region_marks
from book_core.mathml.recognition import PPFormulaNet, RecognitionCache
from book_core.mathml.symbols import TextSymbols
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.objects.models import NativeObjectPage
from book_core.run_context import source_session

OUT = ROOT / "experiments/out/step13c"
FINAL13B = ROOT / "experiments/out/step13b/final/performance"


def keys_of(book):
    path = FINAL13B / f"{book}.json"
    if path.exists():
        return json.loads(path.read_text("utf-8"))["run"]["cache_keys"]
    after = ROOT / f"experiments/out/step13b/final/after/{book}.json"
    return json.loads(after.read_text("utf-8"))["cache_keys"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pages")
    args = parser.parse_args()
    keys = keys_of(args.book)
    source = reference_path(BOOKS[args.book][0])
    extractor = PyMuPDFExtractor("cpu")
    reader = RecognitionCache(
        PPFormulaNet(device="auto", cache_dir=ROOT / ".cache/huggingface"),
        ROOT / ".cache/models",
    )
    first, last = 1, None
    if args.pages:
        first, last = (int(p) for p in args.pages.split("-"))
    done = fresh = 0
    started = time.perf_counter()
    with source_session(source):
        images = RegionImages(extractor, source, args.dpi)
        number = first
        while True:
            path = CACHE / "equations" / keys["equations"] / f"{number}.json"
            if not path.exists() or (last and number > last):
                break
            record = read_model(path, PageEquations, keys["equations"])
            if record.regions:
                page = read_model(
                    CACHE / "text" / keys["native"] / f"{number}.json",
                    ExtractedPage,
                    keys["native"],
                )
                native = verified_read(
                    CACHE / "native" / keys["native"] / f"{number}.json",
                    NativeObjectPage,
                    keys["native"],
                )
                objects = {o.id: o for o in native.objects}
                text = TextSymbols(page, native)
                size = book_size(args.book, keys)
                for region in record.regions:
                    box = (
                        region.bbox.x0,
                        region.bbox.y0,
                        region.bbox.x1,
                        region.bbox.y1,
                    )
                    png = images.crop(
                        number,
                        box,
                        region_marks(region, objects, text),
                        size,
                        region_direction(region, text),
                    )
                    result = reader.read(png)
                    done += 1
                    fresh += not result["cached"]
                    if args.limit and done >= args.limit:
                        break
            if args.limit and done >= args.limit:
                break
            if number % 10 == 0:
                rate = (time.perf_counter() - started) / max(1, fresh)
                print(
                    args.book,
                    "page",
                    number,
                    "regions",
                    done,
                    "new",
                    fresh,
                    f"{rate:.1f}s",
                    flush=True,
                )
            number += 1
    print(
        args.book,
        "done",
        done,
        "new",
        fresh,
        round(time.perf_counter() - started),
        flush=True,
    )


_SIZES = {}


def book_size(book, keys):
    """The equations stage's book text size: the median of the pages' median span sizes."""
    if book not in _SIZES:
        import statistics

        from book_core.equations.cache import text_size

        sizes, number = [], 1
        while (path := CACHE / "text" / keys["native"] / f"{number}.json").exists():
            size = text_size(read_model(path, ExtractedPage, keys["native"]))
            if size:
                sizes.append(size)
            number += 1
        _SIZES[book] = statistics.median(sizes) if sizes else 10.0
        print(book, "book text size", _SIZES[book], flush=True)
    return _SIZES[book]


if __name__ == "__main__":
    main()
