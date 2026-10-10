"""Step 11 housekeeping and disk check before the book 4 hold-out run.

Deletes only Step 11 development cache entries whose key is superseded (not the key in a
current book summary); never current keys, gold or outputs. Estimates book 4's Step 11 cache
from its page count and book 1's per-page Step 11 cache size (x 1.25) and stops when the
estimate exceeds free space minus 5 GB (owner rule, Step 10b). Writes
experiments/out/step11/housekeeping.json.

Usage: python step11_housekeeping.py [--apply]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))

CACHE = ROOT / ".cache/step11/lists"
OUT = ROOT / "experiments/out/step11"
BOOK4_PAGES = 314


def size(path):
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else (
        path.stat().st_size)  # fmt: skip


def main():
    from book_core.lists.keys import book_fingerprint

    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    current = {}
    for summary in OUT.glob("*/summary.json"):
        data = json.loads(summary.read_text("utf-8"))
        current[book_fingerprint(data["cache_key_inputs"])] = data["book"]
    removed, kept = [], []
    for path in sorted((CACHE / "book").glob("*.json")):
        key = path.stem
        page_dir = CACHE / "page" / key
        bytes_ = size(path) + (size(page_dir) if page_dir.exists() else 0)
        row = {"key": key, "book": current.get(key), "bytes": bytes_}
        if key in current:
            kept.append(row)
            continue
        removed.append(row)
        if args.apply:
            path.unlink()
            if page_dir.exists():
                shutil.rmtree(page_dir)
    book1 = next(r for r in kept if r["book"] == "spanish_us_history")
    estimate = book1["bytes"] / 758 * BOOK4_PAGES * 1.25
    free = shutil.disk_usage(ROOT).free
    report = {
        "applied": args.apply, "removed": removed, "kept": kept,
        "removed_bytes": sum(r["bytes"] for r in removed),
        "book4_estimate_bytes": round(estimate), "free_bytes": free,
        "fits_free_minus_5gb": estimate <= free - 5 * 1024**3,
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "housekeeping.json").write_text(json.dumps(report, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"removed", "kept"}}, indent=1))
    if not report["fits_free_minus_5gb"]:
        raise SystemExit("Book 4 estimate exceeds free space minus 5 GB: stop")


if __name__ == "__main__":
    main()
