"""Step 22: what changed between two runs of one book, token by token.

A token is a whitespace-separated word of any text in book.json (units, figure texts, table
cells, furniture). Compares the earlier run with the later one:

- the tokens of all text together (a word split in two or two words joined shows here);
- the tokens that moved between the running text and the furniture (a page number or running
  head now read as furniture);
- the page labels read.

Usage: python step22_tokens.py OLD_BOOK_DIR NEW_BOOK_DIR [--examples 10]
"""

import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path


def texts(node, where, out):
    """(where, page, text) of every text record under ``node``."""
    if isinstance(node, dict):
        content = node.get("content")
        own = isinstance(content, dict) and isinstance(content.get("text"), str)
        marker = node.get("marker")
        if own and isinstance(marker, dict) and isinstance(marker.get("text"), str):
            # A list item's printed marker ("3.") is book text too.
            pages = node.get("pages") or ([node["page"]] if "page" in node else [0])
            out.append((where, pages[0], marker["text"]))
        if own:
            pages = node.get("pages") or ([node["page"]] if "page" in node else [0])
            out.append((where, pages[0], content["text"]))
        for key, value in node.items():
            if not (own and key == "content"):
                texts(value, "furniture" if key == "furniture" else where, out)
    elif isinstance(node, list):
        for item in node:
            texts(item, where, out)


def load(folder):
    book = json.loads((Path(folder) / "book.json").read_text("utf-8"))
    out = []
    texts(book, "content", out)
    return book, out


def tokens(rows):
    all_tokens, by_place = Counter(), Counter()
    for where, page, text in rows:
        for token in unicodedata.normalize("NFKC", text).split():
            all_tokens[token] += 1
            by_place[(where, token)] += 1
    return all_tokens, by_place


def sequences(rows):
    """{page: [token, ...]} in the order the units read."""
    found = {}
    for where, page, text in rows:
        if where == "content":
            found.setdefault(page, []).extend(unicodedata.normalize("NFKC", text).split())
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--examples", type=int, default=10)
    args = parser.parse_args()
    old_book, old_rows = load(args.old)
    new_book, new_rows = load(args.new)
    old_all, old_place = tokens(old_rows)
    new_all, new_place = tokens(new_rows)
    lost, gained = old_all - new_all, new_all - old_all
    print(f"tokens: old {sum(old_all.values())}, new {sum(new_all.values())}; "
          f"lost {sum(lost.values())}, gained {sum(gained.values())}")
    for name, found in (("lost", lost), ("gained", gained)):
        for token, n in found.most_common(args.examples):
            print(f"  {name}: {token!r} x{n}")
    moved = Counter()
    for (where, token), n in (old_place - new_place).items():
        if (("furniture" if where == "content" else "content"), token) in new_place:
            moved[(where, token)] += n
    print(f"tokens that moved between content and furniture: {sum(moved.values())}")
    for (where, token), n in moved.most_common(args.examples):
        print(f"  {token!r} x{n}: was {where}, now {'furniture' if where == 'content' else 'content'}")
    old_seq, new_seq = sequences(old_rows), sequences(new_rows)
    differ = [p for p in sorted(set(old_seq) | set(new_seq)) if old_seq.get(p) != new_seq.get(p)]
    print(f"pages whose reading order or units differ: {len(differ)} of {len(old_seq)}")
    for page in differ[: args.examples]:
        a, b = old_seq.get(page, []), new_seq.get(page, [])
        at = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y),
                  min(len(a), len(b)))  # fmt: skip
        print(f"  page {page}: first difference at word {at}: "
              f"{' '.join(a[at : at + 6])!r} -> {' '.join(b[at : at + 6])!r}")
    old_labels = {p["index"]: p["label"] for p in old_book["pages"]}
    new_labels = {p["index"]: p["label"] for p in new_book["pages"]}
    changed = [(i, old_labels[i], new_labels[i]) for i in old_labels if old_labels[i] != new_labels[i]]
    print(f"page labels changed: {len(changed)} of {len(old_labels)}; examples {changed[:args.examples]}")


if __name__ == "__main__":
    main()
