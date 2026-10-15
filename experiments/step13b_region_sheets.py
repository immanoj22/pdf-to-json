"""Step 13b review sheets: the Step 13a contact sheets on the 13b final records.

A seeded sample per source (manual precision), or every region carrying a rule (for example
``display_rows``: each display joined over rows is reviewed). Red box = region.

Usage: python step13b_region_sheets.py --book statistics --source vector --n 40 --seed 91
       python step13b_region_sheets.py --book statistics --rule display_rows --n 1000
"""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_inspect
import step13_region_sheets

step13_region_sheets.OUT = ROOT / "experiments/out/step13b/review"


def main(book, n, seed, source, rule):
    run = json.loads(
        (ROOT / f"experiments/out/step13b/final/performance/{book}.json").read_text("utf-8")
    )["run"]
    key = run["cache_keys"]["equations"]
    if rule:
        rows = step13_inspect.rows
        # The rule names the sheet folder; regions of every source are filtered by rule.
        step13_region_sheets.rows = lambda book, run, key, _source: (
            row for row in rows(book, run, key) if rule in row["rules"]
        )
    step13_region_sheets.main(book, "final", n, seed, source or rule, key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=91)
    parser.add_argument("--source")
    parser.add_argument("--rule")
    args = parser.parse_args()
    main(args.book, args.n, args.seed, args.source, args.rule)
