"""Step 15 diagnostics: reference units holding the last tokens of page p and the first of p+1
(inspection only). Usage: python step15_refdump.py --book NAME --pages 123 46"""

# ruff: noqa: E402
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common as c14b

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--pages", type=int, nargs="+", required=True)
    args = parser.parse_args()
    gold = common.derived_gold(args.book)
    owner = {}
    for u in gold.units:
        for p, first, n in u["pdf"]:
            for o in range(first, first + n):
                owner[(p, o)] = u
    for number in args.pages:
        for page, tail in ((number, True), (number + 1, False)):
            texts = c14b.token_texts(args.book, page)
            seen = []
            rng = range(len(texts) - 1, -1, -1) if tail else range(len(texts))
            for o in rng:
                u = owner.get((page, o))
                key = u["unit"] if u else None
                if key not in [s[0] for s in seen]:
                    seen.append(
                        (key, u["kind"] if u else None, u["path"][-45:] if u else "", texts[o])
                    )
                if len(seen) >= 4:
                    break
            print(page, "tail" if tail else "head", seen)
