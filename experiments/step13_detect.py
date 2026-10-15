"""Step 13: cache Heron and PP-DocLayoutV3 regions for every page of one Step 13 book.

Same adapters, cache, render and threshold as Step 12 (``step12_detect``); the registry adds
the math development book. Evidence only.

Usage: python step13_detect.py --book statistics
"""

# ruff: noqa: E402
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step12_detect
from step13_books import BOOKS

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=BOOKS)
    args = parser.parse_args()
    step12_detect.BOOKS = BOOKS
    step12_detect.OUT = ROOT / "experiments/out/step13/detection"
    step12_detect.run(args.book)
