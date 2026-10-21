"""Step 14b development evidence: one pickle per page, built from the current caches.

Each page's table-stage ``PageEvidence`` (built exactly as the stage builds it: layout, span
store, analysis objects and compounds, lists-stage page, final figures, equation records,
the learned detectors' table boxes from ``experiments/out/step14a/models`` and the Step 14b
navigation kind), its token owners per retained token ordinal and its lists-stage page are
written to the git-ignored ``.cache/step14b/pages/<book>/<page>.pkl.gz``. Pages are loaded
one at a time (``step14b_common.pages``), so whole books fit in memory. Pages without any
table candidate (and no reference table) are skipped: they never hold a table.

Usage: python step14b_bundles.py --book NAME
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
import step14b_common as c14b
from step7_layouts import CACHE
from step14a_bundles import token_owners

from book_core.equations.ownership import final_figures
from book_core.model.common import BBox
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.tables.detect import candidates
from book_core.tables.evidence import page_evidence


def build(book):
    keys = common.keys(book)
    started = time.perf_counter()
    found = common.read(common.OUT / "models" / f"{book}.json")["pages"]
    navigation = c14b.navigation(book)
    gold_pages = {p for t in common.gold_tables(book) for p in t["pages"]}
    target = c14b.PAGES / book
    target.mkdir(parents=True, exist_ok=True)
    kept = []
    for number in range(1, common.pages(book) + 1):
        page = common.text_page(book, number)
        layout = common.layout_page(book, number)
        analysis = verified_read(
            CACHE / "analysis" / keys["analysis"] / f"{number}.json", ObjectAnalysis,
            keys["analysis"],
        )  # fmt: skip
        built = common.list_page(book, number)
        equations = common.equation_page(book, number)
        row = found.get(str(number), {})
        models = {
            name: [(BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]), b[4], b[5]) for b in boxes]
            for name, boxes in row.items()
        }
        evidence = page_evidence(
            layout, page.store, list(analysis.native.objects) + list(analysis.compounds), built,
            final_figures(common.figure_page(book, number), equations), equations, models,
            navigation.get(number),
        )  # fmt: skip
        del analysis
        if number not in gold_pages and not candidates(evidence):
            continue
        with gzip.open(target / f"{number}.pkl.gz", "wb") as stream:
            pickle.dump({"evidence": evidence, "tokens": token_owners(page, layout),
                         "built": built}, stream, protocol=pickle.HIGHEST_PROTOCOL)  # fmt: skip
        kept.append(number)
        if number % 100 == 0:
            print(book, number, len(kept), round(time.perf_counter() - started), flush=True)
    stored = {k: v for k, v in keys.items() if not k.startswith("_")}
    # The index names the pages of this build; files of earlier builds are never read.
    common.write(target / "_index.json", {"keys": stored, "pages": kept})
    print(book, "pages kept", len(kept), round(time.perf_counter() - started), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        build(name)
