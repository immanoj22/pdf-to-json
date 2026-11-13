"""Before -> after measures for the Step 22 add-on fixes, on one book.

    python step22_addon_measure.py BEFORE_BOOK_DIR AFTER_BOOK_DIR [--export-before DIR]
                                   [--export-after DIR] [--show N]

BOOK_DIR holds book.json; an export DIR is a DocBook delivery folder (step21_export.py output).
Measures: part/chapter titles that still carry the printed number at their start or end
(export), split sentences (step22_splits), front-matter division titles (export), heading
level changes between the two book.json files (same heading id).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import step22_splits  # noqa: E402

NUMBER = re.compile(r"^\s*(\d{1,3}|[IVXLC]{1,7})\b|\b(\d{1,3}|[IVXLC]{1,7})\s*$")


def headings(book):
    def walk(units):
        for u in units:
            yield u
            for key in ("items", "children"):
                yield from walk(u.get(key) or [])

    return {u["id"]: u for u in walk(book["content"]) if u["type"] == "heading"}


def titles(export: Path):
    """[(tag, label, title text)] of the parts, chapters and front/back divisions."""
    out = []
    files = sorted(export.rglob("*.xml"))
    for f in files:
        text = f.read_text("utf-8", errors="replace")
        for m in re.finditer(r"<(part|chapter|preface|appendix|dedication|colophon)\b([^>]*)>\s*"
                             r"<title>(.*?)</title>", text, re.S):
            label = re.search(r'label="([^"]*)"', m.group(2))
            plain = " ".join(re.sub(r"<[^>]+>", "", m.group(3)).split())
            row = (m.group(1), label.group(1) if label else "", plain)
            if row not in out:  # the main file and the chapter files hold the same divisions
                out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--export-before")
    ap.add_argument("--export-after")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    books = [json.loads((Path(d) / "book.json").read_text("utf-8")) for d in (a.before, a.after)]
    for name, book in zip(("before", "after"), books, strict=True):
        print(f"{name}: split sentences {len(step22_splits.splits(book))}")
    old, new = (headings(b) for b in books)
    changed = Counter()
    examples = []
    for hid, h in new.items():
        o = old.get(hid)
        if o is None:
            continue
        if (o.get("level"), o.get("role")) != (h.get("level"), h.get("role")):
            changed[(o.get("level"), o.get("role"), h.get("level"), h.get("role"))] += 1
            examples.append((h["pages"][0], o.get("level"), h.get("level"),
                             " ".join((h["content"]["text"] or "").split())[:40]))
    print(f"heading level/role changes: {sum(changed.values())} of {len(new)} headings "
          f"({len(set(new) - set(old))} new ids, {len(set(old) - set(new))} gone)")
    for key, n in changed.most_common(12):
        print(f"  level {key[0]} {key[1]} -> level {key[2]} {key[3]}: {n}")
    for row in examples[: a.show]:
        print("   ", row)
    for name, d in (("before", a.export_before), ("after", a.export_after)):
        if not d:
            continue
        rows = titles(Path(d))
        numbered = [r for r in rows if r[0] in ("part", "chapter") and NUMBER.search(r[2])]
        print(f"{name}: part/chapter titles with a leading or trailing number: "
              f"{len(numbered)} of {sum(r[0] in ('part', 'chapter') for r in rows)}")
        for r in numbered[: a.show]:
            print("   ", r)
        front = [r for r in rows if r[0] not in ("part", "chapter")]
        print(f"{name}: front/back division titles: {[r[2][:30] for r in front]}")


if __name__ == "__main__":
    main()
