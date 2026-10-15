"""Step 13b boundary table: the unchanged Step 13a boundary labels on the 13b final records.

Every verified gold equation and the same seeded sample of 200 (seed 13); a seeded 40 of the
sample (seed 14) rendered for the manual check, written under
``experiments/out/step13b/boundaries``.

Usage: python step13b_boundaries.py
"""

# ruff: noqa: E402
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_boundaries

step13_boundaries.OUT = ROOT / "experiments/out/step13b/boundaries"

if __name__ == "__main__":
    run = json.loads(
        (ROOT / "experiments/out/step13b/final/performance/statistics.json").read_text("utf-8")
    )["run"]
    step13_boundaries.main(run["cache_keys"]["equations"], 200, 13)
