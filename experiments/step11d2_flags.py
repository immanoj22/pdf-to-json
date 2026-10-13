"""Character flags alone on the frozen Step 11e baseline inputs, approved books only.

The product character stage reads native spans, layout lines and final list units and writes
flags that no other stage reads. Running it on the frozen baseline caches therefore measures
the flags alone: every other output is the baseline by construction. For comparison, the
script also counts the stricter initial name comparison (NFKC only, no case or format
exemption) on the same attributed glyphs.
"""

# ruff: noqa: E402
import argparse
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import pymupdf
import step11c_identity as identity
from reference_paths import reference_path
from step7_layouts import BOOKS
from step11d2_hidden import write
from step11d2_run import BASE, CACHE, CACHE11, read

from book_core.characters.cache import CONFIG, VERSION, decide, observe_page
from book_core.characters.glyphs import glyph_events, span_glyphs
from book_core.characters.rules import name_codepoint
from book_core.layout.models import PageLayout
from book_core.lists.cache import BookListsResult
from book_core.lists.cache import load_page as list_page
from book_core.lists.keys import book_fingerprint
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.run_context import open_source, source_session

OUT = ROOT / "experiments/out/step11d2/flags"


def strict_disagreements(page, pdf_page):
    """Initial comparison: NFKC only. Returns {(span, offset): (name, decoded)}."""
    raw = pdf_page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
    rows = {}
    for sid, groups in span_glyphs(page, raw, glyph_events(pdf_page)).items():
        for offset, decoded, glyph in groups:
            named = name_codepoint(glyph["glyph_name"])
            if named is None or any(c < 0 for c in decoded):
                continue
            text = "".join(map(chr, decoded))
            if unicodedata.normalize("NFKC", chr(named)) != unicodedata.normalize("NFKC", text):
                rows[sid, offset] = (glyph["glyph_name"], text)
    return rows


def main(book):
    before = read(BASE / f"{book}.json")
    keys = before["keys"]
    list_key = book_fingerprint(keys["lists"])
    lists = verified_read(CACHE11 / "lists/book" / f"{list_key}.json", BookListsResult, list_key)
    source = reference_path(BOOKS[book][0])
    observed, line_of, texts, strict = [], {}, {}, Counter()
    strict_examples = Counter()
    with source_session(source) as snapshot, open_source(source) as document:
        assert snapshot.digest == before["source_sha256"]
        for number in sorted(int(n) for n in before["pages"]):
            analysis = verified_read(
                CACHE / "analysis" / keys["analysis"] / f"{number}.json",
                ObjectAnalysis,
                keys["analysis"],
            )
            page = analysis.native.page
            original = page.model_dump_json()
            layout = verified_read(
                CACHE / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
            )
            units = list_page(lists, number, CACHE11).units
            observed.append(observe_page(document, page, layout, units))
            assert page.model_dump_json() == original, "Character evidence changed the store"
            line_of[number] = {sid: s.line_id for sid, s in page.store.spans.items()}
            texts[number] = {sid: s.raw_text for sid, s in page.store.spans.items()}
            for (_, _), (name, text) in strict_disagreements(page, document[number - 1]).items():
                strict["glyphs"] += 1
                strict_examples[name, text] += 1
            if number % 50 == 0:
                print(book, number, flush=True)
    decided = decide(observed, line_of)
    flags = [
        {
            "page": r.page,
            "span_id": f.span_id,
            "raw_text": texts[r.page][f.span_id],
            "reasons": f.reasons,
            "confidence": f.confidence,
            "glyphs": [
                {
                    "glyph_name": g.glyph_name,
                    "name_codepoint": g.name_codepoint,
                    "decoded": "".join(map(chr, g.decoded_codepoints)),
                    "decoded_codepoints": g.decoded_codepoints,
                    "font": g.font,
                    "glyph_id": g.glyph_id,
                }
                for g in f.glyphs
            ],
        }
        for r in decided
        for f in r.flags
    ]
    by_glyph = Counter(
        (g["glyph_name"], g["decoded"], tuple(f["reasons"])) for f in flags for g in f["glyphs"]
    )
    result = {
        "book": book,
        "version": VERSION,
        "config": CONFIG,
        "baseline_keys": {"layout": keys["layout"], "lists": keys["lists"]},
        "pages": len(decided),
        "pages_with_diagnostics": {r.page: r.diagnostics for r in decided if r.diagnostics},
        "flagged_spans": len(flags),
        "reasons": dict(Counter(reason for f in flags for reason in f["reasons"])),
        "by_glyph": [
            {"glyph_name": n, "decoded": d, "reasons": list(rs), "glyphs": c}
            for (n, d, rs), c in by_glyph.most_common()
        ],
        "strict_initial_name_comparison": {
            "glyphs": strict["glyphs"],
            "by_glyph": [
                {"glyph_name": n, "decoded": d, "glyphs": c}
                for (n, d), c in strict_examples.most_common()
            ],
        },
        "flags": flags,
    }
    write(OUT / f"{book}.json", result)
    print(book, result["flagged_spans"], result["reasons"], flush=True)
    for row in result["by_glyph"][:15]:
        print("  ", row, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=identity.BOOKS, required=True)
    main(parser.parse_args().book)
