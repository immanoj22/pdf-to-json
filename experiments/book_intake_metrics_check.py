"""Book intake: books 1-4 give the same metrics after the reference paths moved.

Runs the unchanged Step 11 evaluation (as the Step 11b final run) into
out/book_intake/metrics_check/<book>, then compares each summary with
out/step11b/final/<book>/summary.json. Book 3 (anecdotal) runs once and is logged in
out/book_intake/runs.jsonl.

Usage: python book_intake_metrics_check.py run --book <book>
       python book_intake_metrics_check.py compare
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step11_run  # noqa: E402

OUT = ROOT / "experiments/out/book_intake"
FINAL = ROOT / "experiments/out/step11b/final"
BOOKS = ("spanish_us_history", "immigrant_children", "art_therapy_index", "medical_anatomy")
# Run state, not results: how long the run took and whether it was served from the cache.
# The cache key inputs are compared.
VOLATILE = {"seconds", "cache_hit"}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def differences(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            yield from differences(before.get(key), after.get(key), f"{path}/{key}")
    elif before != after:
        yield path


def compare():
    result = {}
    for book in BOOKS:
        before = strip(json.loads((FINAL / book / "summary.json").read_text("utf-8")))
        after = strip(
            json.loads((OUT / "metrics_check" / book / "summary.json").read_text("utf-8"))
        )
        hits = json.loads((OUT / "metrics_check" / book / "summary.json").read_text("utf-8"))
        result[book] = {
            "identical": before == after,
            "differences": list(differences(before, after)),
            "cache_hit": hits.get("cache_hit"),
        }
    (OUT / "metrics_check.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps({book: row["identical"] for book, row in result.items()}))
    raise SystemExit(0 if all(row["identical"] for row in result.values()) else 1)


def run(args):
    book = args[args.index("--book") + 1]
    step11_run.OUT = OUT / "metrics_check"
    step11_run.HOLDOUT = {}  # books 1-4 are development or anecdotal; nothing is sealed here
    OUT.mkdir(parents=True, exist_ok=True)
    row = {"book": book, "label": "metrics_check", "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if book == "art_therapy_index":
        row["note"] = "anecdotal book: one identity run after the reference paths moved"
    with (OUT / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    sys.argv = [sys.argv[0], *args]
    step11_run.main()


if __name__ == "__main__":
    mode, *rest = sys.argv[1:]
    compare() if mode == "compare" else run(rest)
