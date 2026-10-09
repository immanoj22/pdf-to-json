"""Step 8 overlays: furniture classes, folio with its fitted label, flagged lines (book 1).

Uses the cached book decision and page results of step8_run.py. Fixed pages (glossary, index,
chapter opener, map) plus two pages never inspected during development, drawn with a fixed
seed. Usage: python step8_overlays.py
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step7_layouts import CACHE  # noqa: E402
from step8_run import CACHE8, OUT, vocabulary_for  # noqa: E402

FIXED = {
    669: "glossary: guide-word running head, running foot, folio",
    696: "index: guide-word running head; Step 4 false furniture returned to the flow",
    25: "chapter opener: folio 1; CONÉCTATE repeated box",
    662: "map page: edge map labels stay content",
}
# Pages looked at while developing Step 8 on book 1; unseen pages come from the rest.
INSPECTED = {4, 5, 7, 15, 25, 26, 29, 30, 31, 33, 37, 89, 100, 104, 113, 116, 119, 157, 177}
INSPECTED |= {183, 209, 215, 217, 220, 239, 251, 257, 259, 267, 301, 311, 338, 353, 356, 393}
INSPECTED |= {438, 456, 462, 464, 467, 469, 474, 479, 483, 506, 541, 544, 552, 586, 611, 651}
INSPECTED |= {653, 662, 667, 669, 673, 685, 686, 688, 689, 690, 692, 695, 696, 702, 707, 708}
INSPECTED |= {723, 747, 757}


def main():
    from book_core.debug.furniture_overlay import render_furniture_overlay
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import analyze_book_furniture, page_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition

    source = reference_path("spanish_pdf")
    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE)
    inputs = PageInputs(source, extractor, repetition, CACHE, vocabulary_for("spanish_us_history"))
    metadata = cached_metadata(source, extractor, CACHE8 / "metadata")
    decisions, key, hit = analyze_book_furniture(
        extractor.extract_pages(source), inputs, metadata, CACHE8
    )
    if not hit:
        raise SystemExit("Run step8_run.py first (book decision not cached)")
    candidates = [
        m.page for m in decisions.book.markers if m.page not in INSPECTED and m.source == "printed"
    ]
    rng = random.Random(8)
    unseen = sorted(rng.sample(candidates, 2))
    pages = {**FIXED, **{p: "unseen page (seeded draw, never inspected)" for p in unseen}}
    rows = []
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        if number not in pages:
            continue
        result = page_furniture(page, inputs, decisions, key, CACHE8)
        layout, _ = inputs(page)
        raster = extractor.render_page(source, number, dpi=144)
        target = OUT / "overlays" / f"furniture_p{number}.png"
        drawn = render_furniture_overlay(raster, layout, result, target)
        rows.append(
            {
                "page": number,
                "note": pages[number],
                "path": str(target.relative_to(ROOT)).replace("\\", "/"),
                "marker": result.marker.model_dump(),
                **{k: v for k, v in drawn.items() if k != "output"},
            }
        )
        print(number, pages[number], drawn)
    rows.sort(key=lambda r: list(pages).index(r["page"]))
    (OUT / "overlays/overlays.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
