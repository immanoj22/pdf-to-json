"""Observe the cold 300-page jobs before production removes its temporary cache.

Only reads active-project caches. No reference extraction, scoring or new book run.
"""

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".cache/step11c/book300"
OUT = ROOT / "experiments/out/step11c/book300/parallel_pages.json"
STAGES = ("native", "analysis", "layout", "reading_order")


def files(root, stage):
    return {p.relative_to(root).as_posix(): p for p in (root / stage).glob("*/*.json")}


def main():
    development = BASE / "cache_development_1"
    proof = {}
    while len(proof) != len(STAGES):
        temporary = list((BASE / "final_production_2").glob("book-core-*"))
        if not temporary:
            if (ROOT / "experiments/out/step11c/book300/production_workers2.json").exists():
                raise RuntimeError(
                    "Production completed before the intermediate proof was captured"
                )
            time.sleep(0.2)
            continue
        for stage in STAGES:
            if stage in proof:
                continue
            old, new = files(development, stage), files(temporary[0], stage)
            if len(old) != 300 or len(new) != 300:
                continue
            if set(old) != set(new):
                raise ValueError(f"{stage} cache keys differ between worker counts")
            digests = {}
            for name in sorted(old):
                first = hashlib.sha256(old[name].read_bytes()).hexdigest()
                second = hashlib.sha256(new[name].read_bytes()).hexdigest()
                if first != second:
                    raise ValueError(f"Parallel page output differs: {name}")
                digests[name] = first
            proof[stage] = {"pages": len(digests), "byte_identical": True, "sha256": digests}
            OUT.write_text(json.dumps(proof, indent=2) + "\n", "utf8")
            print(stage, "300 page caches byte identical", flush=True)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
