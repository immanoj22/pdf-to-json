"""Print the content of some pages of a book JSON in a readable outline (inspection).

Usage: python step17_show.py PATH PAGE [PAGE ...]
"""

import json
import sys


def text(node):
    content = node.get("content")
    if isinstance(content, dict):
        value = content["text"].replace("\n", "⏎")
        spans = ",".join(
            f"{s['kind']}[{s['start']}:{s['end']}]" for s in content["spans"][:6]
        )
        joins = ",".join(f"{j['decision']}@{j['at']}" for j in content["joins"][:4])
        return f"{value[:110]!r} {{{spans}}} {{{joins}}}"
    return ""


def show(node, depth=0):
    pad = "  " * depth
    kind = node.get("type", "?")
    extra = []
    for key in ("level", "role", "list_type", "box_kind", "kind", "output", "label"):
        if key in node and node[key] not in (None, "body"):
            extra.append(f"{key}={node[key]}")
    if node.get("marker"):
        extra.append(f"marker={node['marker']['text']!r}")
    if node.get("review_status") not in (None, "ok"):
        extra.append(
            f"[{node['review_status']}: {'; '.join(node.get('flags', []))[:80]}]"
        )
    for key in ("continues_from", "continues_to"):
        if node.get(key):
            extra.append(f"{key}={node[key]['unit']}")
    print(f"{pad}{node.get('order', '')} {kind} {' '.join(extra)} {text(node)}")
    for child in node.get("items", []) + node.get("children", []):
        show(child, depth + 1)
    for cell in node.get("cells", [])[:6]:
        print(
            f"{pad}  cell r{cell['row']}c{cell['column']} {cell['role']}:",
            " | ".join(text(c)[:50] for c in cell["content"]),
        )
    if kind == "figure":
        for key in ("captions", "credits", "text"):
            for item in node.get(key, []):
                print(f"{pad}  {key}: {text(item)[:100]}")


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as stream:
        book = json.load(stream)
    pages = {int(p) for p in sys.argv[2:]}
    for unit in book["content"]:
        if set(unit["pages"]) & pages:
            show(unit)
