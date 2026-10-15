"""Book-level equation stage after figures: regions, model support and character repairs.

Pass 1 counts vector glyph outlines over the whole book (a drawn font repeats its outlines);
pass 2 detects regions on every page with that book evidence, adds layout-model support and
the character repair layer. Page records are written once every page is decided; a partial
cache is recomputed. No stage reads equation records back: units, order and the ledger are
unchanged, and the span store is never changed.
"""

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import fontTools
import pymupdf

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.equations import detect, glyphs, text
from book_core.equations.fonts import FontEvidence
from book_core.equations.models import BookEquations, PageEquations
from book_core.equations.repairs import REPAIR_CONFIDENCE, page_repairs
from book_core.extraction.fingerprints import stable_id
from book_core.run_context import open_source

VERSION = "equations-1"
CONFIG = {
    "glyph": {
        "min_height": glyphs.GLYPH_MIN_HEIGHT,
        "max_height": glyphs.GLYPH_MAX_HEIGHT,
        "tall_max_height": glyphs.TALL_GLYPH_MAX_HEIGHT,
        "tall_max_width": glyphs.TALL_GLYPH_MAX_WIDTH,
        "max_width": glyphs.GLYPH_MAX_WIDTH,
        "bar_max_height": glyphs.BAR_MAX_HEIGHT,
        "bar_min_width": glyphs.BAR_MIN_WIDTH,
        "signature_digits": glyphs.SIGNATURE_DIGITS,
        "min_recurrence": glyphs.MIN_RECURRENCE,
        "social_share": glyphs.SOCIAL_SHARE,
    },
    "cluster": {
        "join_gap": detect.JOIN_GAP,
        "stack_gap": detect.STACK_GAP,
        "bar_reach": detect.BAR_REACH,
        "bar_max_width": detect.BAR_MAX_WIDTH,
        "inline_reach": detect.INLINE_REACH,
        "band_overlap": detect.BAND_OVERLAP,
        "model_overlap": detect.MODEL_OVERLAP,
        "colour_tolerance": detect.COLOUR_TOLERANCE,
    },
    "text": {
        "script_size_ratio": text.SCRIPT_SIZE_RATIO,
        "script_shift_ratio": text.SCRIPT_SHIFT_RATIO,
        "short_name": text.SHORT_NAME,
    },
    "repair_confidence": REPAIR_CONFIDENCE,
}
LOADED_DIGEST = code_digest("equations")


def equations_fingerprint(lists_key, characters_key, native_key, model_identity=None):
    return stable_id(
        lists_key,
        characters_key,
        native_key,
        json.dumps(model_identity or {}, sort_keys=True),
        code_digest("equations"),
        VERSION,
        json.dumps(CONFIG, sort_keys=True),
        "pymupdf-" + pymupdf.VersionBind,
        "fonttools-" + fontTools.version,
    )


def text_size(page):
    sizes = [s.size for s in page.store.spans.values() if s.raw_text.strip() and s.size > 0]
    return statistics.median(sizes) if sizes else None


def analyze_book_equations(
    source,
    pages,
    layout_of,
    units_of,
    native_of,
    characters_of,
    keys,
    cache_dir,
    total,
    model_formulas=None,
):
    """Equation records for every page; returns (key, BookEquations).

    ``native_of(number)``: the page's NativeObjectPage; ``characters_of(number)``: its
    character evidence; ``keys``: {lists, characters, native}; ``model_formulas(number)``:
    {model: [(box, label)]} or None when layout-model evidence is off.
    """
    assert_producer_unchanged("equations", LOADED_DIGEST)
    key = equations_fingerprint(
        keys["lists"],
        keys["characters"],
        keys["native"],
        model_formulas.identity if model_formulas is not None else None,
    )
    directory = Path(cache_dir) / "equations" / key
    paths = {n: directory / f"{n}.json" for n in range(1, total + 1)}
    book_path = directory / "book.json"
    if book_path.exists() and all(path.exists() for path in paths.values()):
        return key, read_model(book_path, BookEquations, key)
    sizes, digest = {}, None
    for page in pages():
        sizes[page.geometry.page] = text_size(page)
        digest = page.source_sha256
    if sorted(sizes) != list(paths):
        raise ValueError("Equation evidence has incomplete page coverage")
    known = [s for s in sizes.values() if s]
    # Glyph scale is the book's body text size: a page of large display type (a cover, a
    # title page) does not make its drawings text-sized.
    book_size = statistics.median(known) if known else 10.0
    shapes, joined, shape_pages = Counter(), Counter(), defaultdict(set)
    for page in pages():
        number = page.geometry.page
        native = native_of(number)
        lines = [line for line in layout_of(page).lines if line.inside_content and not line.blank]
        boxes = [page.store.spans[sid].bbox for line in lines for sid in line.span_ids]
        found, _, signatures = glyphs.page_glyphs(native, book_size, boxes)
        shapes.update(signatures.values())
        for signature in signatures.values():
            shape_pages[signature].add(number)
        for group in detect.glyph_groups(found, book_size, boxes):
            joined.update(signatures[i.id] for i in detect.beside_others(group, signatures))
        del native
    recurring = glyphs.accepted(shapes, joined, shape_pages)
    inputs = {
        "lists_key": keys["lists"],
        "characters_key": keys["characters"],
        "native_key": keys["native"],
        "producer": LOADED_DIGEST,
        "configuration": json.dumps(CONFIG, sort_keys=True),
        "version": VERSION,
    }
    totals = Counter()
    by_presentation, by_source = Counter(), Counter()
    with open_source(source) as document:
        fonts = FontEvidence(document)
        for page in pages():
            number = page.geometry.page
            native = native_of(number)
            layout = layout_of(page)
            units = units_of(number)
            model_boxes = model_formulas(number) if model_formulas is not None else {}
            regions, model_only, diagnostics, signatures = detect.detect_page(
                page,
                native,
                layout,
                units,
                recurring,
                fonts.math_fonts(number),
                model_boxes,
                book_size,
                CONFIG,
            )
            repairs, flags = page_repairs(page, characters_of(number), fonts, regions)
            totals["vector_glyphs"] += sum(1 for s in signatures.values() if s in recurring)
            by_presentation.update(r.presentation for r in regions)
            by_source.update(r.source for r in regions)
            totals["regions"] += len(regions)
            totals["repairs"] += len(repairs)
            totals["flags"] += len(flags)
            record = PageEquations(
                source_sha256=page.source_sha256,
                page=number,
                version=VERSION,
                regions=regions,
                model_only=model_only,
                repairs=repairs,
                character_flags=flags,
                diagnostics=diagnostics,
                cache_key_inputs=inputs,
            )
            assert_producer_unchanged("equations", LOADED_DIGEST)
            write_model(paths[number], record, key)
            del native
        font_summary = fonts.summary()
    book = BookEquations(
        source_sha256=digest,
        pages=total,
        version=VERSION,
        config=CONFIG,
        glyph_shapes=len(recurring),
        vector_glyphs=totals["vector_glyphs"],
        regions=totals["regions"],
        by_presentation=dict(by_presentation),
        by_source=dict(by_source),
        repairs=totals["repairs"],
        character_flags=totals["flags"],
        model_evidence=model_formulas is not None,
        font_evidence=font_summary,
        cache_key_inputs=inputs,
    )
    write_model(book_path, book, key)
    return key, book


def load_page(cache_dir, key, number):
    return read_model(Path(cache_dir) / "equations" / key / f"{number}.json", PageEquations, key)
