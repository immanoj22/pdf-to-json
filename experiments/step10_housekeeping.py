"""Step 10 housekeeping: report cache disk use; delete only superseded Step 10 entries.

An evidence entry is superseded when its evidence producer digest differs from the current
one; a decision entry when its structure producer digest differs. Current keys, every other
stage's caches, gold and outputs are never touched. caching.py is unchanged.

Usage: python step10_housekeeping.py [--apply]
"""

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
OUT = ROOT / "experiments/out/step10"
CACHE = ROOT / ".cache"


def size(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else (
        path.stat().st_size if path.exists() else 0
    )  # fmt: skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from book_core.structure.keys import evidence_code_digest, structure_code_digest

    evidence_now, structure_now = evidence_code_digest(), structure_code_digest()
    superseded = []
    for path in sorted((CACHE / "step10/structure/evidence").glob("*.json.gz")):
        header = gzip.decompress(path.read_bytes()).split(b"\n", 1)[1]
        inputs = json.loads(header)["cache_key_inputs"]
        if inputs.get("evidence_producer_sha256") != evidence_now:
            superseded.append(path)
    for path in sorted((CACHE / "step10/structure/book").glob("*.json")):
        payload = json.loads(json.loads(path.read_text("utf-8"))["payload"])
        if payload["cache_key_inputs"].get("structure_producer_sha256") != structure_now:
            superseded.append(path)
    freed = sum(p.stat().st_size for p in superseded)
    if args.apply:
        for path in superseded:
            path.unlink()
    report = {
        "applied": args.apply,
        "deleted" if args.apply else "would_delete": [p.relative_to(ROOT).as_posix()
                                                      for p in superseded],
        "freed_bytes": freed,
        "cache_use_bytes": {p.name: size(p) for p in sorted(CACHE.iterdir()) if p.is_dir()},
        "rule": "only Step 10 entries whose producer digest is superseded",
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "housekeeping.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in report.items()}, indent=1))


if __name__ == "__main__":
    main()
