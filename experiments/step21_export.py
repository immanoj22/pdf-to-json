"""Step 21: export one converted book with the adapter and check its bibliography.

Usage: python step21_export.py BOOK_DIR OUT_DIR [--profile jaypee_v5] [--entries 112]
BOOK_DIR holds book.json (a converter publication). Prints the Stage 1 and the delivery
checks of ``step21_bibliography``.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]

from book_adapters.engine.run import run_book
from step21_bibliography import check, check_delivery, delivery_ok, ok


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_dir", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--profile", default="jaypee_v5")
    parser.add_argument("--entries", type=int, default=112)
    args = parser.parse_args()
    report = run_book(args.book_dir, args.out, None, args.profile,
                      allow_alt_text_placeholders=True)  # fmt: skip
    root = Path(report["root"])
    book = json.loads((args.book_dir / "book.json").read_text("utf-8"))
    stage1 = check(book, args.entries)
    delivery = check_delivery(root, args.entries)
    print(json.dumps({"stage1": {**stage1, "ok": ok(stage1)},
                      "delivery": {**delivery, "ok": delivery_ok(delivery, args.entries)},
                      "dtd_errors": report["checks"]["dtd"]["errors"],
                      "lossless_missing": report["checks"]["lossless"]["missing"]}, indent=1))


if __name__ == "__main__":
    main()
