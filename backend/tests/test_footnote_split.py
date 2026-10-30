"""Notes set one after another at the page foot are separate notes, matched by their marks.

Step 18: four genuine notes on one page were read as one paragraph. A note line that opens
with a mark the text raises as a reference (``word¹`` ↔ ``1``), or a raised mark, starts a
new note.
"""

import json
from pathlib import Path

import pymupdf
from test_continuity import _run

BODY = (
    "The committee met in the spring and reviewed the evidence on hearing loss in children "
    "before it wrote the recommendations that the schools adopted in the following year "
)


def notes_book(path):
    with pymupdf.open() as doc:
        for number in (1, 2):
            page = doc.new_page(width=420, height=600)
            y, words, mark = 60, BODY.split(), 1
            for k in range(26):
                text = " ".join(words[(k * 5) % 20 :][:9])
                page.insert_text((50, y), text, fontsize=10, fontname="tiro")
                if k in (3, 9, 15):
                    end = 50 + pymupdf.get_text_length(text, "tiro", 10)
                    page.insert_text((end + 0.5, y - 4), str(mark), fontsize=6, fontname="tiro")
                    mark += 1
                y += 13
            page.draw_line((50, y), (150, y), width=0.5)
            notes = [
                (
                    "1",
                    [
                        "Smith J. Hearing in school children. J Audiol 2001;12:4-9;",
                        "see also the later survey of the same schools.",
                    ],
                ),
                ("2", ["Jones K. Classroom acoustics. Acoust Rev 2003;7:22-30."]),
                ("3", ["Brown L. Screening programmes. Child Health 2005;3:1-8."]),
            ]
            y += 12
            for mark, lines in notes:
                for index, text in enumerate(lines):
                    lead = f"{mark} " if index == 0 else ""
                    page.insert_text((50, y), lead + text, fontsize=8, fontname="tiro")
                    y += 10
            page.insert_text((205, 585), str(number + 10), fontsize=8, fontname="tiro")
        doc.save(path)
    return path


def test_consecutive_notes_are_separate_notes(tmp_path):
    result = _run(notes_book(tmp_path / "notes.pdf"), tmp_path / "out", tmp_path / "cache", 1)
    data = json.loads((Path(result["book_json"]) / "book.json").read_text("utf-8"))
    found = []

    def walk(node):
        if node.get("type") == "footnote":
            found.append(node["content"]["text"][:12])
        children = [c for key in ("content", "children", "items") if isinstance(node.get(key), list)
                    for c in node[key]]  # fmt: skip
        for child in children:
            walk(child)

    for top in data["content"]:
        walk(top)
    assert found == ["1 Smith J. H", "2 Jones K. C", "3 Brown L. S"] * 2
