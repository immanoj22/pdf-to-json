"""General character-evidence tests. Flags only; no text is replaced or inferred.

Both tests use Unicode properties and the font's own glyph names. There is no list of code
points, fonts, books or pages.

- Name disagreement: a glyph name that the strict glyph list reads as one character, while
  the PDF decodes the glyph to something else. Case-only differences (small capitals and
  similar case conventions) and decodings to format characters (a soft hyphen drawn with a
  hyphen glyph) are expected conventions, not disagreements. Comparison is after NFKC. A
  glyph decoding to several characters agrees with a name for the whole sequence or for its
  first character.
- Repeated marker: a letter, number or control/unassigned character used as a set-off list
  marker, whose glyph has no readable name or a disagreeing one, and the same glyph of the
  same font repeats as such a marker elsewhere in the book.
"""

import unicodedata

from pymupdf import mupdf as m

from book_core.lists.lines import _spans, set_off_marker

MARKER_CONTROL_CATEGORIES = frozenset({"Cc", "Cf", "Cn"})


def name_codepoint(glyph_name):
    """The single character a glyph name denotes under the strict glyph list, else None."""
    if not glyph_name:
        return None
    base = glyph_name.split(".", 1)[0]
    if not base:
        return None
    code = m.fz_unicode_from_glyph_name_strict(base)
    return code if code > 0 else None


def comparable(codepoints):
    return unicodedata.normalize("NFKC", "".join(map(chr, codepoints))).casefold()


def name_disagrees(named, decoded):
    if named is None or not decoded or any(c < 0 for c in decoded):
        return False
    if any(unicodedata.category(chr(c)) == "Cf" for c in decoded):
        return False
    # A glyph decoding to several characters agrees when its name denotes the whole sequence
    # (a ligature) or the first character it draws (a space carrying a leader dot).
    name = comparable([named])
    return name not in {comparable(decoded), comparable(decoded[:1])}


def marker_character(character):
    if len(character) != 1 or character.isspace():
        return False
    category = unicodedata.category(character)
    return category[0] in {"L", "N"} or category in MARKER_CONTROL_CATEGORIES


def marker_positions(store, layout, units):
    """{(span id, offset)} of single-character set-off markers: accepted unpunctuated bullet
    markers of list units, and set-off glyphs opening a visual line."""
    positions = set()
    for unit in units:
        marker = getattr(unit, "marker", None)
        if marker is None or marker.type != "bullet" or marker.punctuation != "none":
            continue
        for ref in marker.refs:
            text = store.spans[ref.span_id].raw_text
            start = ref.start or 0
            piece = text[start : ref.end if ref.end is not None else len(text)]
            if len(piece.strip()) == 1 and marker_character(piece.strip()):
                positions.add((ref.span_id, start + piece.index(piece.strip())))
    for line in layout.lines:
        raw = "".join(store.spans[s].raw_text for s in line.span_ids)
        rows = _spans(store, line)
        reading = set_off_marker(raw, rows, store)
        if reading is None or not marker_character(raw[reading.start]):
            continue
        for sid, start, end, *_ in rows:
            if start <= reading.start < end:
                positions.add((sid, reading.start - start))
    return positions
