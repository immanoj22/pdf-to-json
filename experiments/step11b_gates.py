"""Step 11b gates: the Step 11 gate suite (24-page source gate, I1-I7, every line in exactly
one unit and ordered once on the measured pages, the structure and lists stages on the
one-page fixtures, the full-book ledger), written to out/step11b. The whole-book unit gates
of the four books are in each book's Step 11b summary.

Usage: python step11b_gates.py [--skip-full-book]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step11_gates

if __name__ == "__main__":
    step11_gates.OUT = ROOT / "experiments/out/step11b"
    step11_gates.main()
