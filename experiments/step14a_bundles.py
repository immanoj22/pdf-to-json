"""Step 14a development bundles: the table stage's page evidence for every page of a book.

Each page's ``PageEvidence`` (without model boxes, which are attached at scoring time) and
its token owners ``[(line id, span ids)]`` per retained token ordinal are pickled into the
git-ignored ``.cache/step14a/bundles/<book>.pkl.gz``, so detection and structure rules can
be scored on whole books in minutes (``step14a_dev.py``). Built from the current caches.

Usage: python step14a_bundles.py --book NAME
"""

# ruff: noqa: E402
import argparse
import gzip
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
from step7_layouts import CACHE

from book_core.equations.ownership import final_figures
from book_core.ledger.tokenization import line_tokens
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.tables.evidence import page_evidence

BUNDLES = ROOT / ".cache/step14a/bundles"


def token_owners(page, layout):
    span_line = {sid: line.id for line in layout.lines for sid in line.span_ids}
    owners = []
    for line in page.store.lines:
        raw = page.store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        for token in line_tokens(page.store, line):
            vl = next((span_line[s] for s in token.span_ids if s in span_line), None)
            owners.append((vl, token.span_ids))
    return owners


def build(book, only=None, suffix=""):
    keys = common.keys(book)
    started = time.perf_counter()
    pages = {}
    for number in range(1, common.pages(book) + 1):
        page = common.text_page(book, number)
        layout = common.layout_page(book, number)
        analysis = verified_read(
            CACHE / "analysis" / keys["analysis"] / f"{number}.json", ObjectAnalysis,
            keys["analysis"],
        )  # fmt: skip
        objects = list(analysis.native.objects) + list(analysis.compounds)
        built = common.list_page(book, number)
        equations = common.equation_page(book, number)
        figures = final_figures(common.figure_page(book, number), equations)
        evidence = page_evidence(layout, page.store, objects, built, figures, equations)
        drawings = [o for o in analysis.native.objects if o.kind == "drawing"]
        if only is not None and number not in only:
            from book_core.tables.detect import candidates

            if not candidates(evidence):
                del analysis, objects
                continue
        pages[number] = {
            "evidence": evidence,
            "tokens": token_owners(page, layout),
            "drawings": drawings,  # rules are recomputed from these at scoring time
        }
        del analysis, objects
        if number % 50 == 0:
            print(book, number, round(time.perf_counter() - started), flush=True)
    BUNDLES.mkdir(parents=True, exist_ok=True)
    with gzip.open(BUNDLES / f"{book}{suffix}.pkl.gz", "wb") as stream:
        pickle.dump({"keys": {k: v for k, v in keys.items() if not k.startswith("_")},
                     "pages": pages}, stream, protocol=pickle.HIGHEST_PROTOCOL)  # fmt: skip
    print(book, "bundle", round(time.perf_counter() - started), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=common.BOOK_ORDER)
    parser.add_argument(
        "--sub",
        action="store_true",
        help="pages with a gold table or a table candidate only (_sub bundle)",
    )
    args = parser.parse_args()
    if args.sub:
        from book_core.tables import detect

        only = {p for t in common.gold_tables(args.book) for p in t["pages"]}
        found = common.read(common.OUT / "models" / f"{args.book}.json")["pages"]
        only |= {int(n) for n, row in found.items() if any(row.values())}
        layout_pages = set()
        for number in range(1, common.pages(args.book) + 1):
            layout = common.layout_page(args.book, number)
            if any(r.type == "table_candidate" for r in layout.regions) or any(
                b.kind == "table" for b in layout.blocks
            ):
                layout_pages.add(number)
        only |= layout_pages
        del detect
        build(args.book, only, "_sub")
    else:
        build(args.book)
