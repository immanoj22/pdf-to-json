"""Line joins inside a Step 11 item: reuse the Step 9 join, or decide a new one.

A new join (two lines that Step 9 kept in different units) gets its hyphen and split-word
decision from the unchanged Step 9 rules (``PageSegmenter.hyphen`` / ``word_join``), applied to
the page's store with the book's vocabulary and compound lexicon, so Step 11 never has its own
hyphen policy.
"""

from __future__ import annotations

from types import SimpleNamespace

from book_core.paragraphs.models import LineJoin
from book_core.paragraphs.segment import PageSegmenter

REVIEW_BELOW = 0.6


def new_join(page, vocabulary, compounds, a_line, a_text, b_line, b_text, kind, confidence,
             reasons):  # fmt: skip
    shim = SimpleNamespace(page=page, vocabulary=vocabulary or {}, compounds=compounds or {})
    a = SimpleNamespace(line=a_line, text=a_text)
    b = SimpleNamespace(line=b_line, text=b_text)
    hyphen = PageSegmenter.hyphen(shim, a, b_text)
    word = None if hyphen is not None else PageSegmenter.word_join(shim, a, b)
    return LineJoin(
        previous_line_id=a_line.id,
        next_line_id=b_line.id,
        kind=kind,
        confidence=round(confidence, 4),
        reasons=reasons,
        hyphen=hyphen,
        word=word,
        review_required=confidence < REVIEW_BELOW,
    )
