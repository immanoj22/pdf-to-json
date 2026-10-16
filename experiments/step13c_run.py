"""Step 13c runs: the Step 13a/13b driver with the Step 13b final capture as baseline.

``freeze`` copies the Step 13b final capture of books 1-4 into
``experiments/out/step13c/before`` once; ``run``/``proof``/``compare``/``details`` are the
Step 13a actions (books 1-4 through the Step 11d/12 driver with layout-model evidence, the
math book through ``run_book``), writing under ``experiments/out/step13c/<out>``. The MathML
stage runs with its default client settings (image recognition on: PP-FormulaNet-L from the
project model cache, readings cached per image under ``.cache/models``).

Usage:
  python step13c_run.py freeze
  python step13c_run.py run --book statistics --out final
  python step13c_run.py proof --book statistics --out final
  python step13c_run.py run --book spanish_us_history --out final
  python step13c_run.py compare --book spanish_us_history --out final
"""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run

step13_run.FROZEN = ROOT / "experiments/out/step13b/final"
step13_run.OUT = ROOT / "experiments/out/step13c"
step13_run.BEFORE = step13_run.OUT / "before"

if __name__ == "__main__":
    step13_run.main()
