"""Step 10b gates: the Step 10 gate suite (24-page source gate, I1-I7, every line in exactly
one unit and ordered once on the measured pages, the structure stage on the one-page
fixtures, the full-book ledger) with the current code, written to out/step10b. The whole-book
unit gates of the four books are in each book's Step 10 summary.

Usage: python step10b_gates.py [--skip-full-book]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step10_gates  # noqa: E402

if __name__ == "__main__":
    step10_gates.OUT = ROOT / "experiments/out/step10b"
    step10_gates.main()
