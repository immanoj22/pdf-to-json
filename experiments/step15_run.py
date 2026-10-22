"""Step 15 runs: the Step 13a driver with the Step 14b final capture as baseline.

``freeze`` copies the Step 14b final capture of books 1-4 into
``experiments/out/step15/before`` once; ``run``/``proof``/``compare``/``details`` are the
Step 13a actions (books 1-4 through the Step 11d/12 driver with layout-model evidence, the
math book through ``run_book``), writing under ``experiments/out/step15/<out>``. The new
continuity stage runs inside ``run_book`` after the tables stage.

Usage:
  python step15_run.py freeze
  python step15_run.py run --book art_therapy_index --out final
  python step15_run.py proof --book art_therapy_index --out final
  python step15_run.py compare --book art_therapy_index --out final
"""

# ruff: noqa: E402
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run

step13_run.FROZEN = ROOT / "experiments/out/step14b/final"
step13_run.OUT = ROOT / "experiments/out/step15"
step13_run.BEFORE = step13_run.OUT / "before"
# The lists change (glossary pages set as table regions) changes the lists keys: proofs
# recompute every page (the per-page proof checkpoints hold the Step 14b keys).
_proof = step13_run.driver.proof
step13_run.driver.proof = lambda book, fresh=True: _proof(book, fresh)

if __name__ == "__main__":
    step13_run.main()
