"""Book-level character evidence after lists. Flags only: no stage reads them back.

Page observations need the source PDF (glyph names and exact attribution), the page's
layout lines and its final list units. Marker repetition is a whole-book decision, so page
files are written once every page is observed; a partial cache is recomputed.
"""

import json
from collections import defaultdict
from pathlib import Path

import pymupdf

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.characters.glyphs import glyph_events, span_glyphs
from book_core.characters.models import CharacterFlag, GlyphEvidence, PageCharacterEvidence
from book_core.characters.rules import (
    marker_positions,
    name_codepoint,
    name_disagrees,
)
from book_core.extraction.fingerprints import stable_id
from book_core.run_context import open_source

VERSION = "character-evidence-1"
CONFIG = {
    "name_comparison": "strict glyph list; NFKC; casefold; format characters exempt",
    "marker_min_occurrences": 2,
    "confidence": {"name": 0.8, "marker": 0.7, "both": 0.9},
}
LOADED_DIGEST = code_digest("characters")
NAME = "glyph_name_disagrees_with_unicode"
MARKER = "unnamed_or_mismatched_glyph_repeated_as_marker"


def characters_fingerprint(lists_key):
    return stable_id(
        lists_key,
        code_digest("characters"),
        VERSION,
        json.dumps(CONFIG, sort_keys=True),
        "pymupdf-" + pymupdf.VersionBind,
    )


def observe_page(document, page, layout, units):
    number = page.geometry.page
    base = {"source_sha256": page.source_sha256, "page": number, "version": VERSION}
    try:
        pdf_page = document[number - 1]
        raw = pdf_page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
        groups = span_glyphs(page, raw, glyph_events(pdf_page))
    except (AssertionError, ValueError, RuntimeError) as error:
        return PageCharacterEvidence(
            **base, diagnostics=[f"Glyph attribution unsupported: {type(error).__name__}: {error}"]
        )
    markers = marker_positions(page.store, layout, units)
    candidates = defaultdict(list)
    for sid, rows in groups.items():
        for offset, decoded, glyph in rows:
            named = name_codepoint(glyph["glyph_name"])
            disagrees = name_disagrees(named, decoded)
            marker = (sid, offset) in markers and (named is None or disagrees)
            if disagrees or marker:
                candidates[sid].append(
                    GlyphEvidence(
                        offset=offset,
                        glyph_id=glyph["glyph_id"],
                        glyph_name=glyph["glyph_name"],
                        name_codepoint=named,
                        decoded_codepoints=decoded,
                        font=glyph["font"],
                        marker_candidate=marker,
                        name_disagrees=disagrees,
                    )
                )
    return PageCharacterEvidence(**base, candidates=dict(candidates))


def decide(pages, line_of):
    """Flags for every page; marker repetition counts occurrences across the whole book."""
    occurrences = defaultdict(set)
    for result in pages:
        for sid, glyphs in result.candidates.items():
            for g in glyphs:
                if g.marker_candidate:
                    occurrences[g.font, g.glyph_id].add((result.page, sid, g.offset))
    repeated = {
        group
        for group, found in occurrences.items()
        if len(found) >= CONFIG["marker_min_occurrences"]
    }
    decided = []
    for result in pages:
        flags = []
        for sid, glyphs in sorted(result.candidates.items()):
            reasons, used = set(), []
            for g in glyphs:
                hit = False
                if g.name_disagrees:
                    reasons.add(NAME)
                    hit = True
                if g.marker_candidate and (g.font, g.glyph_id) in repeated:
                    reasons.add(MARKER)
                    hit = True
                if hit:
                    used.append(g)
            if not reasons:
                continue
            strength = "both" if len(reasons) == 2 else "name" if NAME in reasons else "marker"
            flags.append(
                CharacterFlag(
                    span_id=sid,
                    line_id=line_of[result.page][sid],
                    reasons=sorted(reasons),
                    confidence=CONFIG["confidence"][strength],
                    glyphs=used,
                )
            )
        decided.append(result.model_copy(update={"flags": flags}))
    return decided


def analyze_book_characters(source, pages, layout_of, units_of, lists_key, cache_dir, total):
    """Character evidence for every page; returns its cache key."""
    assert_producer_unchanged("characters", LOADED_DIGEST)
    key = characters_fingerprint(lists_key)
    directory = Path(cache_dir) / "characters" / key
    paths = {n: directory / f"{n}.json" for n in range(1, total + 1)}
    if all(path.exists() for path in paths.values()):
        return key
    observed, line_of = [], {}
    with open_source(source) as document:
        for page in pages():
            number = page.geometry.page
            observed.append(observe_page(document, page, layout_of(page), units_of(number)))
            line_of[number] = {sid: span.line_id for sid, span in page.store.spans.items()}
    if sorted(r.page for r in observed) != list(paths):
        raise ValueError("Character evidence has incomplete page coverage")
    inputs = {
        "lists_key": lists_key,
        "producer": LOADED_DIGEST,
        "configuration": json.dumps(CONFIG, sort_keys=True),
        "version": VERSION,
    }
    assert_producer_unchanged("characters", LOADED_DIGEST)
    for result in decide(observed, line_of):
        write_model(paths[result.page], result.model_copy(update={"cache_key_inputs": inputs}), key)
    return key


def load_page(cache_dir, key, number):
    return read_model(
        Path(cache_dir) / "characters" / key / f"{number}.json", PageCharacterEvidence, key
    )
