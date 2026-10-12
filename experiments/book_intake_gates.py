"""Book intake gates: the Step 11 gate suite with the current producers, written to
out/book_intake/gates, after the reference paths moved to references.local.toml.

Usage: python book_intake_gates.py [--skip-full-book]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step11_gates  # noqa: E402

if __name__ == "__main__":
    step11_gates.OUT = ROOT / "experiments/out/book_intake/gates"
    step11_gates.main()
