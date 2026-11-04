"""A small synthetic universal-book publication (schema-valid) for adapter tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
PROFILES = ROOT / "profiles"
SHA = "0" * 64


class BookBuilder:
    def __init__(self):
        self.units: list[dict] = []
        self.pages: list[dict] = []
        self.sections: list[dict] = []
        self.toc: list[dict] = []
        self.n = 0
        self.order = 0
        self.images: dict[str, tuple[int, int]] = {}
        self.review_items: list[dict] = []
        self.crops: dict[str, tuple[int, int]] = {}

    def uid(self) -> str:
        self.n += 1
        return f"{self.n:016x}"

    def base(self, unit_type: str, on_page: int, **extra) -> dict:
        self.order += 1
        unit = {
            "id": self.uid(),
            "type": unit_type,
            "pages": [on_page],
            "order": self.order,
            "provenance": {"stages": ["test"]},
        }
        unit.update(extra)
        return unit

    @staticmethod
    def content(text: str, spans=(), joins=()) -> dict:
        return {"text": text, "spans": list(spans), "joins": list(joins)}

    def page(self, label: str | None, zone: str, section: str) -> int:
        index = len(self.pages) + 1
        self.pages.append(
            {
                "index": index,
                "label": label,
                "label_source": "printed",
                "width": 500.0,
                "height": 700.0,
                "zone": zone,
                "section": section,
            }
        )
        self.units.append(self.base("page_marker", index, page=index, label=label))
        return index

    def section(self, kind: str, zone: str) -> str:
        sid = self.uid()
        self.sections.append(
            {"id": sid, "kind": kind, "zone": zone, "first_page": 0, "last_page": 0}
        )
        return sid

    def para(self, page, text, role="body", spans=(), joins=(), **extra):
        unit = self.base(
            "paragraph", page, role=role, content=self.content(text, spans, joins), **extra
        )
        self.units.append(unit)
        return unit

    def heading(self, page, text, level, role):
        unit = self.base(
            "heading", page, level=level, role=role, level_method="test", content=self.content(text)
        )
        self.units.append(unit)
        return unit

    def item(self, page, text, marker=None, kind="list_item", **extra):
        unit = self.base(kind, page, content=self.content(text), **extra)
        if marker:
            unit["marker"] = marker
        return unit

    def list(self, page, items, list_type="bulleted", marker_type=None, add=True):
        unit = self.base(
            "list",
            page,
            list_id=self.uid(),
            segment=0,
            list_type=list_type,
            marker_type=marker_type,
            items=items,
        )
        if add:
            self.units.append(unit)
        return unit

    def figure(self, page, label, name, captions=(), texts=(), small=False, size=(40, 30)):
        file = f"{name}.png"
        self.images[file] = size
        unit = self.base(
            "figure",
            page,
            kind="drawing",
            name=name,
            label=label,
            small=small,
            image={
                "file": file,
                "format": "png",
                "width": size[0],
                "height": size[1],
                "dpi": 300,
                "sha256": SHA,
                "bytes": 1,
            },
            captions=[{"id": self.uid(), "refs": {}, "content": self.content(c)} for c in captions],
            text=[{"id": self.uid(), "refs": {}, "content": self.content(t)} for t in texts],
        )
        self.units.append(unit)
        return unit

    def finish(self, folder: Path) -> Path:
        for s in self.sections:
            pages = [p["index"] for p in self.pages if p["section"] == s["id"]]
            s["first_page"], s["last_page"] = min(pages), max(pages)
        book = {
            "schema": {"name": "universal-book", "version": "1.1.0"},
            "metadata": {
                "title": "A Test Book",
                "source": {"sha256": SHA, "pages": len(self.pages)},
                "converter": {"name": "test", "version": "0", "producer": SHA},
                "profile": {"id": "default", "version": "1", "sha256": SHA},
                "settings_sha256": SHA,
                "content_sha256": SHA,
                "languages": [],
            },
            "pages": self.pages,
            "content": self.units,
            "navigation": {
                "toc": self.toc,
                "outline": [],
                "sections": self.sections,
                "page_list": [],
            },
            "assets": [],
        }
        if self.review_items:
            book["review"] = {"counts": {}, "items": self.review_items}
        folder.mkdir(parents=True, exist_ok=True)
        for file, size in sorted(self.crops.items()):
            (folder / file).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", size, (200, 200, 200)).save(folder / file)
        (folder / "book.json").write_text(json.dumps(book, indent=1), "utf-8")
        (folder / "images").mkdir(exist_ok=True)
        for i, (file, size) in enumerate(sorted(self.images.items())):
            Image.new("RGB", size, (20 * i % 255, 120, 200)).save(folder / "images" / file)
        return folder


def build_sample(folder: Path) -> Path:
    b = BookBuilder()
    cover = b.section("cover", "front")
    title = b.section("title_page", "front")
    copyright_ = b.section("copyright", "front")
    preface = b.section("preface", "front")
    toc = b.section("table_of_contents", "front")
    body = b.section("chapter", "body")
    index = b.section("index", "rear")

    p = b.page("i", "front", cover)
    b.para(p, "Cover words")
    p = b.page("ii", "front", title)
    b.heading(p, "A Test Book", 1, "book_title")
    b.para(p, "Ann Author")
    p = b.page("iii", "front", copyright_)
    b.para(p, "ISBN: 978-0-306-40615-7")
    b.para(p, "First Edition: 2026")
    b.para(p, "Smith & Sons <publisher> said 'hello'.")
    p = b.page("iv", "front", preface)
    b.heading(p, "Preface", 1, "front_section_title")
    b.para(p, "The world’s first preface paragraph.")
    b.para(p, "A second preface paragraph.")
    p = b.page("v", "front", toc)
    toc_list = b.list(
        p, [b.item(p, "1.\tThe First Chapter......3", kind="contents_entry")], list_type="contents"
    )
    _ = toc_list

    p1 = b.page("1", "body", body)
    b.figure(p1, "1", "page_1_1", texts=["Foundations of Testing", "PART"])
    b.list(
        p1,
        [
            b.item(
                p1,
                "The First Chapter",
                marker={"text": "1.", "type": "decimal", "value": 1, "punctuation": "period"},
            )
        ],
        list_type="numbered",
        marker_type="decimal",
    )
    p2 = b.page("2", "body", body)
    b.heading(p2, "The First Chapter", 1, "chapter")
    b.heading(p2, "INTRODUCTION", 2, "section")
    text = (
        "Temperatures fall to –10°C between 2010–2020, as shown in Fig. 1 "
        "and Table 1.1 The interven-\ntion"
    )
    cite = text.index("1.1 ") + 2
    first = b.para(
        p2,
        text,
        spans=[
            {"kind": "superscript", "start": cite, "end": cite + 1},
            {"kind": "bold", "start": 0, "end": 12},
        ],
        joins=[
            {
                "at": text.index("\n"),
                "decision": "join",
                "hyphen_at": text.index("\n") - 1,
                "confidence": 0.9,
            }
        ],
    )
    b.figure(p2, "2", "page_2_1", captions=["Fig. 1: A labelled drawing."])
    p3 = b.page("3", "body", body)
    second = b.para(p3, "continues on the next page.")
    first["continues_to"] = {"unit": second["id"], "kind": "page", "confidence": 0.9}
    second["continues_from"] = {"unit": first["id"], "kind": "page", "confidence": 0.9}
    b.heading(p3, "Details", 3, "subsection")
    side = b.base(
        "box",
        p3,
        box_kind="callout",
        children=[
            b.base(
                "heading",
                p3,
                level=1,
                role="sidebar_title",
                level_method="t",
                content=b.content("Box 1: Key points"),
            ),
            b.base("paragraph", p3, role="body", content=b.content("Inside the box.")),
        ],
    )
    item_with_box = b.item(
        p3, "First point", marker={"text": "■", "type": "bullet"}, children=[side]
    )
    b.list(p3, [item_with_box, b.item(p3, "Second point", marker={"text": "■", "type": "bullet"})])
    cells = []
    for r, row in enumerate([["Name", "Value"], ["Alpha", ""]]):
        for c, text in enumerate(row):
            cells.append(
                {
                    "id": b.uid(),
                    "row": r,
                    "column": c,
                    "role": "column_header" if r == 0 else "data",
                    "box": {"page": p3, "x0": 0, "y0": 0, "x1": 1, "y1": 1},
                    "content": [{"type": "text", "refs": {}, "content": b.content(text)}]
                    if text
                    else [],
                }
            )
    b.units.append(
        b.base(
            "table",
            p3,
            rows=2,
            columns=2,
            header_rows=1,
            cells=cells,
            title={
                "id": b.uid(),
                "role": "title",
                "numbered": True,
                "number": "1",
                "refs": {},
                "content": b.content("Table 1: Values."),
            },
        )
    )
    b.heading(p3, "REFERENCES", 2, "section")
    b.list(
        p3,
        [
            b.item(
                p3,
                "Smith J. A paper. 2020;1:1–5.",
                marker={"text": "1.", "type": "decimal", "value": 1, "punctuation": "period"},
                kind="bibliography_entry",
            )
        ],
        list_type="bibliography",
        marker_type="decimal",
    )
    pi = b.page("4", "rear", index)
    b.heading(pi, "Index", 1, "rear_section_title")
    b.units.append(b.base("index_divider", pi, content=b.content("A")))
    entry_text = "Alpha 2f, 3-4"
    b.list(
        pi,
        [
            b.item(
                pi,
                entry_text,
                kind="index_entry",
                level=1,
                locators=[
                    {
                        "kind": "page",
                        "start": 6,
                        "end": 7,
                        "label": "2",
                        "target_page": p2,
                        "confidence": 0.9,
                    },
                    {
                        "kind": "range",
                        "start": 10,
                        "end": 13,
                        "label": "3",
                        "end_label": "4",
                        "target_page": p3,
                        "end_target_page": pi,
                        "confidence": 0.9,
                    },
                ],
            ),
            b.item(
                pi,
                "beta 3",
                kind="index_entry",
                level=2,
                locators=[
                    {
                        "kind": "page",
                        "start": 5,
                        "end": 6,
                        "label": "3",
                        "target_page": p3,
                        "confidence": 0.9,
                    }
                ],
            ),
        ],
        list_type="index",
    )
    b.toc.append(
        {"entry": None, "target_page": p2, "target_label": "2", "level": 1, "confidence": 0.97}
    )
    return b.finish(folder)


def sha_tree(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(folder)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()
