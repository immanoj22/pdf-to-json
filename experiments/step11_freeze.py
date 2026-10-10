"""Step 11 Task 7: freeze record of every producer before the book 4 hold-out run.

Writes the producer digests (alignment, document evidence, layout, reading order, furniture,
paragraphs, structure evidence, structure decision, lists), the dialect profile digests and the
runner digests to experiments/out/step11/freeze.json. ``--verify`` compares the current
digests with the record and exits 1 on any difference (run after the hold-out).

Usage: python step11_freeze.py [--verify]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))

OUT = ROOT / "experiments/out/step11"
RUNNERS = ("step5_run.py", "step5_gold.py", "step6_run.py", "step7_layouts.py",
           "step7_run.py", "step8_run.py", "step9_run.py", "step10_run.py",
           "step11_run.py")  # fmt: skip


def digests():
    from book_core.caching import code_digest
    from book_core.evaluation.dialect_profiles import file_digest, profile_digests
    from book_core.extraction.fingerprints import source_digest
    from book_core.furniture.keys import furniture_code_digest
    from book_core.lists.keys import lists_code_digest
    from book_core.paragraphs.keys import paragraph_code_digest
    from book_core.settings import Settings
    from book_core.structure.keys import evidence_code_digest, structure_code_digest

    profiles = json.loads(Path(Settings().reference_dialects).read_text("utf-8"))
    return {
        "producers": {
            "alignment": code_digest("alignment"),
            "document": code_digest("document"),
            "layout": code_digest("layout"),
            "reading_order": code_digest("reading_order"),
            "furniture": furniture_code_digest(),
            "paragraphs": paragraph_code_digest(),
            "structure_evidence": evidence_code_digest(),
            "structure": structure_code_digest(),
            "lists": lists_code_digest(),
        },
        "dialect_profile_file": file_digest(profiles),
        "dialect_profiles": profile_digests(profiles),
        "runners": {name: source_digest(ROOT / "experiments" / name) for name in RUNNERS},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    path = OUT / "freeze.json"
    current = digests()
    if args.verify:
        frozen = json.loads(path.read_text("utf-8"))
        for amendment in frozen.get("amendments", []):  # logged amendments
            if "producer" in amendment:
                frozen["producers"][amendment["producer"]] = amendment["new_sha256"]
            else:
                frozen["runners"][Path(amendment["file"]).name] = amendment["new_sha256"]
        same = {k: frozen[k] == current[k] for k in current}
        print(json.dumps(same, indent=1))
        sys.exit(0 if all(same.values()) else 1)
    OUT.mkdir(parents=True, exist_ok=True)
    record = {**current, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "note": "frozen before the single book 4 hold-out run (Steps 9-11)"}  # fmt: skip
    path.write_text(json.dumps(record, indent=1) + "\n", "utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
