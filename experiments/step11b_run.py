"""Step 11b: the Step 11 evaluation of one book with the current producers, per rule variant.

Book 4 is a development book from this step on (owner decision, docs/decisions.md); its
Step 10b and Step 11 hold-out results stay the recorded hold-out numbers. There is no hold-out
in this step: every rule change is reported for books 1-4, so book 3 (anecdotal) runs once
per variant too; each of its runs is logged in experiments/out/step11b/runs.jsonl.

The evaluation is ``step11_run.main`` unchanged; only its output folder differs:
experiments/out/step11b/<label>/<book>/summary.json.

Usage: python step11b_run.py --book medical_anatomy --label after
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step11_run

OUT = ROOT / "experiments/out/step11b"


def main():
    args = sys.argv[1:]
    if "--label" not in args:
        raise SystemExit("pass --label <variant>")
    index = args.index("--label")
    label = args[index + 1]
    del args[index : index + 2]
    book = args[args.index("--book") + 1]
    step11_run.OUT = OUT / label
    step11_run.HOLDOUT = {}  # no hold-out in Step 11b (book 4 promoted; book 3 logged below)
    OUT.mkdir(parents=True, exist_ok=True)
    row = {"book": book, "label": label, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if book == "art_therapy_index":
        row["note"] = "anecdotal book run per rule variant (Step 11b: no hold-out)"
    with (OUT / "runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    sys.argv = [sys.argv[0], *args]
    step11_run.main()


if __name__ == "__main__":
    main()
