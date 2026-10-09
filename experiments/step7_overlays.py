"""Step 7 overlays: numbered main flow, float streams and anchors, low-confidence flags.

Uses the frozen cached reading orders of book 1 (vocabulary rebuilt with the same Step 6 rule and
checked against the run summary's digest). Fixed pages plus three pages never inspected during
development, drawn with a fixed seed. Usage: python step7_overlays.py
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from reference_paths import reference_path  # noqa: E402
from step7_layouts import CACHE  # noqa: E402

OUT = ROOT / "experiments/out/step7"
FIXED = {
    26: "two columns, pull quote inset",
    100: "column continuation, chart box at page start",
    465: "two columns then cards (NAACP chronology)",
    669: "bilingual glossary, row-synchronised lanes",
    696: "index columns Step 4 left in one lane",
}
# Pages looked at while tuning on book 1; unseen pages are drawn from the rest.
INSPECTED = {2, 4, 6, 8, 9, 10, 26, 100, 119, 145, 203, 248, 290, 314, 324, 335, 366, 375, 389}
INSPECTED |= {464, 465, 500, 553, 564, 577, 654, 666, 667, 669, 672, 675, 682, 688, 693, 696}
INSPECTED |= {705, 713, 716, 719, 725, 727}


def main():
    from book_core.debug.reading_order_overlay import render_reading_order_overlay
    from book_core.document_analysis.vocabulary import build_vocabulary
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    from book_core.objects.analysis import cached_repetition
    from book_core.reading_order.cache import analyze_reading_order, vocabulary_digest

    summary = json.loads((OUT / "spanish_us_history/summary.json").read_text("utf-8"))
    per_page = json.loads((OUT / "spanish_us_history/per_page.json").read_text("utf-8"))
    source = reference_path("spanish_pdf")
    extractor = PyMuPDFExtractor(device="cpu")
    repetition = cached_repetition(source, extractor, CACHE)
    vocabulary_file = CACHE / "step7_vocabulary.json"
    if vocabulary_file.exists():
        vocabulary = json.loads(vocabulary_file.read_text("utf-8"))
    else:
        from book_core.layout.pipeline import analyze_layout

        counts = Counter()
        for page in range(1, summary["pages"] + 1):
            native = analyze_layout(source, page, extractor, repetition, CACHE)[1].native.page
            counts.update(build_vocabulary([native])["casefold_frequencies"])
        vocabulary = dict(counts)
        vocabulary_file.write_text(json.dumps(vocabulary, ensure_ascii=False), "utf-8")
    if vocabulary_digest(vocabulary) != summary["vocabulary_sha256"]:
        raise ValueError("Vocabulary differs from the frozen run")
    candidates = sorted(
        int(page)
        for page, row in per_page.items()
        if int(page) not in INSPECTED and (row["main_units"] or 0) >= 15
    )
    with_floats = [p for p in candidates if per_page[str(p)]["float_anchor"] is not None]
    rng = random.Random(7)
    unseen = rng.sample(with_floats, 2) + rng.sample(sorted(set(candidates) - set(with_floats)), 1)
    pages = {**FIXED, **{p: "unseen page (seeded draw, never inspected)" for p in unseen}}
    rows = []
    for page, note in pages.items():
        order, layout, _ = analyze_reading_order(
            source, page, extractor, repetition, CACHE, vocabulary
        )
        raster = extractor.render_page(source, page, dpi=144)
        target = OUT / "overlays" / f"reading_order_p{page}.png"
        result = render_reading_order_overlay(raster, layout, order, target)
        rows.append(
            {
                "page": page,
                "note": note,
                "path": str(target.relative_to(ROOT)).replace("\\", "/"),
                "metrics": per_page[str(page)],
                "low_confidence": sum(d.review_required for d in order.decisions),
                **{k: v for k, v in result.items() if k != "output"},
            }
        )
        print(page, note, result)
    (OUT / "overlays/overlays.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")


if __name__ == "__main__":
    main()
