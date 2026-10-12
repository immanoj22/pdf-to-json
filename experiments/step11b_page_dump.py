"""Step 11b diagnostics: the streams, Step 9 units and Step 11 units of a few pages.

Prints each stream of the page in reading order, line by line: line start/block in the line's
reading frame, Step 9 unit and kind, Step 11 unit, kind, level and the unit's first reason.

Usage: python step11b_page_dump.py --book spanish_us_history --pages 687 688
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step9_run import CACHE9
from step10_run import CACHE10, GOLD, evidence_for, load_book
from step11_run import CACHE11


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--pages", type=int, nargs="+", required=True)
    args = parser.parse_args()

    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.evaluation.furniture import token_lines
    from book_core.ledger.tokenization import line_tokens
    from book_core.lists.cache import analyze_book_lists, load_page
    from book_core.paragraphs.cache import load_page as load_step9
    from book_core.paragraphs.geometry import frame
    from book_core.structure.cache import analyze_book_structure

    loaded = load_book(args.book)
    source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
    evidence, evidence_key, _ = evidence_for(args.book, loaded)
    structure, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    result, _ = analyze_book_lists(
        lambda: extractor.extract_pages(source), inputs, paragraphs, CACHE9, structure,
        furniture, CACHE11,
    )  # fmt: skip
    navigation = {n.page: n.kind for n in structure.navigation_pages}
    gold = DerivedGold.load(GOLD / args.book)
    wanted = set(args.pages)
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        if number not in wanted:
            continue
        layout, _ = inputs(page)
        lines = {line.id: line for line in layout.lines}
        built = load_page(result, number, CACHE11)
        step9 = load_step9(paragraphs, number, CACHE9)
        u11 = {lid: u for u in built.units for lid in u.line_ids}
        u9 = {lid: u for u in step9.units for lid in u.line_ids}
        print(f"=== page {number} navigation {navigation.get(number)}")
        for stream in built.order.streams:
            print(f"--- stream {stream.kind} {stream.id[:8]}")
            for lid in stream.line_ids:
                line = lines[lid]
                f = frame(line)
                text = "".join(page.store.spans[s].raw_text for s in line.span_ids)
                a, b = u11[lid], u9[lid]
                first = a.line_ids[0] == lid
                print(
                    f"{f.start:6.1f} {f.block:6.1f} s9={b.id[:6]}:{b.kind[:9]:9s} "
                    f"s11={a.id[:6]}:{a.kind[:10]:10s} L{a.level} "
                    f"{(a.boundary.reasons[0][:40] if first else ''):40s} | {text[:70]!r}"
                )
        # Reference units with tokens on this page that no single unit of ours holds exactly.
        owners = token_lines(page, layout)
        values = [t.value for line in page.store.lines
                  if page.store.raw_line_text(line).strip()
                  and page.geometry.content_bbox.contains_center(line.bbox)
                  for t in line_tokens(page.store, line)]  # fmt: skip
        mine = {}
        for i, lid in enumerate(owners):
            if lid in u11:
                mine.setdefault(u11[lid].id, set()).add(i)
        print("--- reference units not matched exactly")
        for unit in gold.units:
            tokens = {
                o for p, f, n in unit["pdf"] if p == number for o in range(f, f + n)
            }
            if not tokens or unit["kind"] in {"heading", "image_description"}:
                continue
            ours = {u11[owners[o]].id for o in tokens if owners[o] in u11}
            if len(ours) == 1 and mine[next(iter(ours))] == tokens:
                continue
            words = " ".join(values[o] for o in sorted(tokens))
            print(f"{unit['kind']}: {len(ours)} units of ours | {words[:110]}")


if __name__ == "__main__":
    main()
