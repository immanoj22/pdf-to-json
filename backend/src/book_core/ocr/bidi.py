"""Visual-to-logical order for recognizer output of right-to-left lines (any RTL script).

Some recognizers (PP-OCRv5's CTC recognizers) emit a line's characters in visual order, left
to right across the image. For a line whose strong characters are mostly right-to-left
(Unicode bidirectional classes R and AL: Arabic, Hebrew, Syriac, Thaana, N'Ko, ...), the
logical order is recovered by the inverse of the Unicode bidirectional reordering of one
right-to-left paragraph line:

- the text is split into grapheme clusters (a base with its combining marks stays one unit);
- clusters are typed: strong left-to-right (L), strong right-to-left (R, AL), digits (EN, AN
  and the separators between two digits), or neutral;
- neutrals between two left-to-right runs (only neutrals between them) join them, so a Latin
  phrase stays one run; other neutrals resolve to right-to-left (the paragraph direction);
- left-to-right runs and digit runs keep their internal order; the sequence of runs is
  reversed, and right-to-left runs are reversed cluster by cluster, with paired brackets
  mirrored (Unicode Bidi_Mirrored characters with a mirror image).

A line with fewer strong right-to-left than left-to-right characters (or none) is returned
unchanged; a tie reads as right-to-left (the recognizer was chosen for that script).
Nothing script- or language-specific is assumed beyond Unicode properties.
"""

from __future__ import annotations

import unicodedata

import regex

RTL = frozenset({"R", "AL"})
NUMBER = frozenset({"EN", "AN"})
SEPARATOR = frozenset({"CS", "ES", "ET"})  # inside a number: 1,234.5  12:30  5%
# Bidi_Mirroring_Glyph pairs of the common bracket characters (UCD BidiMirroring.txt).
OPEN_CLOSE = "()[]{}<>«»‹›⁅⁆⁽⁾₍₎〈〉《》「」『』【】〔〕"
MIRROR = dict(zip(OPEN_CLOSE, ")(][}{><»«›‹⁆⁅⁾⁽₎₍〉〈》《」「』『】【〕〔", strict=True))


def _kind(cluster):
    classes = [unicodedata.bidirectional(ch) for ch in cluster]
    if classes[0] in RTL:
        return "R"
    if classes[0] == "L":
        return "L"
    if classes[0] in NUMBER:
        return "D"
    if classes[0] in SEPARATOR:
        return "S"
    return "N"


def mostly_rtl(text):
    """At least as many strong right-to-left characters as left-to-right ones (and some)."""
    right = sum(unicodedata.bidirectional(ch) in RTL for ch in text)
    left = sum(unicodedata.bidirectional(ch) == "L" for ch in text)
    return right > 0 and right >= left


def visual_to_logical(text):
    """The logical order of a visually ordered right-to-left line (else ``text``)."""
    if not mostly_rtl(text):
        return text
    clusters = regex.findall(r"\X", text)
    kinds = [_kind(c) for c in clusters]
    # Separators between two digits belong to the number.
    for i, kind in enumerate(kinds):
        if kind == "S":
            left = next((kinds[j] for j in range(i - 1, -1, -1) if kinds[j] != "S"), None)
            right = next((kinds[j] for j in range(i + 1, len(kinds)) if kinds[j] != "S"), None)
            kinds[i] = "D" if left == "D" and right == "D" else "N"
    # Neutrals between two left-to-right runs join them; the others are right-to-left.
    resolved = list(kinds)
    i = 0
    while i < len(kinds):
        if kinds[i] != "N":
            i += 1
            continue
        j = i
        while j < len(kinds) and kinds[j] == "N":
            j += 1
        before = kinds[i - 1] if i > 0 else None
        after = kinds[j] if j < len(kinds) else None
        side = "L" if before == "L" and after == "L" else "R"
        resolved[i:j] = [side] * (j - i)
        i = j
    runs = []
    for cluster, kind in zip(clusters, resolved, strict=True):
        if runs and runs[-1][0] == kind:
            runs[-1][1].append(cluster)
        else:
            runs.append((kind, [cluster]))
    out = []
    for kind, items in reversed(runs):
        if kind == "R":
            out.extend(_mirror(c) for c in reversed(items))
        else:
            out.extend(items)
    return "".join(out)


def _mirror(cluster):
    return MIRROR.get(cluster[0], cluster[0]) + cluster[1:]
