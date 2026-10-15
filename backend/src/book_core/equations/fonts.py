"""Font-program evidence from the embedded fonts (fontTools): math tables, glyph coverage and
the font's own character map. Font names are only used to join a span to its program.

- ``math_font``: the program carries an OpenType MATH table, or most of the characters it
  maps (from its character map, else from its glyph names) are math operators or Greek.
- ``cmap``: {glyph name: code points} from the program's own Unicode character map; a repair
  needs the program itself to say which character a glyph draws.
"""

import io
import logging
import unicodedata

from fontTools.agl import toUnicode
from fontTools.cffLib import CFFFontSet
from fontTools.ttLib import TTFont

LOG = logging.getLogger("book_core.equations")
MATH_SHARE = 0.3
MIN_MAPPED = 8


def _math_character(code: int) -> bool:
    character = chr(code)
    return unicodedata.category(character) == "Sm" or "GREEK" in unicodedata.name(character, "")


def _base_name(name: str) -> str:
    return name.split("+", 1)[1] if "+" in name[:8] else name


def program_evidence(name: str, extension: str, buffer: bytes) -> dict:
    """Evidence of one embedded program; unreadable programs give no evidence."""
    result = {"font": _base_name(name), "program": extension or "none", "readable": False}
    glyph_names: list[str] = []
    cmap: dict[str, list[int]] = {}
    has_math = False
    try:
        if extension in {"ttf", "otf"}:
            font = TTFont(io.BytesIO(buffer), lazy=True)
            glyph_names = list(font.getGlyphOrder())
            has_math = "MATH" in font
            table = font.get("cmap")
            best = table.getBestCmap() if table is not None else None
            for code, glyph in (best or {}).items():
                cmap.setdefault(glyph, []).append(code)
        elif extension == "cff":
            fonts = CFFFontSet()
            fonts.decompile(io.BytesIO(buffer), None)
            glyph_names = list(fonts[fonts.fontNames[0]].charset or [])
        else:
            return result
    except Exception as error:  # an unreadable program is no evidence, never a failure
        LOG.debug("font program %s unreadable: %s", name, error)
        return result
    codes = [c for codes in cmap.values() for c in codes]
    if not codes:
        codes = [ord(c) for g in glyph_names for c in toUnicode(g.split(".", 1)[0]) if c]
        codes = [c for c in codes if c > 0x20]
    mapped = sorted(set(codes))
    share = sum(_math_character(c) for c in mapped) / len(mapped) if mapped else 0.0
    result.update(
        readable=True,
        glyphs=len(glyph_names),
        mapped=len(mapped),
        math_share=round(share, 4),
        math_table=has_math,
        math_font=bool(has_math or (len(mapped) >= MIN_MAPPED and share >= MATH_SHARE)),
    )
    result["_cmap"] = cmap
    result["_glyph_names"] = glyph_names
    return result


class FontEvidence:
    """Lazy per-document cache of program evidence, keyed by font object number."""

    def __init__(self, document):
        self.document = document
        self.by_xref: dict[int, dict] = {}
        self.by_name: dict[str, dict] = {}

    def page_fonts(self, number: int) -> list[dict]:
        rows = []
        for xref, extension, _type, basefont, *_rest in self.document[number - 1].get_fonts(
            full=True
        ):
            if xref <= 0:
                continue
            if xref not in self.by_xref:
                try:
                    name, ext, _t, buffer = self.document.extract_font(xref)
                except Exception:  # a font without an extractable program
                    name, ext, buffer = basefont, extension, b""
                evidence = program_evidence(name or basefont, ext or extension, buffer or b"")
                self.by_xref[xref] = evidence
                self.by_name.setdefault(evidence["font"], evidence)
            rows.append(self.by_xref[xref])
        return rows

    def math_fonts(self, number: int) -> frozenset:
        return frozenset(row["font"] for row in self.page_fonts(number) if row.get("math_font"))

    def maps(self, font: str, glyph_name: str | None, code: int) -> bool:
        """Whether the font's own character map assigns ``code`` to this glyph."""
        evidence = self.by_name.get(_base_name(font))
        if evidence is None or not glyph_name:
            return False
        return code in evidence.get("_cmap", {}).get(glyph_name, [])

    def summary(self) -> dict:
        return {
            str(xref): {k: v for k, v in row.items() if not k.startswith("_")}
            for xref, row in sorted(self.by_xref.items())
        }
