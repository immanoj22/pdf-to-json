"""Run the unchanged Step 11 gates without overwriting historical evidence."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step11_gates  # noqa: E402

if __name__ == "__main__":
    step11_gates.OUT = ROOT / "experiments/out/step11c/gates"
    step11_gates.main()
