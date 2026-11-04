"""Character rules: same-length substitutions decided from the surrounding characters. A
removed character becomes ``DELETE`` (the writer records every change in the ledger)."""

from __future__ import annotations

import re

from ..engine.text import DELETE

RSQUO, LSQUO, APOS = "’", "‘", "'"
EN_DASH, MINUS = "–", "−"


def apostrophe_straight(text: str, ctx: dict) -> tuple[str, list[str]]:
    """Item 18: a right single quote used as an apostrophe becomes U+0027.

    Between two letters/digits it is an apostrophe ("world’s", "don’t"). After a word that
    ends in s with no open single quote before it ("parents’ ") it is a plural possessive.
    Otherwise (a closing quote after an opening ‘) it is kept; unclear cases are reviewed."""
    if RSQUO not in text:
        return text, []
    chars = list(text)
    reviews = []
    open_quote = False
    for i, ch in enumerate(chars):
        if ch == LSQUO:
            open_quote = True
            continue
        if ch != RSQUO:
            continue
        before = chars[i - 1] if i else ""
        after = chars[i + 1] if i + 1 < len(chars) else ""
        if before.isalnum() and after.isalnum():
            chars[i] = APOS
        elif open_quote:
            open_quote = False  # closing single quote: kept
        elif before in ("s", "S") and (not after or not after.isalnum()):
            chars[i] = APOS
        elif before.isalnum() or after.isalnum():
            reviews.append(f"apostrophe or closing quote at offset {i}: kept U+2019")
    return "".join(chars), reviews


def double_quotes_curly(text: str, ctx: dict) -> tuple[str, list[str]]:
    """Item 19: straight double quotes become opening/closing curly quotes by position.
    An odd number of straight quotes is left as it is and reviewed."""
    if '"' not in text:
        return text, []
    positions = [i for i, ch in enumerate(text) if ch == '"']
    if len(positions) % 2:
        return text, [f"{len(positions)} straight double quotes cannot be paired"]
    chars = list(text)
    for n, i in enumerate(positions):
        chars[i] = "“" if n % 2 == 0 else "”"
    return "".join(chars), []


def soft_hyphen_removal(text: str, ctx: dict) -> tuple[str, list[str]]:
    """Soft hyphens (U+00AD) inside a line are removed ("photo\u00adcopying" ->
    "photocopying"). A soft hyphen at a line end is already a Stage 1 join decision."""
    if "\xad" not in text:
        return text, []
    return re.sub("\xad(?!\n)", DELETE, text), []


_NUMBER_AFTER = re.compile(r"\.?\d")


def minus_sign_by_context(text: str, ctx: dict) -> tuple[str, list[str]]:
    """Item 10: an en dash directly before a number is a minus sign when it stands where a
    value starts: at the start, after a space, an opening bracket, a comparison sign, a
    slash or a colon ("–196°C", "(–2.5)", "≤ –3"). Between two numbers ("2010–2020",
    "5–10") it stays an en dash. After a letter ("pH–7") it is unclear: kept and reviewed."""
    if EN_DASH not in text:
        return text, []
    chars = list(text)
    reviews = []
    for i, ch in enumerate(chars):
        if ch != EN_DASH or not _NUMBER_AFTER.match(text, i + 1):
            continue
        before = text[i - 1] if i else ""
        if before == "" or before in " \t\n([{=<>≤≥±/:;,×":
            if before in " \t\n" and i >= 2 and text[i - 2].isdigit():
                continue  # "10 – 20": a spaced range
            chars[i] = MINUS
        elif before.isdigit() or before in ")]%°":
            continue
        else:
            reviews.append(f"en dash or minus before a number at offset {i}: kept en dash")
    return "".join(chars), reviews


_RANGE = re.compile(r"(?<=[0-9ivxlcdm])[-‐‑‒](?=[0-9ivxlcdm])", re.I)


def index_range_en_dash(text: str, ctx: dict) -> tuple[str, list[str]]:
    """Item 9: hyphens between page numbers of an index locator range become en dashes.
    Applied to index entries only, inside locator ranges."""
    if not ctx.get("index_entry"):
        return text, []
    chars = list(text)
    for start, end in ctx.get("locator_ranges", ()):
        for m in _RANGE.finditer(text, start, end):
            chars[m.start()] = EN_DASH
    return "".join(chars), []
