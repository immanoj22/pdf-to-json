"""A stand-in for ``book_core run-book`` used by the app tests: same command line, same
output layout (book-<key>/book.json, images/), the cache stage folders and the failure
record. The mode comes from BOOK_APP_FAKE_MODE: ok | fail | slow."""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "src"))

STAGES = ["native", "analysis", "paint", "text", "layout", "reading_order"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--workers")
    ap.add_argument("--parts")
    args = ap.parse_args()
    mode = os.environ.get("BOOK_APP_FAKE_MODE", "ok")
    if (Path(args.source).parent / "FAIL").exists():  # one book of a queue fails
        mode = "fail"
    time.sleep(float(os.environ.get("BOOK_APP_FAKE_DELAY", "0")))  # a conversion takes a while
    cache = Path(args.cache_dir)
    for stage in STAGES[:3]:
        (cache / stage).mkdir(parents=True, exist_ok=True)
        time.sleep(0.05)
    if mode == "slow":
        (cache / "tmpfile").write_text("partial")
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "partial.txt").write_text("partial")
        time.sleep(120)
        return 0
    if mode == "fail":
        (cache / "failures").mkdir(parents=True, exist_ok=True)
        (cache / "failures" / "20261104T000000Z.json").write_text(
            json.dumps(
                {
                    "stage": "layout",
                    "page": 4,
                    "error_type": "ValueError",
                    "message": "page 4 has no readable text layer",
                }
            )
        )
        print("Traceback (most recent call last):\n  File x\nValueError: boom", file=sys.stderr)
        return 1
    from tests_adapters.adapter_fixtures import build_references, build_sample

    out = Path(args.out) / "book-0123abcd"
    parts = json.loads(Path(args.parts).read_text()) if args.parts else {}
    if parts.get("bibliography") and not parts.get("body"):  # told: the whole PDF is a reference list
        build_references(out)
    else:
        build_sample(out)
    shutil.rmtree(Path(args.out) / "partial.txt", ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
