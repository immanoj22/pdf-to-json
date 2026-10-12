"""Step 11b: why set-off markers are dropped by the repetition evidence, per cause.

Runs the Step 11 lists stage of one book into a temporary cache (the producer cache is not
touched) with ``PageLister.general`` instrumented: every set-off marker (a glyph in a span
of its own, ``lines.set_off_marker``) that is dropped for lack of a second aligned line with
its signature in the block is classed as

- (a) signature mismatch: the block holds an aligned line with the same glyph and mark font
  (and colour) but a different font for the following text;
- (b) block boundary: an aligned line of the same page with the same signature exists, but
  in another block;
- (c) single: neither (a lone marked line on the page).

Usage: python step11b_marker_gap.py --book medical_anatomy --scratch <dir>
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
sys.path.insert(0, str(ROOT / "experiments"))

from step9_run import CACHE9
from step10_run import CACHE10, evidence_for, load_book

OUT = ROOT / "experiments/out/step11b/marker_gap"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()

    import book_core.lists.page as page_module
    from book_core.lists.cache import analyze_book_lists
    from book_core.structure.cache import analyze_book_structure

    found = defaultdict(list)
    original = page_module.PageLister.general

    def colour(lister, line):
        sid = next(s for s, a, b, *_ in line.spans if a <= line.marker.start < b)
        return lister.page.store.spans[sid].color

    def general(self, block, edge_kind):
        ids = {line.id for line in block}
        for line in block:
            m = line.marker
            if m is None or len(m.signature) != 4:
                continue
            glyph = m.signature[1]
            if glyph in page_module.CLASSIC_BULLETS:
                continue

            def aligned(x, line=line):
                return (x.id != line.id and x.marker is not None
                        and abs(x.start - line.start) <= 0.5 * line.size)  # fmt: skip

            if any(aligned(x) and x.marker.signature == m.signature for x in block):
                continue  # kept by the repetition evidence
            mine = (*m.signature[:3], colour(self, line))
            if any(aligned(x) and len(x.marker.signature) == 4
                   and (*x.marker.signature[:3], colour(self, x)) == mine for x in block):  # fmt: skip
                cause = "a_signature_mismatch"
            elif any(aligned(x) and x.id not in ids and x.marker.signature == m.signature
                     for x in self.evidence.values()):  # fmt: skip
                cause = "b_block_boundary"
            else:
                cause = "c_single"
            found[cause].append({"page": self.page.geometry.page, "glyph": glyph,
                                 "mark_font": m.signature[2], "text_font": m.signature[3],
                                 "line": line.raw.strip()[:80]})  # fmt: skip
        return original(self, block, edge_kind)

    page_module.PageLister.general = general
    loaded = load_book(args.book)
    source, extractor, inputs, furniture, _, paragraphs, _, _ = loaded
    evidence, evidence_key, _ = evidence_for(args.book, loaded)
    structure, _ = analyze_book_structure(evidence, evidence_key, CACHE10)
    analyze_book_lists(
        lambda: extractor.extract_pages(source), inputs, paragraphs, CACHE9, structure,
        furniture, Path(args.scratch),
    )  # fmt: skip
    report = {
        "book": args.book,
        "dropped_set_off_markers": {k: len(v) for k, v in sorted(found.items())},
        "glyphs": {
            k: dict(Counter(r["glyph"] for r in v).most_common())
            for k, v in found.items()
        },
        "examples": {k: v[:10] for k, v in sorted(found.items())},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.book}.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", "utf-8"
    )
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
