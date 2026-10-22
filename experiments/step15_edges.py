"""Step 15 diagnostics: the main-flow items at a page break (inspection only).

For each page p given, prints the last main-flow items of p and the first of p + 1 from a
final archive: owner kind, stream, number of lines and the head/tail of the text, and the
units' cross-page links.

Usage: python step15_edges.py --book NAME --pages 25 38 [--capture DIR] [--items 3]
"""

# ruff: noqa: E402
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step14a_common as common
import step14b_common  # noqa: F401
import step15_common as c15

from book_core.cache_store import read_json


def view(book, capture, number):
    run = c15.capture_run(capture)(book)
    payload = read_json(Path(run["output"]) / f"page_{number:06d}.json.gz")
    return c15.PageView(number, payload, common.layout_page(book, number)), payload


def describe(page, who, kind, tail):
    if kind == "table":
        return f"  [table] {who[:8]}"
    unit = page.units[who]
    lines = unit["line_ids"]
    text = page.text(lines[-1] if tail else lines[0]).strip()
    text = ("..." + text[-70:]) if tail else (text[:70] + "...")
    came, to = page.links.get(who, (None, None))
    link = (" <-" if came else "") + (" ->" if to else "")
    return f"  [{kind}/{unit['stream_kind']}] {who[:8]} {len(lines)}L{link} | {text}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--pages", type=int, nargs="+", required=True)
    parser.add_argument("--capture", default=str(ROOT / "experiments/out/step14b/final"))
    parser.add_argument("--items", type=int, default=3)
    args = parser.parse_args()
    for number in args.pages:
        a, _ = view(args.book, args.capture, number)
        b, _ = view(args.book, args.capture, number + 1)
        print(f"=== {args.book} p{number} -> p{number + 1}")
        for who, kind in a.main[-args.items :]:
            print(describe(a, who, kind, True))
        print("  ---- page break")
        for who, kind in b.main[: args.items]:
            print(describe(b, who, kind, False))
