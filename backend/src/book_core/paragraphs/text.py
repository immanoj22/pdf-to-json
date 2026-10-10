"""Derived text view of a paragraph unit (never stored; raw spans are never rewritten).

Lines are joined with a space, except across a line-end hyphen (``join``/``soft_join`` drop
the hyphen and concatenate the halves; ``keep`` keeps it and adds no space) and across a word
join, where no space is inserted. The result is NFKC normalized. ``raw=True`` returns the
original line texts joined by newlines, untouched.
"""

from __future__ import annotations

import unicodedata


def unit_text(store, layout, unit, raw=False, extra_joins=()):
    lines = {line.id: line for line in layout.lines}
    texts = ["".join(store.spans[s].raw_text for s in lines[lid].span_ids) for lid in unit.line_ids]
    if raw:
        return "\n".join(texts)
    joins = {(j.previous_line_id, j.next_line_id): j for j in (*unit.joins, *extra_joins)}
    out = texts[0].rstrip() if len(texts) > 1 else texts[0]
    for (previous, following), text in zip(
        zip(unit.line_ids, unit.line_ids[1:], strict=False), texts[1:], strict=True
    ):
        join = joins.get((previous, following))
        piece = text.strip()
        if join is not None and join.hyphen is not None and join.hyphen.choice != "keep":
            out = out.rstrip()[:-1] + piece  # break hyphen removed in the view only
        elif join is not None and join.hyphen is not None:
            out = out.rstrip() + piece  # real compound: hyphen kept, no space
        elif join is not None and join.word is not None:
            out = out.rstrip() + piece
        else:
            out = f"{out.rstrip()} {piece}"
    return unicodedata.normalize("NFKC", out)
