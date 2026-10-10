"""Step 11 overlays: lists, entries, terms, locators and glossary entry order.

Development pages (books 1 and 2): a bullet-list page, a nested numbered list (contents
levels), a glossary page, an index page, a question page, a reference-list page; and two
book 1 pages never inspected during Step 11 development (seeded draw). Uses the cached
Step 11 result (run step11_run.py first).

Usage: python step11_overlays.py
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step9_run import CACHE9
from step10_run import CACHE10, evidence_for, load_book
from step11_run import CACHE11, OUT

FIXED = {
    "spanish_us_history": {
        30: "bullet lists: a lead-in list and a question list (bullet on its own line)",
        8: "nested contents list: entries with indent levels",
        305: "nested list: Roman-numbered items with lettered sub-items (sidebar outline)",
        669: "bilingual glossary: entry by entry, page reference attached",
        687: "index page: entries, continuations across columns, locators",
        35: "numbered question items with lead terms (hanging continuation merged)",
    },
    "immigrant_children": {34: "reference list: hanging-indent bibliography entries"},
}
# Pages looked at while developing Step 11 (unseen pages are drawn from the rest).
INSPECTED = {8, 30, 35, 50, 107, 291, 305, 347, 497, 669, 687, 700} | set(range(664, 720))


def main():
    from book_core.debug.lists_overlay import render_lists_overlay
    from book_core.lists.cache import analyze_book_lists, load_page
    from book_core.structure.cache import analyze_book_structure

    rows = []
    for book, fixed in FIXED.items():
        loaded = load_book(book)
        source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
        evidence, key, _ = evidence_for(book, loaded)
        structure, _ = analyze_book_structure(evidence, key, CACHE10)
        result, hit = analyze_book_lists(
            lambda s=source, e=extractor: e.extract_pages(s), inputs, paragraphs, CACHE9,
            structure, furniture, CACHE11,
        )  # fmt: skip
        if not hit:
            raise SystemExit("Run step11_run.py first (lists not cached)")
        pages = dict(fixed)
        if book == "spanish_us_history":
            pool = [p for p in range(1, result.book.pages + 1)
                    if p not in INSPECTED and p not in fixed]  # fmt: skip
            for page in sorted(random.Random(11).sample(pool, 2)):
                pages[page] = "unseen page (seeded draw, never inspected)"
        for page in extractor.extract_pages(source):
            number = page.geometry.page
            if number not in pages:
                continue
            built = load_page(result, number, CACHE11)
            layout, _ = inputs(page)
            incoming = [(link["to_unit_id"], link["from_page"]) for link in result.page_links
                        if link["to_page"] == number]  # fmt: skip
            outgoing = [(link["from_unit_id"], link["to_page"]) for link in result.page_links
                        if link["from_page"] == number]  # fmt: skip
            raster = extractor.render_page(source, number, dpi=144)
            target = OUT / "overlays" / f"lists_{book}_p{number}.png"
            drawn = render_lists_overlay(raster, layout, built, result.book.lists, target,
                                         incoming, outgoing)  # fmt: skip
            rows.append({"book": book, "page": number, "what": pages[number], **drawn,
                         "output": target.relative_to(ROOT).as_posix()})  # fmt: skip
    (OUT / "overlays").mkdir(parents=True, exist_ok=True)
    (OUT / "overlays" / "overlays.json").write_text(json.dumps(rows, indent=1) + "\n", "utf-8")
    print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
