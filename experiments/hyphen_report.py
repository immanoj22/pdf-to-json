"""Per book: line-end hyphenated words that read apart, before and after the loader decides the
missing joins (book_adapters.engine.joins). Read-only on the published books.

Usage: PYTHONPATH=backend/src python experiments/hyphen_report.py LABEL BOOK_JSON [LABEL BOOK_JSON ...]
"before" = line ends with a hyphen (hard or soft) and no join record in the book as Stage 1 wrote
it; "after" = what is still apart once the loader has decided; "joined" = what the loader decided
(word = a split with no hyphen at all)."""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

from book_adapters.engine.joins import infer_joins, text_records

SOFT = "­"


def apart(records) -> Counter:
    out = Counter()
    for c in records:
        t = c["text"]
        have = {j["at"] for j in c.get("joins") or ()}
        i = t.find("\n")
        while i != -1:
            if i and i + 1 < len(t) and i not in have and t[i + 1].isalpha() and t[i - 1] in "-" + SOFT:
                out["soft hyphen" if t[i - 1] == SOFT else "hard hyphen"] += 1
            i = t.find("\n", i + 1)
    return out


def main(args: list[str]) -> None:
    for label, path in zip(args[::2], args[1::2]):
        p = Path(path)
        raw = json.loads((p / "book.json" if p.is_dir() else p).read_text("utf-8"))
        before = apart(text_records(raw))  # the book as Stage 1 wrote it
        decided = copy.deepcopy(raw)  # the same text records, with the missing joins decided
        added = infer_joins(text_records(decided))
        after = apart(text_records(decided))
        print(label)
        print(f"   before: {sum(before.values()):4} apart {dict(before)}")
        print(f"   joined by the loader: {dict(added)}")
        print(f"   after : {sum(after.values()):4} apart {dict(after)}")


if __name__ == "__main__":
    main(sys.argv[1:])
