"""Book-level equation stage after figures: regions, owners, model support and repairs.

Pass 1 counts vector glyph outlines over the whole book (a drawn font repeats its outlines)
and measures the book's text line pitch; pass 2 detects regions on every page with that book
evidence, gives every region an owner (``ownership``: text units, display equation units,
real figures; figures of equation evidence only are converted), adds layout-model support
and the character repair layer. Page records are written once every page is decided; a
partial cache is recomputed. No earlier stage reads equation records back: units, lines,
order and the ledger are unchanged, and the span store is never changed.
"""

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import fontTools
import pymupdf

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.equations import detect, glyphs, ownership, text
from book_core.equations.fonts import FontEvidence
from book_core.equations.models import BookEquations, GlyphOwnership, PageEquations
from book_core.equations.repairs import REPAIR_CONFIDENCE, page_repairs
from book_core.extraction.fingerprints import stable_id
from book_core.run_context import open_source

VERSION = "equations-2"
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
        "dot_max_side": glyphs.DOT_MAX_SIDE,
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
        "accent_gap": detect.ACCENT_GAP,
        "row_slack": detect.ROW_SLACK,
        "overline_reach": detect.OVERLINE_REACH,
        "operator_max_width": detect.OPERATOR_MAX_WIDTH,
        "mark_stack": detect.MARK_STACK,
        "clip_margin": detect.CLIP_MARGIN,
        "touch": detect.TOUCH,
        "reversed_contrast": detect.REVERSED_CONTRAST,
        "row_gap": detect.ROW_GAP,
        "default_pitch": detect.DEFAULT_PITCH,
    },
    "ownership": {"in_figure": ownership.IN_FIGURE},
    "text": {
        "script_size_ratio": text.SCRIPT_SIZE_RATIO,
        "script_shift_ratio": text.SCRIPT_SHIFT_RATIO,
        "short_name": text.SHORT_NAME,
        "script_span": text.SCRIPT_SPAN,
    },
    "repair_confidence": REPAIR_CONFIDENCE,
}
LOADED_DIGEST = code_digest("equations")


def equations_fingerprint(lists_key, characters_key, native_key, figures_key, model_identity=None):
    return stable_id(
        lists_key,
        characters_key,
        native_key,
        figures_key,
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
    lists_of,
    native_of,
    characters_of,
    figures_of,
    keys,
    cache_dir,
    total,
    model_formulas=None,
):
    """Equation records for every page; returns (key, BookEquations).

    ``lists_of(number)``: the page's PageLists (units and reading order);
    ``native_of(number)``: its NativeObjectPage; ``characters_of(number)``: its character
    evidence; ``figures_of(number)``: its PageFigures; ``keys``: {lists, characters, native,
    figures}; ``model_formulas(number)``: {model: [(box, label)]} or None when layout-model
    evidence is off.
    """
    assert_producer_unchanged("equations", LOADED_DIGEST)
    key = equations_fingerprint(
        keys["lists"],
        keys["characters"],
        keys["native"],
        keys["figures"],
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
    pitches = []
    for page in pages():
        number = page.geometry.page
        native = native_of(number)
        layout = layout_of(page)
        lines = [line for line in layout.lines if line.inside_content and not line.blank]
        boxes = [page.store.spans[sid].bbox for line in lines for sid in line.span_ids]
        found, _, signatures = glyphs.page_glyphs(native, book_size, boxes)
        shapes.update(signatures.values())
        for signature in signatures.values():
            shape_pages[signature].add(number)
        for group in detect.glyph_groups(found, book_size, boxes):
            joined.update(signatures[i.id] for i in detect.beside_others(group, signatures))
        pitches += detect.line_pitches(layout, lists_of(number).units)
        del native
    recurring = glyphs.accepted(shapes, joined, shape_pages)
    # Display rows join within the book's own text line pitch.
    pitch = statistics.median(pitches) if pitches else None
    inputs = {
        "lists_key": keys["lists"],
        "characters_key": keys["characters"],
        "native_key": keys["native"],
        "figures_key": keys["figures"],
        "producer": LOADED_DIGEST,
        "configuration": json.dumps(CONFIG, sort_keys=True),
        "version": VERSION,
    }
    totals = Counter()
    by_presentation, by_source, by_owner, owned_objects = Counter(), Counter(), Counter(), Counter()
    converted_images, kept_images = set(), set()
    with open_source(source) as document:
        fonts = FontEvidence(document)
        for page in pages():
            number = page.geometry.page
            native = native_of(number)
            layout = layout_of(page)
            built = lists_of(number)
            figures = figures_of(number)
            model_boxes = model_formulas(number) if model_formulas is not None else {}
            regions, model_only, diagnostics, signatures = detect.detect_page(
                page,
                native,
                layout,
                built.units,
                recurring,
                fonts.math_fonts(number),
                model_boxes,
                book_size,
                CONFIG,
                pitch,
            )
            regions, units, conversions, kept, owned = ownership.own_page(
                page,
                layout,
                built,
                figures,
                native,
                regions,
                ownership.FigureContent(page, layout, native),
                lambda figure: figure.image.file_name if figure.image is not None else None,
            )
            repairs, flags = page_repairs(page, characters_of(number), fonts, regions)
            totals["vector_glyphs"] += sum(1 for s in signatures.values() if s in recurring)
            by_presentation.update(r.presentation for r in regions)
            by_source.update(r.source for r in regions)
            by_owner.update(r.owner.kind for r in regions)
            owned_objects.update(owned.model_dump())
            totals["regions"] += len(regions)
            totals["units"] += len(units)
            totals["converted"] += len(conversions)
            totals["kept"] += len(kept)
            totals["repairs"] += len(repairs)
            totals["flags"] += len(flags)
            converted_ids = {c.figure_id for c in conversions}
            for figure in figures.figures:
                if figure.image is None:
                    continue
                if figure.id in converted_ids:
                    converted_images.add(figure.image.file_name)
                else:
                    kept_images.add(figure.image.file_name)
            record = PageEquations(
                source_sha256=page.source_sha256,
                page=number,
                version=VERSION,
                regions=regions,
                units=units,
                figure_conversions=conversions,
                figure_math=kept,
                ownership=owned,
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
        units=totals["units"],
        by_owner=dict(by_owner),
        ownership=GlyphOwnership(**{k: owned_objects[k] for k in GlyphOwnership.model_fields}),
        figures_converted=totals["converted"],
        figures_kept_with_math=totals["kept"],
        # A spread shares one image file: it stays exported while a kept figure uses it.
        images_not_exported=sorted(converted_images - kept_images),
        line_pitch=pitch,
        model_evidence=model_formulas is not None,
        font_evidence=font_summary,
        cache_key_inputs=inputs,
    )
    write_model(book_path, book, key)
    return key, book


def load_page(cache_dir, key, number):
    return read_model(Path(cache_dir) / "equations" / key / f"{number}.json", PageEquations, key)
