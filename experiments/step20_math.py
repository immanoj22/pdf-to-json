"""Step 20 Statistics MathML score against the verified gold: the frozen Step 13c scorer
(``step13c_dev.evaluate`` on the run's archived regions and records, as
``step13c_evaluate.py`` reads them) for a Step 19 or Step 20 run record.

Usage: python step20_math.py experiments/out/step20/final/performance/statistics.json OUT.json
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]


def main():
    from step13c_dev import evaluate
    from step13c_evaluate import archive_records

    record, out = Path(sys.argv[1]), Path(sys.argv[2])
    run = json.loads(record.read_text("utf-8"))["run"]
    regions_by_page, records = archive_records(run)
    gold = evaluate(regions_by_page, records, range(1, run["pages"] + 1))
    gold.pop("rows", None)
    gold.pop("examples", None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gold, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in gold.items() if k in ("strict", "expression")})[:1500])


if __name__ == "__main__":
    main()
