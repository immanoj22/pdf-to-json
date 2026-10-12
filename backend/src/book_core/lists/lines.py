"""Line evidence for lists and entries: markers, terms, locators, page references, questions.

Everything is read from the raw spans of one visual line and measured in the line's own
reading frame (``paragraphs.geometry``), so right-to-left and vertical lines are handled the
same way: "start" is always where reading begins. Character offsets are raw-span offsets and
become ``SpanRef`` ranges; no text is copied into the model.

- **Markers**: a bullet (a symbol character, or a dash, followed by space; or a glyph set
  apart as its own span at the line start, ``set_off_marker``), a number ("1."
  "1)" "(1)", or a number then a tab, a wide space or two spaces; "01" counts as padded), a
  single letter or a Roman numeral with the same punctuation. Letters and Roman numerals are
  ambiguous (an initial, the letter "I", the word "vi") and are decided in the stream with
  sequence evidence (``sequence_markers``). A marker may stand on a line of its own.
- **Terms**: a leading run set heavier than the rest of the line and ending at a separator
  (wide space, tab, colon, dash) is a term; definitions follow it.
- **Locators**: a tail of comma-separated page labels (any script's digits, optionally with a
  short letter prefix or a range) is an index locator list. A cross-reference is a word of a
  small multilingual cross-reference lexicon (configuration data); it decides only the locator
  kind, never a unit boundary.
- **Page references**: a short parenthesised line holding a page label ("(p. 12)").
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import regex

from book_core.model.common import SpanRef
from book_core.paragraphs.geometry import frame

BOLD, ITALIC = 1 << 4, 1 << 1
# A bullet is a symbol (So, Sm), a bullet-like punctuation, or a dash, then whitespace.
# Math operators (Sm: = + < > ±) are never markers, except the bullet-like dot operators.
BULLET_LIKE_MATH = "∙⋅∘"
_BULLET = regex.compile(r"^(\s*)([\p{So}∙⋅∘•‣⁃·◦▪▫●○■□◆◇►▶➢➤✓✔※]|[–—-])(?=\s|$)")
# Dialogue, not a dash item: the text opens with an opening question, exclamation or quotation
# mark, or carries a dialogue tag (a further dash followed by a lower-case word).
_DIALOGUE = regex.compile(r"^\s*[¿¡«“\"'‘‚„]|[.,;:!?¿¡…]\s*[—–]\s*\p{Ll}")
_NUMBER = regex.compile(r"^(\s*)(\()?(\p{N}{1,3})(?:(?(2)\)|[.)])(?=\s|$)|(?=\t| | |\s{2,}))")
_LETTER = regex.compile(r"^(\s*)(\()?(\p{L})(?(2)\)|[.)])(?=\s|$)")
_ROMAN = regex.compile(r"^(\s*)(\()?([ivxlcdm]{1,6}|[IVXLCDM]{1,6})(?(2)\)|[.)])(?=\s|$)")
_SEPARATOR = regex.compile(r"[\t   ]|\s{2,}|\s[–—]\s|:\s")
_TERMINAL_Q = "?؟？;⸮"  # question marks of several scripts (U+037E GREEK QUESTION MARK = ;)
LOCATOR = r"(?:\p{L}{0,3}\p{N}+(?:\s*[–—-]\s*\p{N}+)?|[ivxlcdm]{1,7}(?:\s*[–—-]\s*[ivxlcdm]{1,7})?)"
_LOCATOR_TAIL = regex.compile(rf"(?:^|,|\s)\s*({LOCATOR}(?:\s*[,;]\s*{LOCATOR})*)\s*[,;–—-]?\s*$")
_ONE_LOCATOR = regex.compile(rf"{LOCATOR}")
_PAGE_REF = regex.compile(r"^\s*\(\s*[^()\s]{0,8}\s*(\p{L}{0,4}\p{N}{1,4})\s*\)\s*$")
_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
# Supporting evidence only (configuration data): cross-reference words of several languages.
CROSS_REFERENCE_WORDS = frozenset(
    {"see", "véase", "vease", "voir", "siehe", "vedi", "veja", "zie", "katso",
     "see also", "véase también", "ver también", "voir aussi", "siehe auch", "vedi anche",
     "ver também", "zie ook"}
)  # fmt: skip


def roman_value(text):
    lowered = text.casefold()
    if not lowered or any(c not in _ROMAN_VALUES for c in lowered):
        return None
    total = 0
    for a, b in zip(lowered, lowered[1:] + " ", strict=True):
        value = _ROMAN_VALUES[a]
        total += -value if b != " " and _ROMAN_VALUES[b] > value else value
    return total if 0 < total < 4000 else None


@dataclass
class MarkerReading:
    start: int  # raw offset of the marker's first character
    end: int  # raw offset just after its punctuation
    type: str
    value: int | None
    punctuation: str
    padded: bool = False
    ambiguous: bool = False  # letter or Roman numeral: needs sequence evidence
    alternatives: tuple = ()  # (type, value) readings of an ambiguous marker
    signature: tuple = ()  # (parenthesised, punctuation) for sequence matching


@dataclass
class LineEvidence:
    id: str
    stream_id: str
    stream_kind: str
    unit_id: str
    unit_kind: str
    raw: str
    text: str  # NFKC, evidence only
    spans: list  # [(span id, raw start, raw end, bold, italic, size)]
    start: float
    end: float
    block: float
    size: float
    blank: bool
    marker: MarkerReading | None = None
    own_marker_line: bool = False  # the line is only a marker
    text_start: float | None = None  # inline position where the item text begins
    term_end: int | None = None  # raw offset where a leading term ends (exclusive)
    term_weight: float = 0.0
    locators: list = field(default_factory=list)  # [(raw start, raw end, kind)]
    tail_locator: bool = False  # the line ends with a locator list
    open_end: bool = False  # ends with a comma, semicolon, hyphen or dash
    page_ref: bool = False  # a parenthesised page reference only
    question: bool = False
    bold_share: float = 0.0
    italic_share: float = 0.0


def _spans(store, line):
    rows, offset = [], 0
    for sid in line.span_ids:
        span = store.spans[sid]
        font = span.font.split("+", 1)[-1].casefold()
        bold = bool(span.flags & BOLD) or "bold" in font or "black" in font or "heavy" in font
        italic = bool(span.flags & ITALIC) or "italic" in font or "oblique" in font
        rows.append((sid, offset, offset + len(span.raw_text), bold, italic, span.size))
        offset += len(span.raw_text)
    return rows


def refs_for(spans, start, end):
    """SpanRefs covering raw offsets [start, end) of a line (whole spans are not split)."""
    refs = []
    for sid, a, b, *_ in spans:
        low, high = max(a, start), min(b, end)
        if low < high:
            refs.append(SpanRef(span_id=sid, start=low - a, end=high - a))
    return refs


def _weight_shares(spans, raw):
    letters = bold = italic = 0
    for _, a, b, is_bold, is_italic, _ in spans:
        count = sum(not c.isspace() for c in raw[a:b])
        letters += count
        bold += count * is_bold
        italic += count * is_italic
    return (bold / letters, italic / letters) if letters else (0.0, 0.0)


def read_marker(raw):
    """The marker reading at the start of a raw line, or None."""
    match = _BULLET.match(raw)
    if match:
        glyph = match.group(2)
        kind = "dash" if glyph in "–—-" else "bullet"
        return MarkerReading(match.start(2), match.end(2), kind, None, "none",
                             signature=(False, glyph))  # fmt: skip
    match = _NUMBER.match(raw)
    if match:
        digits = match.group(3)
        paren = bool(match.group(2))
        tail = raw[match.end(3) : match.end(3) + 1]
        punctuation = (
            "parentheses" if paren else {".": "period", ")": "parenthesis"}.get(tail, "space")
        )
        end = match.end(3) + (1 if punctuation != "space" else 0)
        value = int(unicodedata.numeric(digits[0]) if len(digits) == 1 else int(
            "".join(str(int(unicodedata.digit(c))) for c in digits)))  # fmt: skip
        return MarkerReading(match.start(2) if paren else match.start(3), end, "decimal", value,
                             punctuation, padded=len(digits) > 1 and digits[0] in "0０",
                             signature=(paren, punctuation))  # fmt: skip
    alternatives = []
    roman = _ROMAN.match(raw)
    if roman:
        value = roman_value(roman.group(3))
        if value:
            kind = "upper_roman" if roman.group(3).isupper() else "lower_roman"
            alternatives.append((kind, value, roman))
    letter = _LETTER.match(raw)
    if letter and letter.group(3).isalpha():
        char = letter.group(3)
        if "a" <= char.casefold() <= "z":
            value = ord(char.casefold()) - ord("a") + 1
        else:
            value = None  # other scripts: sequence by code point
        kind = "upper_alpha" if char.isupper() else "lower_alpha"
        alternatives.append((kind, value if value else ord(char.casefold()), letter))
    if not alternatives:
        return None
    kind, value, match = alternatives[0]
    paren = bool(match.group(2))
    punct = raw[match.end(3) : match.end(3) + 1]
    punctuation = "parentheses" if paren else {".": "period", ")": "parenthesis"}[punct]
    return MarkerReading(
        match.start(2) if paren else match.start(3), match.end(3) + 1, kind, value, punctuation,
        ambiguous=True, alternatives=tuple((k, v) for k, v, _ in alternatives),
        signature=(paren, punctuation),
    )  # fmt: skip


# A glyph set off as its own span is never a marker when it opens text (opening brackets and
# quotes, other punctuation) or is a decimal digit (numbers are read by ``read_marker``).
_NOT_SET_OFF = frozenset({"Nd", "Ps", "Pe", "Pi", "Po", "Pc", "Zs", "Zl", "Zp"})


def set_off_marker(raw, spans, store):
    """A bullet set apart as a span of its own at the line start, or None.

    Typeset bullets often sit right against the item text ("◆Thyroid gland") or come from a
    symbol font whose glyphs extract as letters, numbers or control characters ("Ǌ", "¾").
    A single glyph alone in its span (whitespace aside), followed by item text (a letter or
    number), is read as a bullet. Its signature carries the glyph and the font change into the
    text; only a known bullet glyph counts on its own: any other glyph needs a second line of
    the block with the same signature at the same start (repetition evidence,
    ``PageLister.general``), so one italic variable or Greek letter opening a line ("p < .001",
    "α = .77") never makes a list. A colour change is not required.
    """
    first = len(raw) - len(raw.lstrip())
    if first >= len(raw):
        return None
    owner = next((row for row in spans if row[1] <= first < row[2]), None)
    if owner is None or raw[owner[1] : owner[2]].strip() != raw[first]:
        return None
    following = next((row for row in spans if row[1] >= owner[2]
                      and raw[row[1] : row[2]].strip()), None)  # fmt: skip
    glyph = raw[first]
    if following is None or unicodedata.category(glyph) in _NOT_SET_OFF:
        return None
    if not regex.match(r"\s*[\p{L}\p{N}]", raw[first + 1 :]):
        return None  # an expression ("p < .05", "F(1, 147)"), not item text
    mark, text = store.spans[owner[0]], store.spans[following[0]]
    if unicodedata.category(glyph) == "Sm" and glyph not in BULLET_LIKE_MATH:
        return None  # a math operator opening an expression ("= 3x", "+ 4y")
    symbol = unicodedata.category(glyph) in {"So", "Pd", "Co"} or glyph in BULLET_LIKE_MATH
    if not symbol and mark.font == text.font and mark.color == text.color:
        return None  # a letter set like the text is part of it, not a set-off marker
    kind = "dash" if glyph in "–—-" else "bullet"
    return MarkerReading(first, first + 1, kind, None, "none",
                         signature=(False, glyph, mark.font, text.font))  # fmt: skip


def _term(spans, raw, after):
    """(raw offset where a heavier leading run ends at a separator, its letter share)."""
    content = [(a, b, bold) for _, a, b, bold, _, _ in spans
               if b > after and raw[max(a, after) : b].strip()]  # fmt: skip
    if len(content) < 2 or not content[0][2]:
        return None, 0.0
    end = next((a for a, _, bold in content if not bold), None)
    if end is None:
        return None, 0.0
    lead = raw[after:end]
    if not regex.search(r"\p{L}", lead):
        return None, 0.0
    joint = lead[-3:] + raw[end : end + 2]
    trimmed = lead.rstrip()
    if not (_SEPARATOR.search(joint) or trimmed.endswith((":", ".", "–", "—"))):
        return None, 0.0  # a weight change inside running text is no term
    share = sum(c.isalpha() for c in lead) / max(1, sum(c.isalpha() for c in raw))
    return after + len(trimmed), share


def read_locators(raw, spans):
    """[(start, end, kind)] of a locator tail and whether the line ends with one.

    A cross-reference (a word of the cross-reference lexicon after punctuation or at the line
    start) runs to the line end; page locators are read in the text before it. Only the
    locator kind depends on the lexicon, never a unit boundary.
    """
    xref = None
    for word in sorted(CROSS_REFERENCE_WORDS, key=len, reverse=True):
        hit = regex.search(
            rf"(?:(?<=[.,;(]\s*)|^\s*){regex.escape(word)}\s+\p{{L}}", raw, flags=regex.IGNORECASE
        )
        if hit:
            xref = hit.start()
            break
    head = raw if xref is None else raw[:xref].rstrip(" ,.;(")
    found = []
    match = _LOCATOR_TAIL.search(head)
    if match and not regex.search(r"\p{N}", match.group(1)):
        match = None  # Roman-looking words alone ("mix", "civil") are no locators
    if match:
        for item in _ONE_LOCATOR.finditer(head, match.start(1), match.end(1)):
            kind = "range" if regex.search(r"[–—-]", item.group()) else "page"
            found.append((item.start(), item.end(), kind))
    if xref is not None:
        found.append((xref, len(raw.rstrip()), "cross_reference"))
        return found, False
    ends = bool(match) and raw[match.end(1) :].strip() in {"", ",", ";"}
    return found, ends and not raw.rstrip().endswith((",", ";"))


def line_evidence(store, line, stream, unit):
    spans = _spans(store, line)
    raw = "".join(store.spans[s].raw_text for s in line.span_ids)
    text = unicodedata.normalize("NFKC", raw)
    f = frame(line)
    evidence = LineEvidence(
        id=line.id, stream_id=stream.id, stream_kind=stream.kind, unit_id=unit.id,
        unit_kind=unit.kind, raw=raw, text=text, spans=spans, start=f.start, end=f.end,
        block=f.block, size=f.size, blank=not raw.strip(),
    )  # fmt: skip
    if evidence.blank:
        return evidence
    evidence.bold_share, evidence.italic_share = _weight_shares(spans, raw)
    marker = read_marker(raw) or set_off_marker(raw, spans, store)
    if marker is not None and marker.type == "dash" and _DIALOGUE.search(raw[marker.end :]):
        marker = None  # a dialogue line ("—¿Qué haces? —preguntó"), not a dash item
    if marker is not None:
        evidence.marker = marker
        rest = raw[marker.end :]
        evidence.own_marker_line = not regex.search(r"[\p{L}\p{N}]", rest)
        offset = marker.end + len(rest) - len(rest.lstrip())
        evidence.text_start = _inline_position(line, store, spans, offset, f)
    after = marker.end if marker is not None else 0
    after += len(raw[after:]) - len(raw[after:].lstrip())
    evidence.term_end, evidence.term_weight = _term(spans, raw, after)
    evidence.locators, evidence.tail_locator = read_locators(raw, spans)
    stripped = raw.rstrip()
    evidence.open_end = stripped.endswith((",", ";", "-", "‐", "–", "—", "­"))
    evidence.page_ref = bool(_PAGE_REF.match(text))
    evidence.question = stripped[-1:] in _TERMINAL_Q or stripped.endswith("?)")
    return evidence


def _inline_position(line, store, spans, offset, f):
    """Inline position (reading frame) of the character at raw ``offset`` of the line."""
    dx, dy = line.direction
    norm = (dx * dx + dy * dy) ** 0.5 or 1.0
    dx, dy = dx / norm, dy / norm
    for sid, a, b, *_ in spans:
        if a <= offset < b:
            box = store.spans[sid].bbox
            along = [x * dx + y * dy for x in (box.x0, box.x1) for y in (box.y0, box.y1)]
            low, high = min(along), max(along)
            share = (offset - a) / max(1, b - a)
            if line.text_direction == "rtl":  # reading starts at the high end
                return -(high - (high - low) * share)
            return low + (high - low) * share
    return f.start


def sequence_markers(lines):
    """Resolve letter/Roman markers of one stream with sequence evidence.

    An ambiguous marker counts when another marker of the stream with the same punctuation
    has the adjacent value in one of its readings (a, b; ii, iii); its reading is the one
    the neighbours share. Returns {line id: reason} for ambiguous markers kept.
    """
    readings = {}
    for line in lines:
        m = line.marker
        if m is not None and m.ambiguous:
            readings[line.id] = m
    signatures = {}
    for m in readings.values():
        for kind, value in m.alternatives:
            signatures.setdefault((m.signature, kind), set()).add(value)
    kept = {}
    for lid, m in readings.items():
        for kind, value in m.alternatives:
            values = signatures.get((m.signature, kind), set())
            if value - 1 in values or value + 1 in values:
                m.type, m.value, m.ambiguous = kind, value, False
                kept[lid] = f"{kind.replace('_', ' ')} marker with sequence evidence"
                break
    for lid in readings:
        if lid not in kept:
            next(line for line in lines if line.id == lid).marker = None
    return kept
