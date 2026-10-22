"""Step 15 Task 4: effect on units and paragraphs, Step 14b final archive vs Step 15 final archive.

Token owners as in Step 14b (``step14b_effect.assignment``): a table cell (or the unit lying
wholly in it), else the unit of the final view. Two paragraph views per archive:

- **per page**: a unit and the units it continues into on the same page (column links)
  form one logical paragraph; page breaks split (the book-1 reference convention);
- **chained**: every link counts, across pages too (the convention of the book-2 and
  book-4 references, which keep paragraphs whole across page breaks).

Before (Step 14b) the links are the units' own (``continues_from``); after, the continuity
record's. Per book: paragraph scores of both views before and after, page by page the
change of boundary tp/fp/fn with its cause (pages whose units changed, pages with a new
link), unit kinds, and order inside reference tables.

Usage: python step15_effect.py [--book NAME] [--out final]
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common  # noqa: F401
import step14b_effect as e14b

from book_core.cache_store import read_json
from book_core.evaluation.paragraphs import PARAGRAPH_KINDS, paragraph_scores

OUT = ROOT / "experiments/out/step15"


def links(root, pages):
    """[(from page, from id, to page, to id)] of an archive: the continuity record, else the
    units' own links."""
    book = read_json(root / "book.json.gz")
    if "continuity" in book:
        return [(b["from_page"], b["from_id"], b["to_page"], b["to_id"])
                for c in book["continuity"]["chains"] if c["kind"] != "table"
                for b in c["breaks"]]  # fmt: skip
    out = []
    for number in range(1, pages + 1):
        payload = read_json(root / f"page_{number:06d}.json.gz")
        view = payload["table_view"]
        removed = set(view["removed"])
        units = [u for u in payload["units"]["units"] if u["id"] not in removed]
        for unit in [*units, *view["added"]]:
            if unit.get("continues_to"):
                out.append((number, unit["id"], number + 1, unit["continues_to"]))
    return out


def logical(assigned, found, chained):
    parent = {}

    def root(x):
        while x in parent:
            x = parent[x]
        return x

    for fp, a, tp, b in found:
        if chained or fp == tp:
            ra, rb = root(a), root(b)
            if ra != rb:
                parent[rb] = ra
    return {token: root(owner) for token, owner in assigned.items()}


def evaluate(book, out):
    before_root, run = e14b.archive(ROOT / f"experiments/out/step14b/final/performance/{book}.json")
    after_root, _ = e14b.archive(OUT / out / f"performance/{book}.json")
    tables_gold = common.gold_tables(book)
    a_before, k_before, t_before, o_before = e14b.assignment(book, before_root, run["pages"],
                                                             tables_gold)  # fmt: skip
    a_after, k_after, t_after, o_after = e14b.assignment(book, after_root, run["pages"],
                                                         tables_gold)  # fmt: skip
    l_before, l_after = links(before_root, run["pages"]), links(after_root, run["pages"])
    result = {
        "book": book,
        "unit_kinds": {
            k: [k_before.get(k, 0), k_after.get(k, 0)] for k in sorted(set(k_before) | set(k_after))
        },  # fmt: skip
        "links": {
            "before": len(l_before),
            "after": len(l_after),
            "column_after": sum(fp == tp for fp, _, tp, _ in l_after),
        },  # fmt: skip
        "cell_order_in_reference_tables": {
            name: round(o["agree"] / o["pairs"], 4) if o["pairs"] else None
            for name, o in (("before", o_before), ("after", o_after))
        },
    }
    if book == common.MATH_BOOK:
        common.write(OUT / out / "effect" / f"{book}.json", result)
        return result
    gold = common.derived_gold(book)
    sequence = [(p, o, u["unit"]) for u in gold.units if u["kind"] in PARAGRAPH_KINDS
                for p, first, n in u["pdf"] for o in range(first, first + n)]  # fmt: skip
    new_link_pages = {fp for fp, _, tp, _ in set(l_after) - set(l_before)} | {
        tp for _, _, tp, _ in set(l_after) - set(l_before)}  # fmt: skip
    unit_pages = {p for (p, _), owner in a_after.items() if a_before.get((p, _)) != owner}
    unit_pages |= {p for (p, _), owner in a_before.items() if a_after.get((p, _)) != owner}
    for view, chained in (("per_page", False), ("chained", True)):
        before = logical(a_before, l_before, chained)
        after = logical(a_after, l_after, chained)
        result[view] = {"before": paragraph_scores(gold, before),
                        "after": paragraph_scores(gold, after)}  # fmt: skip
        changes = defaultdict(Counter)
        for name, mapping in (("before", before), ("after", after)):
            scored = [(p, o, u) for p, o, u in sequence if (p, o) in mapping]
            for (p1, o1, u1), (p2, o2, u2) in zip(scored, scored[1:], strict=False):
                ref, ours = u1 != u2, mapping[(p1, o1)] != mapping[(p2, o2)]
                changes[p1][f"{name}_tp"] += ref and ours
                changes[p1][f"{name}_fp"] += ours and not ref
                changes[p1][f"{name}_fn"] += ref and not ours
        pages = {}
        for number, row in sorted(changes.items()):
            delta = {k: row[f"after_{k}"] - row[f"before_{k}"] for k in ("tp", "fp", "fn")}
            if any(delta.values()):
                cause = []
                if number in unit_pages:
                    cause.append("units changed (Part 0)")
                if number in new_link_pages or number + 1 in new_link_pages:
                    cause.append("new continuity link")
                pages[str(number)] = {"boundary_change": delta, "cause": cause}
        result[view]["pages"] = pages
        result[view]["unexplained_pages"] = [p for p, r in pages.items() if not r["cause"]]
    common.write(OUT / out / "effect" / f"{book}.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    keys = ("boundary_precision", "boundary_recall", "boundary_f1", "exact_unit_match")
    for name in [args.book] if args.book else common.BOOK_ORDER:
        r = evaluate(name, args.out)
        brief = {"links": r["links"], "kinds": r["unit_kinds"]}
        for view in ("per_page", "chained"):
            if view in r:
                brief[view] = {side: {k: r[view][side][k] for k in keys}
                               for side in ("before", "after")}  # fmt: skip
                brief[view]["unexplained"] = r[view]["unexplained_pages"]
        print(name, brief, flush=True)


if __name__ == "__main__":
    main()
