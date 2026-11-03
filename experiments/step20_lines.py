"""Step 20 line-building check: rebuild visual lines with the current ``layout/lines.py`` from a
run's cached object analysis and compare them with that run's layout lines (no other stage
runs). Joined-across lines are measured against the native line order, as in
``step20_checks.py``. Changed lines are listed with their text for review.

Usage: python step20_lines.py --book iap_mec --tag before [--pages 27 210 | --all]
"""

import argparse
import json
import sys
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
OUT = ROOT / "experiments/out/step20"


def ranks(store):
    rank, position = {}, 0
    for line in store.lines:
        if not "".join(store.spans[sid].raw_text for sid in line.span_ids).strip():
            continue
        for sid in line.span_ids:
            rank[sid] = position
        position += 1
    return rank


def joined_across(span_ids, rank):
    found = sorted({rank[s] for s in span_ids if s in rank})
    return any(b - a > 1 for a, b in pairwise(found))


def compare(record, number):
    from book_core.layout.lines import build_lines
    from book_core.layout.models import PageLayout
    from book_core.objects.analysis import verified_read
    from book_core.objects.models import ObjectAnalysis

    root, keys = Path(record["cache"]), record["run"]["cache_keys"]
    analysis = verified_read(
        root / "analysis" / keys["analysis"] / f"{number}.json", ObjectAnalysis, keys["analysis"]
    )
    layout = verified_read(
        root / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
    )
    store = analysis.native.page.store
    rank = ranks(store)
    old = {frozenset(line.span_ids): line for line in layout.lines}
    new = {frozenset(line.span_ids): line for line in build_lines(analysis.native)}
    text = lambda spans: "".join(
        store.spans[s].raw_text for s in sorted(spans, key=list(store.spans).index)
    ).strip()[:100]
    removed = [k for k in old if k not in new]
    added = [k for k in new if k not in old]
    return {
        "page": number,
        "lines_old": len(old),
        "lines_new": len(new),
        "joined_across_old": sum(joined_across(k, rank) for k in old),
        "joined_across_new": sum(joined_across(k, rank) for k in new),
        "changed": [
            {"old": text(k), "new": [text(a) for a in added if a <= k]} for k in removed
        ],
        "added_not_from_split": sum(1 for a in added if not any(a <= k for k in removed)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pages", type=int, nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--name", default="lines")
    parser.add_argument("--show", type=int, default=0, help="print changed lines of N pages")
    args = parser.parse_args()
    record = json.loads((OUT / args.tag / "performance" / f"{args.book}.json").read_text("utf-8"))
    pages = range(1, record["run"]["pages"] + 1) if args.all else args.pages
    rows = [compare(record, n) for n in pages]
    changed = [r for r in rows if r["changed"]]
    summary = {
        "book": args.book,
        "pages": len(rows),
        "pages_changed": len(changed),
        "lines_old": sum(r["lines_old"] for r in rows),
        "lines_new": sum(r["lines_new"] for r in rows),
        "lines_changed": sum(len(r["changed"]) for r in rows),
        "joined_across_old": sum(r["joined_across_old"] for r in rows),
        "joined_across_new": sum(r["joined_across_new"] for r in rows),
        "added_not_from_split": sum(r["added_not_from_split"] for r in rows),
        "changed_pages": [r["page"] for r in changed],
    }
    target = OUT / "dev" / args.name / f"{args.book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"summary": summary, "pages": rows}, indent=1,
                                 ensure_ascii=False) + "\n", "utf-8")  # fmt: skip
    print(json.dumps({k: v for k, v in summary.items() if k != "changed_pages"}))
    for row in changed[: args.show]:
        print(f"-- p{row['page']}")
        for item in row["changed"][:12]:
            print("   ", repr(item["old"]), "->", [repr(t) for t in item["new"]])


if __name__ == "__main__":
    main()
