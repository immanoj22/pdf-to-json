"""Multilingual section-numbering evidence for heading candidates.

Patterns, never decisions: a numbered unit is more likely a heading, its depth is level
evidence, and a sectioning word is role evidence. Recognised forms:

- a sectioning word with a number ("Capítulo 3", "Unidad IV", "Lesson 2", "TEMA 1",
  "Article VII"); the word list is a small multilingual lexicon of sectioning nouns (data, not
  book rules) and the number is Arabic (any Unicode digits) or Roman;
- CJK ordinal forms such as "第3章" / "第三課";
- decimal numbering "1", "1.2", "1.2.3" (depth = number of parts) before a title, and a
  zero-padded number standing alone at the start or the end of a short title ("01 Title",
  "Title 02": the printed lesson number stays in native text order);
- a Roman numeral before a title ("IV. Title");
- a bare number standing alone (a lesson number printed apart from its title);
- a single letter standing alone (alphabetical dividers of glossaries and indexes).

All matching is on NFKC text, case-insensitive for words; no script is assumed.
"""

from __future__ import annotations

import unicodedata

import regex

# Sectioning nouns by role hint (lowercase, NFKC, accents kept). Data, multilingual.
SECTION_WORDS = {
    "part": ["part", "parte", "partie", "teil", "deel", "część", "часть", "bölüm kısmı"],
    "unit": [
        "unit", "unidad", "unidade", "unité", "unità", "einheit", "eenheid", "tema", "theme",
        "thème", "module", "módulo", "modul", "modulo", "block", "bloque", "bloc",
    ],
    "chapter": [
        "chapter", "capítulo", "capitulo", "chapitre", "kapitel", "capitolo", "hoofdstuk",
        "rozdział", "глава", "bölüm", "fasıl", "الفصل", "פרק",
    ],
    "lesson": [
        "lesson", "lección", "leccion", "lição", "licao", "leçon", "lektion", "lezione",
        "les", "lekcja", "урок", "ders", "الدرس", "שיעור",
    ],
    "section": [
        "section", "sección", "seccion", "secção", "seção", "abschnitt", "sezione", "sectie",
        "article", "artículo", "articulo", "artigo", "artikel", "articolo", "§",
    ],
    "appendix": ["appendix", "apéndice", "apendice", "apêndice", "annexe", "anhang", "anexo"],
}  # fmt: skip
_WORD_ROLE = {word: role for role, words in SECTION_WORDS.items() for word in words}
_ROMAN = (
    r"(?=[ivxlcdm]+(?![\p{L}\p{N}]))"
    r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
)
_NUMBER = rf"(?:\p{{N}}+|{_ROMAN})"
_WORDS = "|".join(sorted((regex.escape(w) for w in _WORD_ROLE), key=len, reverse=True))
_KEYWORD = regex.compile(rf"^\s*({_WORDS})\s*({_NUMBER})\b", regex.IGNORECASE)
_KEYWORD_AFTER = regex.compile(rf"^\s*({_NUMBER})\s*(?:[.:)]\s*)?({_WORDS})\b", regex.IGNORECASE)
_CJK = regex.compile(r"^\s*第\s*([\p{N}一二三四五六七八九十百千〇零]+)\s*([章節节課课部編编篇回])")
_CJK_ROLE = {"章": "chapter", "節": "section", "节": "section", "課": "lesson", "课": "lesson",
             "部": "part", "編": "part", "编": "part", "篇": "part", "回": "chapter"}  # fmt: skip
_DECIMAL = regex.compile(r"^\s*(\p{N}{1,3}(?:[.\-‐]\p{N}{1,3}){0,4})[.)]?(?:\s+|\t)(?=\S)")
_PADDED_END = regex.compile(r"(?:\s|^)(0\p{N})\s*$")
_ROMAN_START = regex.compile(rf"^\s*({_ROMAN})[.):]\s+(?=\p{{L}})", regex.IGNORECASE)
_LETTER = regex.compile(r"^\s*(\p{L})\s*$")
_BARE = regex.compile(r"^\s*(\p{N}{1,3})[.)]?\s*$")


def _numbered_title(match, text):
    """A number before words is numbering when it is marked (a dot or parenthesis, a tab or
    wide space, zero padding, several levels) or followed by a mixed-case title; a plain
    number before capitals ("11 DE SEPTIEMBRE") reads as a date or quantity."""
    token = match[1]
    marked = match.group(0).rstrip()[-1:] in ".)" or "\t" in match.group(0)
    if marked or token[:1] == "0" or regex.search(r"[.\-‐]", token):
        return True
    rest = text[match.end() :]
    letters = [c for c in rest if c.isalpha()]
    cased = [c for c in letters if c.isupper() or c.islower()]
    return bool(cased) and not all(c.isupper() for c in cased) and len(token) <= 2


def _value(token: str) -> int | None:
    token = token.strip()
    if regex.fullmatch(r"\p{N}+", token):
        try:
            return int("".join(str(unicodedata.digit(c)) for c in token))
        except (TypeError, ValueError):
            return None
    roman = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    lowered = token.casefold()
    if lowered and all(c in roman for c in lowered):
        total = 0
        for a, b in zip(lowered, lowered[1:] + " ", strict=True):
            total += -roman[a] if b in roman and roman[b] > roman[a] else roman[a]
        return total
    return None


def numbering(text: str) -> dict | None:
    """Numbering evidence of a heading-candidate text, or None."""
    text = unicodedata.normalize("NFKC", text).strip()
    if not text:
        return None
    match = _KEYWORD.match(text)
    if match and _value(match[2]) is not None:
        word = match[1].casefold()
        return {"kind": "keyword", "role_hint": _WORD_ROLE.get(word), "depth": 1,
                "value": _value(match[2]), "position": "start"}  # fmt: skip
    match = _KEYWORD_AFTER.match(text)
    if match and _value(match[1]) is not None:
        return {"kind": "keyword", "role_hint": _WORD_ROLE.get(match[2].casefold()), "depth": 1,
                "value": _value(match[1]), "position": "start"}  # fmt: skip
    match = _CJK.match(text)
    if match:
        return {"kind": "keyword", "role_hint": _CJK_ROLE.get(match[2]), "depth": 1,
                "value": _value(match[1]), "position": "start"}  # fmt: skip
    match = _LETTER.match(text)
    if match:
        return {"kind": "letter", "role_hint": None, "depth": 1, "value": None,
                "position": "start"}  # fmt: skip
    match = _BARE.match(text)
    if match:
        return {"kind": "number", "role_hint": None, "depth": 1, "value": _value(match[1]),
                "position": "start", "padded": match[1][:1] == "0" or None}  # fmt: skip
    match = _DECIMAL.match(text)
    if match and regex.search(r"\p{L}", text[match.end() :]) and _numbered_title(match, text):
        parts = regex.split(r"[.\-‐]", match[1])
        return {"kind": "decimal", "role_hint": None, "depth": len(parts),
                "value": _value(parts[-1]), "position": "start",
                "padded": match[1][:1] == "0" or None}  # fmt: skip
    match = _PADDED_END.search(text)
    if match and regex.search(r"\p{L}", text[: match.start()]):
        return {"kind": "decimal", "role_hint": None, "depth": 1, "value": _value(match[1]),
                "position": "end", "padded": True}  # fmt: skip
    match = _ROMAN_START.match(text)
    if match and _value(match[1]) is not None:
        return {"kind": "roman", "role_hint": None, "depth": 1, "value": _value(match[1]),
                "position": "start"}  # fmt: skip
    return None
