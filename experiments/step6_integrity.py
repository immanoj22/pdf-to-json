"""Read-only gold integrity before/after repository line-ending normalization."""

import json

from reference_paths import PROJECT_ROOT

from book_core.evaluation.derived_harness import DerivedGold


def verify():
    rows = []
    for directory in sorted((PROJECT_ROOT / "backend/tests/gold_derived").iterdir()):
        if directory.is_dir():
            gold = DerivedGold.load(directory)
            rows.append({"book": gold.book, "units": len(gold.units), "checksums": "verified"})
    return {"derived_gold": rows, "modified_gold": False}


if __name__ == "__main__":
    result = verify()
    out = PROJECT_ROOT / "experiments/out/step6"
    out.mkdir(parents=True, exist_ok=True)
    (out / "gold_integrity.json").write_bytes((json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps(result))
