"""Step 16 runs: the Step 15 driver with the Step 15 final capture as baseline.

Born-digital books must reproduce Step 15 exactly: the OCR stage is not enabled here.
``freeze`` copies the Step 15 final capture into ``experiments/out/step16/before`` once;
``run``/``proof``/``compare``/``details`` are the Step 13a actions writing under
``experiments/out/step16/<out>``.  ``archives`` compares the final archives file by file.

Usage:
  python step16_run.py freeze
  python step16_run.py run --book art_therapy_index --out final
  python step16_run.py proof --book art_therapy_index --out final
  python step16_run.py compare --book art_therapy_index --out final
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run

step13_run.FROZEN = ROOT / "experiments/out/step15/final"
step13_run.OUT = ROOT / "experiments/out/step16"
step13_run.BEFORE = step13_run.OUT / "before"
_proof = step13_run.driver.proof
step13_run.driver.proof = lambda book, fresh=True: _proof(book, fresh)

if __name__ == "__main__":
    step13_run.main()
