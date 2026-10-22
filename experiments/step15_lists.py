"""Step 15 Part 0 development check: lists-stage pages rebuilt with the current code.

Every page of a navigation kind (and ``--pages``) is rebuilt from the Step 14b final caches
(text page, layout, Step 9 units, the structure stage's navigation and headings, page
labels, the book vocabulary and compound lexicon) with the current ``lists.page`` and
compared with the cached Step 14b lists page: units (lines, kind) and order. Changed pages
are listed with their unit kinds before and after.

Usage: python step15_lists.py [--book NAME] [--pages N ...]
"""

# ruff: noqa: E402
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common  # noqa: F401 - keys of the Step 14b final capture
from step9_run import CACHE9
from step10_run import CACHE10

from book_core.cache_store import read_json
from book_core.lists.cache import page_contexts
from book_core.lists.page import DEFAULT_CONFIG, build_page_lists
from book_core.objects.analysis import verified_read
from book_core.paragraphs.lexicon import Profile
from book_core.paragraphs.models import PageParagraphs
from book_core.structure.models import BookStructure

OUT = ROOT / "experiments/out/step15/lists"
CAPTURE = ROOT / "experiments/out/step14b/final"


def step9_page(keys, number):
    entry = read_json(CACHE9 / "paragraphs/page" / keys["paragraphs"] / f"{number}.json")
    return PageParagraphs.model_validate(json.loads(entry["payload"]))


def context_of(book, keys):
    run = common.read(CAPTURE / "performance" / f"{book}.json")["run"]
    archive = read_json(Path(run["output"]) / "book.json.gz")
    markers = [SimpleNamespace(page=m["page"], label=m["label"])
               for m in archive["furniture"]["markers"]]  # fmt: skip
    structure = verified_read(
        CACHE10 / "structure/book" / f"{keys['structure']}.json", BookStructure,
        keys["structure"],
    )  # fmt: skip
    from book_core.document_analysis.vocabulary import build_vocabulary

    texts = [common.text_page(book, n) for n in range(1, common.pages(book) + 1)]
    vocabulary = build_vocabulary(texts)["casefold_frequencies"]
    profile = Profile()
    for page in texts:
        profile.add_page(page, common.layout_page(book, page.geometry.page),
                         SimpleNamespace(edges=[]))  # fmt: skip
    compounds = profile.freeze()["compounds"]
    del texts
    navigation = {n.page: n.kind for n in structure.navigation_pages}
    return page_contexts(structure, SimpleNamespace(markers=markers), vocabulary, compounds,
                         dict(DEFAULT_CONFIG)), navigation  # fmt: skip


def signature(built):
    units = sorted((tuple(u.line_ids), u.kind, u.stream_kind) for u in built.units)
    order = [tuple(s.line_ids) for s in built.order.streams]
    return units, order


def check(book, pages=None):
    keys = common.keys(book, CAPTURE)
    context, navigation = context_of(book, keys)
    wanted = sorted(set(pages or []) | set(navigation))
    changed = []
    for number in wanted:
        page = common.text_page(book, number)
        layout = common.layout_page(book, number)
        built, _ = build_page_lists(page, layout, step9_page(keys, number), context(number))
        before = common.list_page(book, number)
        if signature(built) == signature(before):
            continue
        changed.append({
            "page": number, "navigation": navigation.get(number),
            "kinds_before": dict(Counter(u.kind for u in before.units)),
            "kinds_after": dict(Counter(u.kind for u in built.units)),
            "order_changes": [len(before.order_changes), len(built.order_changes)],
        })  # fmt: skip
    row = {"book": book, "pages_checked": len(wanted), "changed": changed}
    common.write(OUT / f"{book}.json", row)
    print(book, len(wanted), [(c["page"], c["navigation"]) for c in changed], flush=True)
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--pages", type=int, nargs="*")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        check(name, args.pages)
