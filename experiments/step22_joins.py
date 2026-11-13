"""New joins between two runs: units of the later book.json that hold lines of two or more
units of the earlier one. Prints the join point for hand checking.

    python step22_joins.py BEFORE_BOOK_JSON AFTER_BOOK_JSON [--show N]
"""
import argparse
import json


def units(book):
    out = []

    def walk(us):
        for u in us:
            c = u.get("content")
            if isinstance(c, dict) and (u.get("refs") or {}).get("lines"):
                out.append(u)
            for key in ("items", "children"):
                walk(u.get(key) or [])

    walk(book["content"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--show", type=int, default=10**6)
    a = ap.parse_args()
    old = units(json.load(open(a.before, encoding="utf-8")))
    new = units(json.load(open(a.after, encoding="utf-8")))
    owner = {}
    for u in old:
        for line in u["refs"]["lines"]:
            owner.setdefault(line, u)
    joins = []
    for u in new:
        seen = []
        for line in u["refs"]["lines"]:
            o = owner.get(line)
            if o is not None and (not seen or seen[-1]["id"] != o["id"]):
                seen.append(o)
        for x, y in zip(seen, seen[1:]):
            joins.append((u, x, y))
    print(f"new joins: {len(joins)}")
    for u, x, y in joins[: a.show]:
        left = " ".join((x["content"]["text"] or "").split())[-45:]
        right = " ".join((y["content"]["text"] or "").split())[:45]
        print(f"  p{x['pages'][-1]} {x['type']}/{x.get('role')} -> p{y['pages'][0]} "
              f"{y['type']}/{y.get('role')}: {left!r} | {right!r}")


if __name__ == "__main__":
    main()
