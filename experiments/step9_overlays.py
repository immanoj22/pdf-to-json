"""Step 9 overlays (book 1): paragraphs boxed and numbered, joins, hyphen decisions, flags.

Pages 26, 100, 465, a glossary page, a page with a cross-page continuation, and three pages
never inspected during development (seeded draw). Uses the cached Step 9 book result.
Usage: python step9_overlays.py
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
from step8_run import CACHE8, step6_artifact, vocabulary_for  # noqa: E402
from step9_run import CACHE9, OUT, navigation_map  # noqa: E402

FIXED = {
    26: "two columns; the Gobernantes paragraph wrapped around the pull quote",
    100: "column continuation into the right column",
    465: "two columns, then cards",
    669: "bilingual glossary",
}
# Pages looked at while developing Step 9 on book 1 (unseen pages come from the rest).
INSPECTED = {24, 26, 33, 35, 36, 44, 45, 46, 47, 58, 60, 62, 74, 84, 122, 130, 135, 136, 137}
INSPECTED |= {138, 151, 153, 176, 196, 206, 216, 229, 248, 254, 260, 270, 322, 347, 349, 352}
INSPECTED |= {370, 391, 424, 436, 440, 458, 488, 490, 501, 551, 555, 594, 614, 616, 617, 642}
INSPECTED |= {666, 669, 678, 685, 686, 687, 688, 689, 690, 691, 693, 696, 697, 719, 724, 725}
INSPECTED |= {729, 738, 747, 749, 752}


def main():
    from book_core.debug.paragraph_overlay import render_paragraph_overlay
    from book_core.document_analysis.metadata import cached_metadata
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.furniture.cache import load_book_furniture
    from book_core.furniture.inputs import PageInputs
    from book_core.objects.analysis import cached_repetition
    from book_core.paragraphs.cache import analyze_book_paragraphs, load_page

    source = reference_path("spanish_pdf")
    extractor = PyMuPDFExtractor(device="cpu")
    inputs = PageInputs(
        source, extractor, cached_repetition(source, extractor, CACHE), CACHE,
        vocabulary_for("spanish_us_history"),
    )  # fmt: skip
    metadata = cached_metadata(source, extractor, CACHE8 / "metadata")
    furniture, furniture_key = load_book_furniture(inputs, metadata, CACHE8)
    artifact, _ = step6_artifact(inputs.digest)
    result, hit = analyze_book_paragraphs(
        lambda: extractor.extract_pages(source), inputs, furniture, furniture_key, CACHE8,
        navigation_map(artifact), CACHE9,
    )  # fmt: skip
    if not hit:
        raise SystemExit("Run step9_run.py first (book result not cached)")
    joins = result.book.page_joins
    crossing = sorted({j.to_page for j in joins if j.to_page not in INSPECTED})
    rng = random.Random(9)
    pages = dict(FIXED)
    pages[rng.choice(crossing)] = "paragraph continued from the previous page"
    pool = [p for p in range(1, result.book.pages + 1) if p not in INSPECTED and p not in pages]
    for page in sorted(rng.sample(pool, 3)):
        pages[page] = "unseen page (seeded draw, never inspected)"
    rows = []
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        if number not in pages:
            continue
        built = load_page(result, number, CACHE9)
        layout, _ = inputs(page)
        incoming = [(j.to_unit_id, j.from_page) for j in joins if j.to_page == number]
        outgoing = [(j.from_unit_id, j.to_page) for j in joins if j.from_page == number]
        raster = extractor.render_page(source, number, dpi=144)
        target = OUT / "overlays" / f"paragraphs_p{number}.png"
        drawn = render_paragraph_overlay(raster, layout, built, target, incoming, outgoing)
        rows.append({
            "page": number, "note": pages[number],
            "path": str(target.relative_to(ROOT)).replace("\\", "/"),
            "incoming_page_joins": len(incoming), "outgoing_page_joins": len(outgoing),
            **{k: v for k, v in drawn.items() if k != "output"},
        })  # fmt: skip
        print(number, pages[number], drawn)
    rows.sort(key=lambda r: list(pages).index(r["page"]))
    (OUT / "overlays/overlays.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
