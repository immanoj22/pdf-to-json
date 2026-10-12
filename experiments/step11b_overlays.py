"""Step 11b overlays: four book 4 pages (a list page, the index, a chapter opener, an
objectives or question page), drawn with the Step 11 lists overlay from the cached Step 11
result of the current producers (run step11b_run.py first).

Usage: python step11b_overlays.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import step11_overlays

OUT = ROOT / "experiments/out/step11b"
PAGES = {
    "medical_anatomy": {
        242: "list page: set-off bullets (symbol glyph against the text)",
        306: "index page: space-separated locators, sub-entries, four columns",
        41: "chapter opener: banner title, learning objectives, sections",
        56: "review and multiple-choice questions",
    }
}


def main():
    step11_overlays.FIXED = PAGES
    step11_overlays.OUT = OUT
    step11_overlays.main()
    rows = json.loads((OUT / "overlays" / "overlays.json").read_text("utf-8"))
    print(len(rows), "overlays")


if __name__ == "__main__":
    main()
