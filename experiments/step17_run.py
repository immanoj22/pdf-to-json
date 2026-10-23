"""Step 17 runs: the Step 15/16 driver with the Step 16 final capture as baseline.

``freeze`` copies the Step 16 final capture into ``experiments/out/step17/before`` once;
``run``/``proof``/``compare``/``details`` are the Step 13a actions writing under
``experiments/out/step17/<out>``. Book 2 (immigrant children) runs with OCR input for its
cover page (owner decision, Step 17 Part 0) through ``step17_ocr_cover.py``.

Usage:
  python step17_run.py freeze
  python step17_run.py run --book art_therapy_index --out final
  python step17_run.py proof --book art_therapy_index --out final
  python step17_run.py compare --book art_therapy_index --out final
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step13_run

step13_run.FROZEN = ROOT / "experiments/out/step16/final"
step13_run.OUT = ROOT / "experiments/out/step17"
step13_run.BEFORE = step13_run.OUT / "before"
_proof = step13_run.driver.proof
step13_run.driver.proof = lambda book, fresh=True: _proof(book, fresh)

if __name__ == "__main__":
    step13_run.main()
