"""Step 14b Task 6: effect on units, Step 14a final archive vs Step 14b final archive.

For each archive, every retained token is assigned to its final owner as in Step 14a
(``step14a_effect``): a table cell (or the unit lying wholly in that cell), else its unit in
the final view. Per book:

- paragraph metric (``evaluation.paragraphs.paragraph_scores``) of both archives, and page by
  page the change of boundary true positives, false positives and misses, with the pages'
  tables and navigation kinds before and after (every change must be on such a page);
- unit kinds (paragraphs, list items, headings, index/contents/glossary entries) before and
  after, headings of the structure stage before and after;
- order inside reference tables (Step 14a pairs measure).

Usage: python step14b_effect.py --book NAME [--out final]
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b
from step14a_bundles import token_owners
from step14a_effect import cell_tokens

from book_core.cache_store import read_json
from book_core.evaluation.paragraphs import PARAGRAPH_KINDS, paragraph_scores
from book_core.lists.models import TEXT_KINDS
from book_core.model.spans import ExtractedPage


def archive(path):
    run = common.read(path)["run"]
    return Path(run["output"]), run


def assignment(book, root, pages, tables_gold):
    """(after {(page, ordinal): owner}, unit kinds, per-page tables, cell order pairs)."""
    after, kinds, tables_of, order = {}, Counter(), {}, Counter()
    for number in range(1, pages + 1):
        payload = read_json(root / f"page_{number:06d}.json.gz")
        page = ExtractedPage.model_validate(payload["source"])
        owners = token_owners(page, common.layout_page(book, number))
        units = payload["units"]["units"]
        view = payload["table_view"]
        removed = set(view["removed"])
        final = [u for u in units if u["id"] not in removed] + view["added"]
        kinds.update(u["kind"] for u in final)
        unit_of = {lid: u for u in units for lid in u["line_ids"]}
        final_of = {lid: u for u in final for lid in u["line_ids"]}
        tables = payload["tables"]["tables"]
        tables_of[number] = len(tables)
        cells, cell_order = {}, {}
        cell_units = {c["id"]: set(c["unit_ids"]) for t in tables for c in t["cells"]}
        for table in tables:
            found = cell_tokens(payload, table, owners)
            cells.update(found)
            rank = {c["id"]: k for k, c in enumerate(
                sorted(table["cells"], key=lambda c: (c["row"], c["column"])))}  # fmt: skip
            for ordinal, cid in found.items():
                cell_order[ordinal] = (table["id"], rank[cid], ordinal)
        for ordinal, (line, _) in enumerate(owners):
            if ordinal in cells:
                unit = unit_of.get(line)
                inside = unit is not None and unit["id"] in cell_units.get(cells[ordinal], ())
                after[(number, ordinal)] = unit["id"] if inside else cells[ordinal]
            else:
                unit = final_of.get(line)
                if unit is not None and unit["kind"] in TEXT_KINDS:
                    after[(number, ordinal)] = unit["id"]
        for t in tables_gold:
            if number not in t["pages"]:
                continue
            firsts = []
            for c in sorted(t["cells"], key=lambda c: (c["row"], c["column"])):
                refs = [o for p, o in c["tokens"] if p == number]
                if refs and refs[0] in cell_order:
                    firsts.append(cell_order[refs[0]])
            for i in range(len(firsts)):
                for j in range(i + 1, len(firsts)):
                    if firsts[i][0] == firsts[j][0]:
                        order["pairs"] += 1
                        order["agree"] += firsts[i] <= firsts[j]
    return after, kinds, tables_of, order


def headings(root):
    book = read_json(root / "book.json.gz")
    return {(h["page"], tuple(h["unit_ids"])) for h in book["structure"]["headings"]}, {
        n["page"]: n["kind"] for n in book["structure"]["navigation_pages"]
    }


def evaluate(book, out):
    before_root, run = archive(ROOT / f"experiments/out/step14a/final/performance/{book}.json")
    after_root, _ = archive(c14b.OUT / out / f"performance/{book}.json")
    tables_gold = common.gold_tables(book)
    a_before, k_before, t_before, o_before = assignment(book, before_root, run["pages"],
                                                        tables_gold)  # fmt: skip
    a_after, k_after, t_after, o_after = assignment(book, after_root, run["pages"], tables_gold)
    h_before, n_before = headings(before_root)
    h_after, n_after = headings(after_root)
    result = {
        "book": book,
        "unit_kinds": {
            k: [k_before.get(k, 0), k_after.get(k, 0)] for k in sorted(set(k_before) | set(k_after))
        },  # fmt: skip
        "headings": {
            "before": len(h_before),
            "after": len(h_after),
            "removed": sorted([list(h) for h in h_before - h_after]),
            "added": sorted([list(h) for h in h_after - h_before]),
        },  # fmt: skip
        "navigation_changed": {
            str(p): [n_before.get(p), n_after.get(p)]
            for p in sorted(set(n_before) | set(n_after))
            if n_before.get(p) != n_after.get(p)
        },  # fmt: skip
        "cell_order_in_reference_tables": {
            name: round(o["agree"] / o["pairs"], 4) if o["pairs"] else None
            for name, o in (("before", o_before), ("after", o_after))
        },
    }
    if book != common.MATH_BOOK:
        gold = common.derived_gold(book)
        result["paragraphs"] = {"before": paragraph_scores(gold, a_before),
                                "after": paragraph_scores(gold, a_after)}  # fmt: skip
        sequence = [(p, o, u["unit"]) for u in gold.units if u["kind"] in PARAGRAPH_KINDS
                    for p, first, n in u["pdf"] for o in range(first, first + n)]  # fmt: skip
        changes = defaultdict(Counter)
        for name, logical in (("before", a_before), ("after", a_after)):
            scored = [(p, o, u) for p, o, u in sequence if (p, o) in logical]
            for (p1, o1, u1), (p2, o2, u2) in zip(scored, scored[1:], strict=False):
                ref, ours = u1 != u2, logical[(p1, o1)] != logical[(p2, o2)]
                changes[p1][f"{name}_tp"] += ref and ours
                changes[p1][f"{name}_fp"] += ours and not ref
                changes[p1][f"{name}_fn"] += ref and not ours
        pages = {}
        for number, row in sorted(changes.items()):
            delta = {k: row[f"after_{k}"] - row[f"before_{k}"] for k in ("tp", "fp", "fn")}
            if any(delta.values()):
                pages[str(number)] = {
                    "boundary_change": delta,
                    "tables": [t_before.get(number, 0), t_after.get(number, 0)],
                    "navigation": [n_before.get(number), n_after.get(number)],
                }
        result["pages"] = pages
        result["changes_without_a_table_or_navigation_change"] = [
            p for p, row in pages.items()
            if not any(row["tables"]) and row["navigation"][0] == row["navigation"][1]
        ]  # fmt: skip
    common.write(c14b.OUT / out / "effect" / f"{book}.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", choices=common.BOOK_ORDER)
    parser.add_argument("--out", default="final")
    args = parser.parse_args()
    for name in [args.book] if args.book else common.BOOK_ORDER:
        r = evaluate(name, args.out)
        short = {k: v for k, v in r.items() if k not in {"pages", "paragraphs", "headings"}}
        short["headings"] = {k: r["headings"][k] for k in ("before", "after")}
        if "paragraphs" in r:
            for side in ("before", "after"):
                s = r["paragraphs"][side]
                short[side] = {k: s[k] for k in ("boundary_precision", "boundary_recall",
                                                 "boundary_f1", "exact_unit_match")}  # fmt: skip
        print(short, flush=True)


if __name__ == "__main__":
    main()
