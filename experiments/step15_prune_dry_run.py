"""Step 15 disk: a dry-run list of cache entries a Step 15 run has superseded (deletes nothing).

For each book whose Step 15 final run exists, the registry entries of the stages that run
re-keyed (lists and every later stage) that the Step 14b final capture used are listed with
their bytes: the Step 15 run has written the current entries of those stages, so they are
superseded. They are referenced only by the tracked Step 14b capture files (performance
records); Step 15 evaluation reads the Step 14b final archives (kept) and the unchanged
layout caches, never these. The Step 14b final archives, current entries, gold, and every
earlier stage's caches are not listed. Deleting needs the owner's approval
(``--apply`` re-plans and deletes exactly the listed files).

Usage: python step15_prune_dry_run.py [--apply]
"""

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common

from book_core.cache_store import read_json
from book_core.lists.keys import book_fingerprint

CACHE = ROOT / ".cache"
OUT = ROOT / "experiments/out/step15/cache_prune_dry_run.json"
STAGES = ("lists", "characters", "figures", "equations", "mathml", "tables")


def plan():
    index = read_json(CACHE / ".cache-index.json")
    current = set(index["current"].values())
    protected = {n for key in current for n in index["entries"][key]["files"]}
    entries, total = [], 0
    for book in common.BOOK_ORDER:
        new = ROOT / f"experiments/out/step15/final/performance/{book}.json"
        if not new.exists():
            continue
        old_run = common.read(ROOT / f"experiments/out/step14b/final/performance/{book}.json")
        old_keys = old_run["run"]["cache_keys"]
        new_keys = common.read(new)["run"]["cache_keys"]
        sha = read_json(Path(old_run["run"]["output"]) / "manifest.json.gz")["source_sha256"]
        for stage in STAGES:
            old, now = (k if isinstance(k, str) else book_fingerprint(k)
                        for k in (old_keys[stage], new_keys[stage]))  # fmt: skip
            if old == now:
                continue
            for key, entry in index["entries"].items():
                if (entry["book"], entry["stage"], entry["key"]) != (sha, stage, old):
                    continue
                if key in current:
                    continue
                files = [n for n in entry["files"] if n not in protected]
                size = sum((CACHE / n).stat().st_size for n in files if (CACHE / n).exists())
                entries.append({"book": book, "stage": stage, "key": old, "files": len(files),
                                "bytes": size, "names": files})  # fmt: skip
                total += size
    return {"rule": "Step 14b stage caches (lists and later) superseded by a Step 15 run of the "
                    "same book; Step 14b final archives kept",
            "entries": entries, "total_bytes": total}  # fmt: skip


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    found = plan()
    brief = {**found, "entries": [{k: v for k, v in e.items() if k != "names"}
                                  for e in found["entries"]]}  # fmt: skip
    if args.apply:
        saved = json.loads(OUT.read_text("utf-8"))
        if [e["names"] for e in saved["entries"]] != [e["names"] for e in found["entries"]]:
            raise SystemExit("The cache changed since the dry run; make a new dry run")
        for entry in found["entries"]:
            for name in entry["names"]:
                path = CACHE / name
                if path.exists():
                    path.unlink()
        found["deleted"] = True
    common.write(OUT, found)
    print(json.dumps(brief, indent=1)[:3000], round(found["total_bytes"] / 1e9, 2), "GB")
