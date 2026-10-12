"""Step 11b diagnostics: a per-token table of one book (development books only).

For every retained PDF token: page, ordinal, NFKC text, visual line, the Step 9 unit
(id, kind), the Step 11 unit (id, kind, list id, list kind, level) and the reference unit
holding it (derived gold: kind, element path, list depth, table). Written as a gzipped
pickle for the boundary, navigation and heading analyses of docs/step11b_report.md.

Usage: python step11b_tokens.py --book medical_anatomy --out <file.pkl.gz>
"""

import argparse
import gzip
import pickle
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
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    from book_core.evaluation.derived_harness import DerivedGold
    from book_core.ledger.tokenization import line_tokens
    from book_core.lists.cache import analyze_book_lists, load_page
    from book_core.paragraphs.cache import load_page as load_step9
    from book_core.structure.cache import analyze_book_structure

    loaded = load_book(args.book)
    source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
    evidence, evidence_key, _ = evidence_for(args.book, loaded)
    structure, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    result, _ = analyze_book_lists(
        lambda: extractor.extract_pages(source), inputs, paragraphs, CACHE9, structure,
        furniture, CACHE11,
    )  # fmt: skip
    gold = DerivedGold.load(GOLD / args.book)
    ref = {}
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                ref[(page, ordinal)] = unit["unit"]
    list_kind = {}
    for lst in result.book.lists:
        list_kind[lst.id] = (lst.kind, lst.role)
    aliases = result.list_aliases
    rows, lines_out, units_out = [], {}, {}
    for page in extractor.extract_pages(source):
        number = page.geometry.page
        layout, _ = inputs(page)
        built = load_page(result, number, CACHE11)
        step9 = load_step9(paragraphs, number, CACHE9)
        span_line = {sid: line.id for line in layout.lines for sid in line.span_ids}
        for line in layout.lines:
            text = "".join(page.store.spans[s].raw_text for s in line.span_ids)
            spans = [page.store.spans[s] for s in line.span_ids]
            lines_out[(number, line.id)] = {
                "text": text, "bbox": (line.bbox.x0, line.bbox.y0, line.bbox.x1, line.bbox.y1),
                "size": line.font_size, "fonts": sorted({s.font for s in spans}),
                "flags": sorted({s.flags for s in spans}), "colors": sorted({s.color for s in spans}),
            }  # fmt: skip
        u11 = {lid: u for u in built.units for lid in u.line_ids}
        u9 = {lid: u for u in step9.units for lid in u.line_ids}
        for u in built.units:
            lid = aliases.get(u.list_id, u.list_id) if u.list_id else None
            units_out[u.id] = {
                "page": number, "kind": u.kind, "list": lid, "level": u.level,
                "list_kind": list_kind.get(lid) or list_kind.get(u.list_id),
                "lines": list(u.line_ids), "sources": list(u.source_unit_ids),
                "reasons": list(u.boundary.reasons), "confidence": u.boundary.confidence,
                "marker": u.marker.type if u.marker else None, "stream": u.stream_kind,
            }  # fmt: skip
        for u in step9.units:
            units_out.setdefault(("s9", u.id), {"kind": u.kind, "lines": list(u.line_ids),
                                                "reasons": list(u.boundary.reasons)})  # fmt: skip
        ordinal = 0
        for line in page.store.lines:
            raw = page.store.raw_line_text(line)
            if not raw.strip() or not page.geometry.content_bbox.contains_center(
                line.bbox
            ):
                continue
            for token in line_tokens(page.store, line):
                lid = next(
                    (span_line[s] for s in token.span_ids if s in span_line), None
                )
                a, b = u11.get(lid), u9.get(lid)
                rows.append((number, ordinal, token.value, lid,
                             b.id if b else None, b.kind if b else None,
                             a.id if a else None, a.kind if a else None,
                             ref.get((number, ordinal))))  # fmt: skip
                ordinal += 1
    gold_units = {u["unit"]: u for u in gold.units}
    with gzip.open(args.out, "wb") as handle:
        pickle.dump(
            {"rows": rows, "lines": lines_out, "units": units_out, "gold": gold_units,
             "navigation": [(n.page, n.kind, n.confidence) for n in structure.navigation_pages],
             "profile": structure.profile},
            handle,
        )  # fmt: skip
    print(len(rows), "tokens")


if __name__ == "__main__":
    main()
