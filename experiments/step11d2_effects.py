"""Explain accuracy changes on every page whose list units changed."""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step11c_identity import BOOKS
from step11d2_hidden import write
from step11d2_run import BASE, CACHE, CACHE9, CACHE11, differences, read

from book_core.cache_store import read_json
from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.furniture import token_lines
from book_core.evaluation.lists import LIST_KINDS, Ours, list_items
from book_core.evaluation.reading_order import ReadingOrderOutput, page_order, reading_order_scores
from book_core.layout.models import PageLayout
from book_core.lists.cache import BookListsResult
from book_core.lists.cache import load_page as list_page
from book_core.lists.keys import book_fingerprint
from book_core.lists.models import TEXT_KINDS
from book_core.model.spans import ExtractedPage
from book_core.objects.analysis import verified_read
from book_core.paragraphs.cache import BookParagraphResult
from book_core.paragraphs.cache import load_page as paragraph_page
from book_core.paragraphs.text import unit_text

OUT = ROOT / "experiments/out/step11d2/hidden"


def order_pairs(gold, number, view):
    merged = defaultdict(list)
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            if page == number:
                merged[unit["unit"]].extend(range(first, first + length))
    main = next((s for s, info in view.streams.items() if info["kind"] == "main"), None)
    rank = {token: i for i, token in enumerate(view.main)}
    positions = {}
    for uid, tokens in merged.items():
        stream = Counter(view.stream_of.get(t) for t in tokens).most_common(1)[0][0]
        if main is not None and stream == main:
            positions[uid] = median(rank[t] for t in tokens if t in rank)
    return {
        "main_units": sorted(positions),
        "concordant": [
            [a, b] for a, b in combinations(sorted(positions), 2) if positions[a] < positions[b]
        ],
        "discordant": [
            [a, b] for a, b in combinations(sorted(positions), 2) if positions[a] > positions[b]
        ],
    }


def main(book):
    versions = [read(BASE / f"{book}.json"), read(OUT / f"after/{book}.json")]
    numbers = [
        int(n)
        for n in versions[0]["pages"]
        if versions[0]["pages"][n]["lists"] != versions[1]["pages"][n]["lists"]
    ]
    gold = DerivedGold.load(ROOT / "backend/tests/gold_derived" / book)
    archive = Path(read(OUT.parent.parent / f"step11e/performance/{book}.json")["run"]["output"])
    results = []
    for version in versions:
        keys = version["keys"]
        paragraphs = verified_read(
            CACHE9 / "paragraphs/book" / f"{keys['paragraphs']}.json",
            BookParagraphResult,
            keys["paragraphs"],
        )
        key = book_fingerprint(keys["lists"])
        lists = verified_read(CACHE11 / "lists/book" / f"{key}.json", BookListsResult, key)
        stages, views, pairs, descriptions = {}, {}, {}, {}
        ours = Ours(unit_of={})
        for number in numbers:
            page = ExtractedPage.model_validate(
                read_json(archive / f"page_{number:06d}.json.gz")["source"]
            )
            layout = verified_read(
                CACHE / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
            )
            built = list_page(lists, number, CACHE11)
            prior = paragraph_page(paragraphs, number, CACHE9)
            owner = {lid: unit for unit in built.units for lid in unit.line_ids}
            for ordinal, lid in enumerate(token_lines(page, layout)):
                unit = owner.get(lid)
                if unit is not None and unit.kind in TEXT_KINDS:
                    ours.unit_of[number, ordinal] = unit.id
            for unit in built.units:
                ours.kind_of[unit.id] = unit.kind
                if unit.list_id:
                    ours.list_of[unit.id] = unit.list_id
                if unit.level is not None:
                    ours.level_of[unit.id] = unit.level
            views[number], _ = page_order(page, layout, built.order)
            pairs[number] = order_pairs(gold, number, views[number])
            stages[number] = {
                name: [
                    {
                        "id": u.id,
                        "kind": u.kind,
                        "stream_kind": u.stream_kind,
                        "line_ids": u.line_ids,
                        "text": unit_text(page.store, layout, u),
                        "list_id": getattr(u, "list_id", None),
                        "level": getattr(u, "level", None),
                    }
                    for u in model.units
                ]
                for name, model in (("paragraphs", prior), ("lists", built))
            }
            descriptions.update({u["id"]: u for u in stages[number]["lists"]})
        item_rows = {}
        for unit in list_items(gold):
            tokens = [
                (p, i)
                for p, start, length in unit["pdf"]
                for i in range(start, start + length)
                if (p, i) in ours.unit_of
            ]
            if not tokens:
                continue
            votes = Counter(ours.unit_of[t] for t in tokens)
            majority = votes.most_common(1)[0][0]
            item_rows[unit["unit"]] = {
                "page": tokens[0][0],
                "scored_tokens": len(tokens),
                "kind_agrees": ours.kind_of[majority] in LIST_KINDS,
                "units": [descriptions[uid] for uid in votes],
            }
        results.append(
            {
                "stages": stages,
                "reference_items": item_rows,
                "pairs": pairs,
                "reading_order": reading_order_scores(
                    gold, ReadingOrderOutput("step11", book, {}, {}, views)
                ),
            }
        )
    changed_items = {}
    for uid in results[0]["reference_items"].keys() | results[1]["reference_items"].keys():
        a, b = [r["reference_items"].get(uid) for r in results]
        if (
            a is None
            or b is None
            or a["kind_agrees"] != b["kind_agrees"]
            or a["scored_tokens"] != b["scored_tokens"]
            or len(a["units"]) != len(b["units"])
        ):
            changed_items[uid] = {"before": a, "after": b}
    pair_changes = {}
    for number in numbers:
        values = {}
        for kind in ("concordant", "discordant"):
            a, b = [{tuple(p) for p in r["pairs"][number][kind]} for r in results]
            values[kind] = {"added": sorted(b - a), "removed": sorted(a - b)}
        pair_changes[number] = values
    write(
        OUT / f"effects_{book}.json",
        {
            "changed_pages": numbers,
            "changed_reference_items": changed_items,
            "pair_changes": pair_changes,
            "versions": results,
            "reading_order_changes": differences(*[r["reading_order"] for r in results]),
        },
    )
    print(
        book,
        "changed list kinds",
        [
            (uid, row["before"]["kind_agrees"], row["after"]["kind_agrees"])
            for uid, row in changed_items.items()
            if row["before"] is not None
            and row["after"] is not None
            and row["before"]["kind_agrees"] != row["after"]["kind_agrees"]
        ],
    )
    print(
        "order pair changes",
        {
            n: {k: {side: len(items) for side, items in v.items()} for k, v in row.items()}
            for n, row in pair_changes.items()
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=BOOKS, required=True)
    main(parser.parse_args().book)
