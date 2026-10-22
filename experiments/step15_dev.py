"""Step 15 development: the continuity stage on inputs rebuilt from a final archive.

Each page's stage input (``continuity.cache.PageInput``) is rebuilt from a final archive
(default: the Step 14b final capture): span store, cached layout, the final unit view, the
lists-stage order, text-owning tables, the units final figures link, the navigation kind and
the printed page label; with the structure stage's headings, the lists-stage links, the
Step 9 page joins and the book vocabulary of the run. ``link_book`` then decides exactly as
the stage does; the result is written as the archive would carry it
(``dev/<label>/<book>.json``) and scored with ``step15_measure`` (``--continuity``).

Usage: python step15_dev.py [--book NAME] [--label try1] [--capture DIR]
"""

# ruff: noqa: E402
import argparse
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common  # noqa: F401 - cache keys of the Step 14b final capture
import step15_common as c15
import step15_measure as measure

from book_core.cache_store import read_json
from book_core.continuity.cache import PageInput, link_book
from book_core.continuity.models import BookContinuity
from book_core.lists.models import ItemUnit
from book_core.model.common import Provenance
from book_core.model.spans import ExtractedPage
from book_core.reading_order.models import PageReadingOrder
from book_core.tables.models import TableRecord

DIGEST = "0" * 64


def vocabulary(book):
    if book == common.MATH_BOOK:
        from book_core.document_analysis.vocabulary import build_vocabulary

        texts = [common.text_page(book, n) for n in range(1, common.pages(book) + 1)]
        return build_vocabulary(texts)["casefold_frequencies"]
    from step8_run import vocabulary_for

    return vocabulary_for(book)


def claimed(figures):
    return frozenset(
        link["unit_id"]
        for figure in figures
        for name in ("captions", "credits", "internal_text")
        for link in figure.get(name, [])
    )


def inputs_of(book, capture):
    run = c15.capture_run(capture)(book)
    root = Path(run["output"])
    archive = read_json(root / "book.json.gz")
    navigation = {n["page"]: n["kind"] for n in archive["structure"]["navigation_pages"]}
    labels = {m["page"]: (m["label"], m["source"]) for m in archive["furniture"]["markers"]}

    to, came = {}, {}
    for link in archive["lists"]["page_links"]:
        to[link["from_unit_id"]] = link["to_unit_id"]
        came[link["to_unit_id"]] = link["from_unit_id"]

    def lists_links(unit):
        # The stage reads the lists-stage units: a Step 15 archive's units carry the
        # continuity links instead, so the lists-stage links are restored.
        return {**unit, "continues_to": to.get(unit["id"]), "continues_from": came.get(unit["id"])}

    def pages():
        for number in range(1, run["pages"] + 1):
            payload = read_json(root / f"page_{number:06d}.json.gz")
            yield PageInput(
                page=ExtractedPage.model_validate(payload["source"]),
                layout=common.layout_page(book, number),
                units=[ItemUnit.model_validate(lists_links(u))
                       for u in c15.final_units(payload)],  # fmt: skip
                order=PageReadingOrder.model_validate(payload["units"]["order"]),
                tables=[TableRecord.model_validate(t) for t in payload["tables"]["tables"]],
                claimed=claimed(payload["figures"]["figures"]),
                navigation=navigation.get(number),
                label=labels.get(number, (None, "none")),
            )  # fmt: skip

    headings = (
        frozenset(u for h in archive["structure"]["headings"] if not h["run_in"]
                  for u in h["unit_ids"]),
        frozenset(u for h in archive["structure"]["headings"] if h["run_in"]
                  for u in h["unit_ids"]),
    )  # fmt: skip
    lists = SimpleNamespace(page_links=archive["lists"]["page_links"])
    paragraphs = measure_paragraphs(book, capture)
    return pages, headings, lists, paragraphs, run["pages"]


def measure_paragraphs(book, capture):
    from step9_run import CACHE9

    from book_core.objects.analysis import verified_read
    from book_core.paragraphs.cache import BookParagraphResult

    key = c15.capture_run(capture)(book)["cache_keys"]["paragraphs"]
    return verified_read(CACHE9 / "paragraphs/book" / f"{key}.json", BookParagraphResult, key)


def run(book, label, capture):
    started = time.perf_counter()
    pages, headings, lists, paragraphs, total = inputs_of(book, capture)
    found = link_book(pages, headings, lists, paragraphs, vocabulary(book), total, DIGEST)
    record = BookContinuity(source_sha256=DIGEST, pages=total, version="dev",
                            provenance=Provenance(method="derived"), **found)  # fmt: skip
    path = c15.OUT / "dev" / label / f"{book}.json"
    common.write(path, record.model_dump(mode="json"))
    print(book, record.counts, record.profile, round(time.perf_counter() - started), "s",
          flush=True)  # fmt: skip
    measure.measure(book, Path(capture), f"dev/{label}/measure", continuity=path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--label", default="try")
    parser.add_argument("--capture", default=str(ROOT / "experiments/out/step14b/final"))
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        run(name, args.label, args.capture)
