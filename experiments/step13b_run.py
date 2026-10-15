"""Step 13b runs: the Step 13a driver with the Step 13a final capture as baseline.

``freeze`` copies the Step 13a final capture of books 1-4 (identity, objects, full gates and
metrics) into ``experiments/out/step13b/before`` once. ``run``/``proof``/``compare``/
``details`` are the Step 13a actions (books 1-4 through the Step 11d/12 driver with layout-
model figure evidence; the math book through ``run_book``), writing under
``experiments/out/step13b/<out>``.

Usage:
  python step13b_run.py freeze
  python step13b_run.py run --book statistics --out final
  python step13b_run.py proof --book statistics --out final
  python step13b_run.py run --book spanish_us_history --out final
  python step13b_run.py compare --out final
"""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run

step13_run.FROZEN = ROOT / "experiments/out/step13/final"
step13_run.OUT = ROOT / "experiments/out/step13b"
step13_run.BEFORE = step13_run.OUT / "before"

if __name__ == "__main__":
    step13_run.main()
