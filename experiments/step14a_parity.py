"""Step 14a parity check: the stage's own page evidence decides as the development bundles.

For every page where development finds a table or a possible table (and every reference
table page), page evidence is built exactly as the stage builds it (``page_evidence`` with
the cached analysis objects, the lists-stage page, final figures, equation records, the
detectors' table boxes and the structure stage's navigation kind) and analysed; the text-
owning and possible tables (their line sets) must equal those from the bundle evidence.

Usage: python step14a_parity.py [--book NAME]
"""

# ruff: noqa: E402
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14a_dev as dev
from step7_layouts import CACHE

from book_core.equations.ownership import final_figures
from book_core.model.common import BBox
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.tables.evidence import page_evidence
from book_core.tables.page import analyze


def decided(evidence):
    tables, _ = analyze(evidence)
    return sorted((t.strong, tuple(sorted(line.id for line in t.lines))) for t in tables)


def check(book):
    bundle = dev.load(book, sub=book == "spanish_us_history")
    keys = common.keys(book)
    navigation = common.navigation(book)
    models = common.read(common.OUT / "models" / f"{book}.json")["pages"]
    pages = {p for t in common.gold_tables(book) for p in t["pages"]}
    for number, page in bundle["pages"].items():
        if analyze(page["evidence"])[0]:
            pages.add(number)
    differ = []
    for number in sorted(pages):
        analysis = verified_read(
            CACHE / "analysis" / keys["analysis"] / f"{number}.json", ObjectAnalysis,
            keys["analysis"],
        )  # fmt: skip
        equations = common.equation_page(book, number)
        row = models.get(str(number), {})
        evidence = page_evidence(
            common.layout_page(book, number),
            common.text_page(book, number).store,
            list(analysis.native.objects) + list(analysis.compounds),
            common.list_page(book, number),
            final_figures(common.figure_page(book, number), equations),
            equations,
            {
                name: [(BBox(x0=b[0], y0=b[1], x1=b[2], y1=b[3]), b[4], b[5]) for b in boxes]
                for name, boxes in row.items()
            },
            navigation.get(number),
        )
        if decided(evidence) != decided(bundle["pages"][number]["evidence"]):
            differ.append(number)
    print(book, "pages checked", len(pages), "differ", differ, flush=True)
    return differ


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    args = parser.parse_args()
    bad = [p for b in ([args.book] if args.book else common.BOOK_ORDER) for p in check(b)]
    sys.exit(1 if bad else 0)
