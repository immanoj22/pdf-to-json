"""Step 14b runs: the Step 13a driver with the Step 14a final capture as baseline.

``freeze`` copies the Step 14a final capture of books 1-4 into
``experiments/out/step14b/before`` once; ``run``/``proof``/``compare``/``details`` are the
Step 13a actions (books 1-4 through the Step 11d/12 driver with layout-model evidence, the
math book through ``run_book``), writing under ``experiments/out/step14b/<out>``. The table
stage runs with its default client settings (model evidence on).

Usage:
  python step14b_run.py freeze
  python step14b_run.py run --book statistics --out final
  python step14b_run.py proof --book statistics --out final
  python step14b_run.py run --book spanish_us_history --out final
  python step14b_run.py compare --book spanish_us_history --out final
"""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run

step13_run.FROZEN = ROOT / "experiments/out/step14a/final"
step13_run.OUT = ROOT / "experiments/out/step14b"
step13_run.BEFORE = step13_run.OUT / "before"
# The Step 14b structure fix changes the lists keys: proofs recompute every page (the per-page
# proof checkpoints of earlier steps hold the old keys).
_proof = step13_run.driver.proof
step13_run.driver.proof = lambda book, fresh=True: _proof(book, fresh)

if __name__ == "__main__":
    step13_run.main()
