"""Step 10 overlays (book 1): headings with level and role, styled non-headings, zone band.

A unit opener, a lesson page, p26, a sidebar page, a contents page, an index page and two
pages never inspected during development (seeded draw). Uses the cached Step 10 decision.
Usage: python step10_overlays.py
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step9_run import CACHE9  # noqa: E402
from step10_run import CACHE10, OUT, evidence_for, heading_classifier, load_book  # noqa: E402

FIXED = {
    25: "unit opener (TEMA 1)",
    31: "lesson page: lesson title, reading-strategy box, display titles",
    26: "p26: lesson 01 page with the Iroquois display title",
    119: "sidebar page: biography box title",
    7: "table of contents",
    690: "index page",
}
# Pages looked at while developing Step 10 (unseen pages come from the rest).
INSPECTED = set(range(1, 32)) | set(range(37, 80)) | set(range(85, 120)) | {161, 171, 175}
INSPECTED |= set(range(581, 601)) | set(range(645, 691)) | set(range(719, 728)) | {735, 755}
INSPECTED |= {104, 133, 140, 145, 191, 213, 215, 257, 299, 351, 391, 409, 486, 501, 539, 589}


def main():
    from book_core.debug.structure_overlay import render_structure_overlay
    from book_core.paragraphs.cache import load_page
    from book_core.structure.cache import analyze_book_structure

    loaded = load_book("spanish_us_history")
    source, extractor, inputs, _, _, paragraphs, _, _ = loaded
    evidence, key, _ = evidence_for("spanish_us_history", loaded)
    structure, hit = analyze_book_structure(
        evidence, key, CACHE10, classifier=heading_classifier()
    )
    if not hit:
        raise SystemExit("Run step10_run.py first (decision not cached)")
    rng = random.Random(10)
    pool = [p for p in range(1, structure.pages + 1) if p not in INSPECTED and p not in FIXED]
    pages = dict(FIXED)
    for page in sorted(rng.sample(pool, 2)):
        pages[page] = "unseen page (seeded draw, never inspected)"
    rows = []
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        if number not in pages:
            continue
        built = load_page(paragraphs, number, CACHE9)
        layout, _ = inputs(page)
        units_of = {u.id: u.line_ids for u in built.units}
        raster = extractor.render_page(source, number, dpi=144)
        target = OUT / "overlays" / f"structure_p{number}.png"
        drawn = render_structure_overlay(raster, layout, units_of, structure, number, target)
        rows.append({"page": number, "what": pages[number], **drawn,
                     "output": target.relative_to(ROOT).as_posix()})  # fmt: skip
    (OUT / "overlays" / "overlays.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
