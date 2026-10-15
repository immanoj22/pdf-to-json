"""Step 13b development bundles: the equations stage inputs of every page in one file each.

Rules are iterated on the math book many times; reading text pages, layout, units, native
objects, figures and cached layout-model formula boxes from the development caches dominates
a run. This writes one compressed pickle per page (git-ignored ``.cache/step13b/bundles``)
plus the book evidence of pass 1 (accepted glyph shapes, book text size), so ``detect_page``
and the ownership pass can be re-run on any page set in seconds. Development only: the
final records come from ``book_run``.

Usage: python step13b_bundles.py --book statistics --run final
"""

# ruff: noqa: E402
import argparse
import gzip
import pickle
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step11_run import CACHE11
from step13_equations import DEV, formulas, stage_inputs

from book_core.equations import detect, glyphs
from book_core.equations.cache import text_size
from book_core.equations.fonts import FontEvidence
from book_core.figures.cache import load_page as figure_page
from book_core.lists.cache import BookListsResult
from book_core.lists.cache import load_page as list_page
from book_core.objects.analysis import verified_read
from book_core.run_context import open_source, source_session

BUNDLES = ROOT / ".cache/step13b/bundles"


def build(book, run):
    inputs = stage_inputs(book, run)
    keys = inputs["keys"]
    target = BUNDLES / book
    target.mkdir(parents=True, exist_ok=True)
    detector = formulas(inputs["source"], inputs["extractor"])
    lists = verified_read(
        CACHE11 / "lists/book" / f"{keys['lists']}.json", BookListsResult, keys["lists"]
    )
    sizes = {}
    shapes, joined, shape_pages = Counter(), Counter(), defaultdict(set)
    with source_session(inputs["source"]), open_source(inputs["source"]) as document:
        fonts = FontEvidence(document)
        for page in inputs["pages"]():
            number = page.geometry.page
            sizes[number] = text_size(page)
            bundle = {
                "page": page,
                "layout": inputs["layout_of"](page),
                "units": inputs["units_of"](number),
                "order": list_page(lists, number, CACHE11).order,
                "native": inputs["native_of"](number),
                "figures": figure_page(DEV, keys["figures"], number),
                "model_boxes": detector(number),
                "math_fonts": fonts.math_fonts(number),
            }
            with gzip.open(target / f"{number}.pkl.gz", "wb", compresslevel=3) as stream:
                pickle.dump(bundle, stream, protocol=pickle.HIGHEST_PROTOCOL)
            if number % 50 == 0:
                print(book, number, flush=True)
    known = [s for s in sizes.values() if s]
    book_size = statistics.median(known) if known else 10.0
    for number in sorted(sizes):
        bundle = load(book, number)
        lines = [ln for ln in bundle["layout"].lines if ln.inside_content and not ln.blank]
        boxes = [bundle["page"].store.spans[sid].bbox for ln in lines for sid in ln.span_ids]
        found, _, signatures = glyphs.page_glyphs(bundle["native"], book_size, boxes)
        shapes.update(signatures.values())
        for signature in signatures.values():
            shape_pages[signature].add(number)
        for group in detect.glyph_groups(found, book_size, boxes):
            joined.update(signatures[i.id] for i in detect.beside_others(group, signatures))
    book_evidence = {
        "book_size": book_size,
        "accepted": glyphs.accepted(shapes, joined, shape_pages),
        "pages": len(sizes),
        "keys": keys,
    }
    with gzip.open(target / "book.pkl.gz", "wb") as stream:
        pickle.dump(book_evidence, stream)
    print(book, "bundles", len(sizes), "accepted shapes", len(book_evidence["accepted"]))


def add_order(book, run):
    """Add the page reading order to bundles written before it was bundled."""
    keys = stage_inputs(book, run)["keys"]
    lists = verified_read(
        CACHE11 / "lists/book" / f"{keys['lists']}.json", BookListsResult, keys["lists"]
    )
    for path in sorted((BUNDLES / book).glob("[0-9]*.pkl.gz")):
        number = int(path.name.split(".")[0])
        bundle = load(book, number)
        if "order" in bundle:
            continue
        bundle["order"] = list_page(lists, number, CACHE11).order
        with gzip.open(path, "wb", compresslevel=3) as stream:
            pickle.dump(bundle, stream, protocol=pickle.HIGHEST_PROTOCOL)


def load(book, number):
    with gzip.open(BUNDLES / book / f"{number}.pkl.gz", "rb") as stream:
        return pickle.load(stream)


def book_evidence(book):
    with gzip.open(BUNDLES / book / "book.pkl.gz", "rb") as stream:
        return pickle.load(stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--run", default="final")
    parser.add_argument("--add-order", action="store_true")
    args = parser.parse_args()
    if args.add_order:
        add_order(args.book, args.run)
    else:
        build(args.book, args.run)
