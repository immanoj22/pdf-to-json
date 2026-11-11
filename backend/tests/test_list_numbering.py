"""Step 21: a numbered list whose numerals are set flush right stays one list across 9 -> 10."""

import json
from pathlib import Path

import pymupdf
from test_continuity import _run

FIRST = "Smith J, Jones K. A prospective study of blood pressure in young adults and its"
SECOND = "relation to lifestyle and family history. J Hypertens 2019;37:1021-30."


def bibliography(path, first=7, last=14):
    with pymupdf.open() as doc:
        page = doc.new_page(width=560, height=800)
        page.insert_text((60, 70), "Bibliography", fontsize=18, fontname="hebo")
        y = 110
        for number in range(first, last + 1):
            label = f"{number}."
            # numerals flush right at x = 80 (a longer number starts further left), the entry
            # text on the same baseline from x = 86, its second line hanging at the same x
            x = 80 - pymupdf.get_text_length(label, "helv", 9)
            page.insert_text((x, y), label, fontsize=9, fontname="helv")
            page.insert_text((86, y), FIRST, fontsize=9, fontname="helv")
            page.insert_text((86, y + 11), SECOND, fontsize=9, fontname="helv")
            y += 30
        doc.save(path)


def lists_of(book_json):
    data = json.loads(Path(book_json).read_text("utf-8"))
    found = []

    def walk(units):
        for unit in units:
            if unit["type"] == "list" and any(
                (i.get("marker") or {}).get("type") == "decimal" for i in unit["items"]
            ):
                found.append(unit)
            for key in ("items", "children"):
                walk(unit.get(key) or [])

    walk(data["content"])
    return found


def test_flush_right_numbers_across_nine_and_ten_are_one_list(tmp_path):
    bibliography(tmp_path / "b.pdf")
    result = _run(tmp_path / "b.pdf", tmp_path / "out", tmp_path / "cache", 1)
    book = json.loads((Path(result["book_json"]) / "book.json").read_text("utf-8"))
    summary = [u["type"] for u in book["content"]]
    found = lists_of(Path(result["book_json"]) / "book.json")
    values = [i["marker"]["value"] for node in found for i in node["items"]]
    assert values == list(range(7, 15)), summary
    lengths = [len(n["items"]) for n in found]
    assert len(found) == 1, lengths
