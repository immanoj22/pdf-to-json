"""Step 16 parity: the Step 15 development-path checks on the Step 16 final archives."""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step15_parity as parity

parity.FINAL = ROOT / "experiments/out/step16/final"

if __name__ == "__main__":
    bad = Counter()
    for name in common.BOOK_ORDER:
        row = {"continuity": parity.continuity(name), "tables": parity.tables(name)}
        bad["continuity"] += not row["continuity"]["identical"]
        bad["tables"] += bool(row["tables"]["differ"])
        common.write(parity.FINAL / "parity" / f"{name}.json", row)
        print(
            name,
            row["continuity"]["identical"],
            row["tables"]["differ"][:5],
            flush=True,
        )
    sys.exit(1 if sum(bad.values()) else 0)
