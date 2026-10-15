"""The character repair layer: proposals over the character stage's glyph evidence.

A glyph whose name the strict glyph list reads as one character, while the PDF decodes it to
another (``characters`` stage evidence), is a repair only when the embedded font program's
own character map assigns that same character to that same glyph: two independent sources
(the glyph name and the program's map) then agree against the decoding. Anything less keeps
the original text and becomes a review flag. The span store is never changed; a repair is a
record (original, corrected, evidence, confidence, review status).
"""

from book_core.equations.models import CharacterRepair, CharacterReviewFlag
from book_core.extraction.fingerprints import stable_id

REPAIR_CONFIDENCE = 0.95


def _region_of(span_id, offset, regions):
    for region in regions:
        for ref in region.span_refs:
            if ref.span_id == span_id and (ref.start or 0) <= offset < (ref.end or 10**9):
                return region.id
    return None


def page_repairs(page, evidence, fonts, regions):
    """(repairs, flags) of one page from its character evidence and font programs."""
    repairs, flags = [], []
    for span_id, glyphs in sorted(evidence.candidates.items()):
        span = page.store.spans[span_id]
        for glyph in glyphs:
            if not glyph.name_disagrees:
                continue
            region = _region_of(span_id, glyph.offset, regions)
            named = glyph.name_codepoint
            width = len("".join(map(chr, glyph.decoded_codepoints)))
            original = span.raw_text[glyph.offset : glyph.offset + max(1, width)]
            if named is not None and fonts.maps(glyph.font, glyph.glyph_name, named):
                repairs.append(
                    CharacterRepair(
                        id=stable_id(page.source_sha256, "repair", span_id, glyph.offset),
                        span_id=span_id,
                        start=glyph.offset,
                        end=glyph.offset + len(original),
                        original=original,
                        corrected=chr(named),
                        glyph_id=glyph.glyph_id,
                        glyph_name=glyph.glyph_name,
                        font=glyph.font,
                        evidence=[
                            "glyph name reads as the corrected character (strict glyph list)",
                            "the embedded font program maps the corrected character to this glyph",
                            "the PDF decodes the glyph to another character",
                        ],
                        confidence=REPAIR_CONFIDENCE,
                        in_equation=region,
                    )
                )
                continue
            reasons = ["glyph name disagrees with the decoded text"]
            if named is None:
                reasons.append("glyph name does not denote one character")
            else:
                reasons.append("the font program does not confirm the glyph name")
            flags.append(
                CharacterReviewFlag(
                    span_id=span_id,
                    start=glyph.offset,
                    glyph_id=glyph.glyph_id,
                    glyph_name=glyph.glyph_name,
                    proposed=chr(named) if named is not None else None,
                    reasons=reasons,
                    in_equation=region,
                )
            )
    return repairs, flags
