"""Printed page-label tokens: arabic (any script's decimal digits), roman and prefixed labels.

A label is parsed from a line's NFKC text after stripping decoration (punctuation, dashes,
symbols and spaces) at its ends. Nothing here decides that a token is a folio: that needs the
whole-book sequence (``furniture.sequence``). Digits from every Unicode script count, so the
rule never assumes Latin text or left-to-right order.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import regex

_DECORATION = regex.compile(r"^[\p{P}\p{S}\p{Z}\s]+|[\p{P}\p{S}\p{Z}\s]+$")
_ARABIC = regex.compile(r"\p{Nd}{1,5}")
_ROMAN = regex.compile(r"(?i)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})")
# A short letter prefix (section or appendix letters) or a chapter number, then the number.
_PREFIXED = regex.compile(
    r"(?P<prefix>\p{L}{1,4}|\p{Nd}{1,3})(?P<joint>[\p{Pd}.:]?)(?P<n>\p{Nd}{1,4})"
)
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


@dataclass(frozen=True)
class Label:
    kind: str  # arabic | roman | prefixed
    value: int  # the running number
    prefix: str = ""  # prefixed labels: the prefix and joint, e.g. "HT" or "3-"
    upper: bool = False  # roman: written in capitals

    def render(self, value: int | None = None) -> str:
        value = self.value if value is None else value
        if self.kind == "roman":
            text = to_roman(value)
            return text.upper() if self.upper else text
        return f"{self.prefix}{value}"

    @property
    def series(self) -> tuple[str, str, bool]:
        """Labels of one sequence share kind, prefix and case."""
        return (self.kind, self.prefix, self.upper)


def roman_value(text: str) -> int | None:
    text = text.lower()
    if not text or not _ROMAN.fullmatch(text):
        return None
    total = 0
    for current, following in zip(text, [*text[1:], ""], strict=True):
        value = _ROMAN_VALUES[current]
        total += -value if following and _ROMAN_VALUES[following] > value else value
    return total or None


def to_roman(value: int) -> str:
    parts = []
    for number, numeral in (
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    ):
        while value >= number:
            parts.append(numeral)
            value -= number
    return "".join(parts)


def _digits(text: str) -> int:
    return int("".join(str(unicodedata.digit(c)) for c in text))


def _overprint_unit(core: str) -> str | None:
    """The unit of text drawn k >= 2 times in one place (an extraction overprint)."""
    for size in range(1, len(core) // 2 + 1):
        if len(core) % size == 0 and core[:size] * (len(core) // size) == core:
            return core[:size]
    return None


def label_candidates(text: str) -> list[Label]:
    """Every label a short text could be: as written, then as an overprinted unit.

    Text drawn several times in one place extracts as a repeat (``438438438``, ``8080``). Both
    readings are kept; only the whole-book sequence decides which one, if any, is a folio.
    """
    core = _DECORATION.sub("", unicodedata.normalize("NFKC", text))
    if not core or regex.search(r"\s", core):
        return []
    labels = []
    for value in (core, _overprint_unit(core)):
        label = _parse_core(value) if value else None
        if label is not None and label not in labels:
            labels.append(label)
    return labels


def parse_label(text: str) -> Label | None:
    """The first reading of ``label_candidates`` (as written when that parses)."""
    labels = label_candidates(text)
    return labels[0] if labels else None


def _parse_core(core: str) -> Label | None:
    if len(core) > 9:
        return None
    if _ARABIC.fullmatch(core):
        value = _digits(core)
        return Label("arabic", value) if value > 0 else None
    roman = roman_value(core)
    if roman is not None and (core.islower() or core.isupper()):
        return Label("roman", roman, upper=core.isupper())
    match = _PREFIXED.fullmatch(core)
    if match is not None:
        value = _digits(match["n"])
        if value > 0:
            return Label("prefixed", value, prefix=match["prefix"] + match["joint"])
    return None


def normalize_label(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()
