"""Inline structure of a unit as neutral metadata on span ranges.

- Style runs: consecutive spans sharing bold, italic, superscript, subscript, small caps and
  colour emphasis (a colour that differs from the unit's dominant colour). Plain runs are not
  recorded. Superscript is the extractor's flag or a smaller span raised above the line;
  subscript a smaller span lowered below it. Small caps come from the font name.
- Language runs: the configured language detector (Settings languages; Lingua) over the
  unit's NFKC text. Its segment offsets are mapped back to source spans; a span whose NFKC
  form changes length is mapped as a whole (no invented character offsets).
Nothing here copies text into the model or decides anything structural.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

import regex

from book_core.model.common import SpanRef
from book_core.paragraphs.models import LanguageRun, StyleRun

SUPERSCRIPT_FLAG = 1
BOLD, ITALIC = 1 << 4, 1 << 1
SHIFT = 0.15  # font sizes a smaller span must sit above/below the line centre
SMALLER = 0.85
_SMALL_CAPS = regex.compile(r"(?i)small\s*caps|smcp|(?<![a-z])sc(?![a-z])")


def _attributes(span, line, dominant_color):
    size = line.font_size or span.size
    centre = (span.bbox.y0 + span.bbox.y1) / 2
    line_centre = (line.bbox.y0 + line.bbox.y1) / 2
    smaller = span.size <= SMALLER * size
    raised = smaller and line_centre - centre >= SHIFT * size
    lowered = smaller and centre - line_centre >= SHIFT * size
    font = span.font.split("+", 1)[-1]
    return (
        bool(span.flags & BOLD) or "bold" in font.casefold(),
        bool(span.flags & ITALIC) or "italic" in font.casefold() or "oblique" in font.casefold(),
        bool(span.flags & SUPERSCRIPT_FLAG) or raised,
        lowered,
        bool(_SMALL_CAPS.search(font)),
        span.color if span.color != dominant_color else None,
    )


def style_runs(store, lines):
    """StyleRuns over the spans of ``lines`` (VisualLines in unit order)."""
    weights = Counter()
    for line in lines:
        for sid in line.span_ids:
            span = store.spans[sid]
            weights[span.color] += max(1, len(span.raw_text.strip()))
    dominant = weights.most_common(1)[0][0] if weights else None
    runs, current, attrs = [], [], None
    for line in lines:
        for sid in line.span_ids:
            span = store.spans[sid]
            if not span.raw_text.strip():
                continue
            value = _attributes(span, line, dominant)
            if value != attrs and current:
                runs.append((attrs, current))
                current = []
            attrs = value
            current.append(SpanRef(span_id=sid))
    if current:
        runs.append((attrs, current))
    return [
        StyleRun(
            refs=refs,
            bold=a[0],
            italic=a[1],
            superscript=a[2],
            subscript=a[3],
            small_caps=a[4],
            color=a[5],
        )
        for a, refs in runs
        if any(a[:5]) or a[5] is not None
    ]


def unit_text(store, lines):
    """NFKC text of a unit (lines joined by a space) and, per character, its source span."""
    parts, owners = [], []
    for index, line in enumerate(lines):
        if index:
            parts.append(" ")
            owners.append(None)
        for sid in line.span_ids:
            normalized = unicodedata.normalize("NFKC", store.spans[sid].raw_text)
            parts.append(normalized)
            owners.extend([sid] * len(normalized))
    return "".join(parts), owners


def language_runs(store, lines, detector):
    """(language, confidence, LanguageRuns) for a unit; ('und', 0, []) without evidence."""
    if detector is None:
        return "und", 0.0, []
    text, owners = unit_text(store, lines)
    evidence = detector.detect(text)
    runs = []
    if evidence.mixed:
        for segment in evidence.segments:
            spans = list(dict.fromkeys(s for s in owners[segment.start : segment.end] if s))
            if spans:
                runs.append(
                    LanguageRun(
                        refs=[SpanRef(span_id=s) for s in spans],
                        language=segment.language,
                        confidence=min(1.0, max(0.0, segment.confidence)),
                    )
                )
    return evidence.language, min(1.0, max(0.0, evidence.confidence)), runs
