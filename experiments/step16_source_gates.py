"""Step 16 source, ledger and final-archive gates: the Step 15 gates on the Step 16 runs."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step15_source_gates as s15

s15.gates.RUN = ROOT / "experiments/out/step16/final"
s15.gates.BASELINE = ROOT / "experiments/out/step16/before"

if __name__ == "__main__":
    for name in (
        "spanish_us_history",
        "immigrant_children",
        "art_therapy_index",
        "medical_anatomy",
        "statistics",
    ):
        s15._load(name)
    s15.gates.main()
