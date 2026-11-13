"""Split sentences in a book.json: a paragraph or list item ending without sentence punctuation,
followed (in reading order, skipping page markers, figures, tables and lists between them)
by a paragraph or list item that starts with a lowercase letter, unless the model links the
two as one paragraph continued (``continues_to``).

    python step22_splits.py BOOK_JSON [--show N]
"""
import argparse
import json
import re

END = re.compile(r"[.!?:;)\]\"'”’…]\s*$")
SKIP = {"page_marker", "figure", "table", "equation"}
NAVIGATION_LISTS = {"index", "glossary", "bibliography", "contents", "toc"}


def flat(units, out):
    for u in units:
        t = u.get("type")
        if t in ("list",):
            out.append(("list", u))
            if u.get("list_type") in NAVIGATION_LISTS:
                continue  # index, glossary and bibliography entries are not sentences
            for it in u.get("items") or []:
                flat([{**it, "type": "list_item"}], out)
            continue
        if t in ("question_set", "question_entry", "question", "answer", "section", "callout",
                 "sidebar", "box") or (u.get("children") and t not in ("list_item",)):
            out.append((t, u))
            flat(u.get("children") or [], out)
            continue
        out.append((t, u))
        if t == "list_item":
            flat(u.get("children") or [], out)


def text(u):
    c = u.get("content")
    return (c or {}).get("text") if isinstance(c, dict) else None


def splits(book):
    seq = []
    flat(book["content"], seq)
    found = []
    prev = None
    between = []
    for t, u in seq:
        if t in SKIP or t == "list":
            if prev is not None:
                between.append(t)
            continue
        s = text(u)
        if s is None:
            continue
        if t == "heading":
            prev, between = None, []
            continue
        if prev is not None and t in ("paragraph", "list_item") and not (
            (prev.get("continues_to") or {}).get("unit") == u.get("id")
        ):
            first = s.lstrip()[:1]
            if first.isalpha() and first.islower():
                found.append((prev, u, list(between)))
        ptxt = s.rstrip()
        prev = u if (t in ("paragraph", "list_item") and ptxt and not END.search(ptxt)) else None
        between = []
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    b = json.load(open(a.book, encoding="utf-8"))
    f = splits(b)
    print(f"split sentences: {len(f)}")
    for p, n, bt in f[: a.show]:
        print(f"  p{p['pages'][-1]}->p{n['pages'][0]} [{','.join(bt) or '-'}] "
              f"{text(p).rstrip()[-40:]!r} / {text(n).lstrip()[:40]!r}")


if __name__ == "__main__":
    main()
