"""Retained PDF benchmark tokens in native extraction order, with stable ledger token ids.

This is a read-only view of the span store: the same retention rule as the ledger (non-blank
line whose centre lies in the page content frame) and the same token ids. Native order is
extraction evidence only; nothing here claims semantic reading order.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from book_core.ledger.tokenization import line_tokens
from book_core.model.spans import ExtractedPage

# Characters that, at the end of a line, indicate a word broken across lines.
LINE_BREAK_HYPHENS = "-­‐‑"
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class PdfToken:
    id: str
    page: int
    ordinal: int  # position in the page's retained-token sequence
    value: str
    line: int  # ordinal of the retained line on its page
    line_final: bool
    hyphen_break: bool  # last token of a line whose raw text ends with a hyphen
    soft_hyphen: bool  # the raw line contains U+00AD next to this token's text


@dataclass(frozen=True)
class PdfLine:
    page: int
    ordinal: int
    id: str
    key: str  # NFKC text with digits masked: repetition evidence for furniture
    center: tuple[float, float]
    token_count: int


@dataclass(frozen=True)
class PdfPage:
    page: int
    tokens: tuple[PdfToken, ...]
    lines: tuple[PdfLine, ...]

    @property
    def digest(self) -> str:
        """Identity of the token sequence, so stored references can be re-validated."""
        return hashlib.sha256("\n".join(t.id for t in self.tokens).encode()).hexdigest()


def page_tokens(page: ExtractedPage) -> PdfPage:
    store = page.store
    tokens: list[PdfToken] = []
    lines: list[PdfLine] = []
    for line in store.lines:
        raw = store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        found = list(line_tokens(store, line))
        line_ordinal = len(lines)
        stripped = raw.rstrip()
        normalized = unicodedata.normalize("NFKC", raw)
        lines.append(
            PdfLine(
                page=line.page,
                ordinal=line_ordinal,
                id=line.id,
                key=_DIGIT.sub("#", " ".join(normalized.split())),
                center=((line.bbox.x0 + line.bbox.x1) / 2, (line.bbox.y0 + line.bbox.y1) / 2),
                token_count=len(found),
            )
        )
        for position, token in enumerate(found):
            final = position == len(found) - 1
            tokens.append(
                PdfToken(
                    id=token.id,
                    page=line.page,
                    ordinal=len(tokens),
                    value=token.value,
                    line=line_ordinal,
                    line_final=final,
                    hyphen_break=final and stripped[-1:] in LINE_BREAK_HYPHENS,
                    soft_hyphen="­" in raw,
                )
            )
    return PdfPage(page=page.geometry.page, tokens=tuple(tokens), lines=tuple(lines))


def book_tokens(pages: Iterable[ExtractedPage]) -> list[PdfPage]:
    return [page_tokens(page) for page in pages]
