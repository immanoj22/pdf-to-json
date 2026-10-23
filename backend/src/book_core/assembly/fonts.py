"""Per-book font styles: which fonts are bold, italic or small caps, learned from evidence.

No font list is hard-coded. For every font of the book (subset prefix removed) the stage
collects two kinds of evidence over all its characters:

- **flags**: the share of characters whose span carries the PDF font-descriptor bold or italic
  flag (PyMuPDF span flags);
- **name**: the style part of the PostScript name, split into words ("Times-BoldItalic" →
  bold, italic; "MinionPro-SemiboldIt" → semibold, it). The words are the PostScript naming
  conventions for weight, slope and small capitals, not font names.

A font is bold when its name says a bold weight or most of its characters carry the bold
flag (likewise italic). A name saying "regular", "roman" or "book" never overrides a flag
majority; such a font (the name says regular, most characters carry the flag) is reported
(``disagreements``) for review. Every decision keeps its evidence. Small caps come from the
name words or are decided per span (``small_caps_span``): a run of capitals set smaller than
the line's text.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import regex

BOLD_FLAG, ITALIC_FLAG, SUPERSCRIPT_FLAG = 1 << 4, 1 << 1, 1
BOLD_WORDS = frozenset({"bold", "bd", "black", "blk", "heavy", "hv", "semibold", "semibd",
                        "sb", "demi", "demibold", "dembd", "extrabold", "xbold", "ultrabold",
                        "ultra", "ub", "fat", "poster"})  # fmt: skip
ITALIC_WORDS = frozenset({"italic", "it", "ital", "oblique", "obl", "slanted", "sl", "kursiv",
                          "inclined", "cursive"})  # fmt: skip
SMALL_CAPS_WORDS = frozenset({"sc", "smallcaps", "smcp", "caps", "petitecaps"})
REGULAR_WORDS = frozenset({"regular", "roman", "book", "normal", "plain", "upright", "rg",
                           "reg"})  # fmt: skip
ABBREVIATED = {"b": ("bold",), "i": ("italic",), "bi": ("bold", "italic"),
               "ib": ("bold", "italic"), "z": ("bold", "italic")}  # fmt: skip
FLAG_MAJORITY = 0.5
_CAMEL = regex.compile(r"\p{Lu}+(?=\p{Lu}\p{Ll})|\p{Lu}?\p{Ll}+|\p{Lu}+|\p{N}+")


def base_name(font):
    """The font name without its subset prefix ("ABCDEF+Times-Bold" → "Times-Bold")."""
    return font.split("+", 1)[1] if regex.match(r"^[A-Z]{6}\+", font) else font


def style_words(font):
    """Lower-case words of the style part of a PostScript font name (after the first "-" or
    ","; the whole name split at case changes when there is no separator)."""
    name = base_name(font)
    for separator in ("-", ","):
        if separator in name:
            style = name.split(separator, 1)[1]
            break
    else:
        style = name
    if style.casefold() in ABBREVIATED and style != name:
        return list(ABBREVIATED[style.casefold()])
    # "BoldItalicMT" → bold, italic, mt; "BdIt" → bd, it; "Semibold-SC700" → semibold, sc, 700
    return [w.casefold() for w in _CAMEL.findall(style)]


@dataclass
class FontEvidence:
    characters: int = 0
    bold_flag: int = 0
    italic_flag: int = 0


@dataclass
class FontStyle:
    name: str
    bold: bool
    italic: bool
    small_caps: bool
    characters: int
    evidence: list[str] = field(default_factory=list)
    disagreement: bool = False


class FontTable:
    """Collect evidence page by page (``add``), then ``freeze`` into decisions."""

    def __init__(self):
        self.seen = defaultdict(FontEvidence)
        self.styles = {}

    def add(self, store):
        for span in store.spans.values():
            if span.provenance.method != "native":
                continue
            weight = len(span.raw_text.strip())
            if not weight:
                continue
            row = self.seen[base_name(span.font)]
            row.characters += weight
            row.bold_flag += weight * bool(span.flags & BOLD_FLAG)
            row.italic_flag += weight * bool(span.flags & ITALIC_FLAG)

    def freeze(self):
        for name, row in sorted(self.seen.items()):
            words = set(style_words(name))
            # A truncated style word ("Itali", "Obliq") counts as its full word.
            words |= {full for w in words if len(w) >= 4
                      for full in ("italic", "oblique", "semibold", "demibold")
                      if full.startswith(w)}  # fmt: skip
            bold_name, italic_name = bool(words & BOLD_WORDS), bool(words & ITALIC_WORDS)
            bold_share = row.bold_flag / row.characters if row.characters else 0.0
            italic_share = row.italic_flag / row.characters if row.characters else 0.0
            bold = bold_name or bold_share >= FLAG_MAJORITY
            italic = italic_name or italic_share >= FLAG_MAJORITY
            evidence = [
                f"name words: {', '.join(sorted(words)) or 'none'}",
                f"bold flag on {bold_share:.0%} of characters",
                f"italic flag on {italic_share:.0%} of characters",
            ]
            # A name that says "regular" (or roman, book...) against a flag majority: review.
            # A silent name, or flags missing for a named weight, are not contradictions.
            regular = bool(words & REGULAR_WORDS) and not (bold_name or italic_name)
            disagreement = regular and (bold_share >= FLAG_MAJORITY
                                        or italic_share >= FLAG_MAJORITY)  # fmt: skip
            self.styles[name] = FontStyle(
                name=name,
                bold=bold,
                italic=italic,
                # "SC700"-like codes (a word with a number) are not a small-caps style
                small_caps=bool(words & SMALL_CAPS_WORDS) and not any(w.isdigit() for w in words),
                characters=row.characters,
                evidence=evidence,
                disagreement=disagreement,
            )
        return self

    def style(self, font):
        return self.styles.get(base_name(font))

    @property
    def disagreements(self):
        return sorted(name for name, s in self.styles.items() if s.disagreement)

    def body_font(self):
        counts = Counter({name: s.characters for name, s in self.styles.items()})
        return counts.most_common(1)[0][0] if counts else None


def small_caps_span(text, size, line_size):
    """A run of capital letters set clearly smaller than its line's text (no lowercase)."""
    letters = [c for c in text if c.isalpha()]
    return (
        len(letters) >= 2
        and all(c.isupper() for c in letters)
        and size <= 0.85 * line_size
        and line_size > 0
    )
