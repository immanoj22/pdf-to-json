"""A running head set larger than the body is still a running head, not a heading.

Step 18: a book's 18 pt chapter running heads (alternating sides with page parity, the
chapter's name on each of its pages) were typed as headings. A title prints once; a running
head recurs as the outermost isolated line.
"""

import json
from pathlib import Path

import pymupdf
from test_continuity import _run

WORDS = (
    "The valley trade grew along the river while the merchants of the coast built ports "
    "and the inland towns sent grain and wool to the markets of the capital each autumn "
).split()


def book(path):
    with pymupdf.open() as doc:
        for number in range(1, 9):
            page = doc.new_page(width=612, height=792)
            head = "Persia" if number <= 4 else "Arabia"
            width = pymupdf.get_text_length(head, "hebo", 18)
            x = 576 - width if number % 2 else 36
            page.insert_text((x, 50), head, fontsize=18, fontname="hebo")
            for k in range(40):
                words = WORDS[(number * 5 + k * 3) % 24 :] + WORDS
                page.insert_text((36, 90 + 15 * k), " ".join(words[:14]), fontsize=9)
            page.insert_text((300, 760), str(number + 40), fontsize=8)
        doc.save(path)
    return path


def test_large_alternating_running_heads_are_furniture(tmp_path):
    result = _run(book(tmp_path / "heads.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    data = json.loads((Path(result["book_json"]) / "book.json").read_text("utf-8"))
    heads = [f["content"]["text"] for f in data["furniture"] if f["kind"] == "running_head"]
    assert heads == ["Persia"] * 4 + ["Arabia"] * 4
    headings = []

    def walk(node):
        if node.get("type") == "heading":
            headings.append(node["content"]["text"])
        for key in ("content", "children", "items"):
            if isinstance(node.get(key), list):
                for child in node[key]:
                    walk(child)

    for top in data["content"]:
        walk(top)
    assert not {"Persia", "Arabia"} & set(headings)
