"""Load a published book folder (book.json, manifest.json, images/) read-only, check it
against the Stage 1 JSON Schema and the manifest, and index every text record."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema


class BookLoadError(ValueError):
    pass


@dataclass
class LoadedBook:
    folder: Path
    data: dict[str, Any]
    sha256: str
    records: dict[str, dict] = field(default_factory=dict)  # addr -> TextContent
    order: dict[str, int] = field(default_factory=dict)  # addr -> reading-order index
    units: dict[str, dict] = field(default_factory=dict)  # unit id -> unit
    markers: set[str] = field(default_factory=set)  # addrs of list-marker records

    @property
    def pages(self) -> list[dict]:
        return self.data["pages"]

    def image_path(self, file: str) -> Path:
        return self.folder / "images" / file


def book_schema() -> dict:
    ref = resources.files("book_core.assembly") / "book.schema.json"
    return json.loads(ref.read_text("utf-8"))


def load_book(folder: Path | str, check_manifest: bool = True) -> LoadedBook:
    folder = Path(folder)
    path = folder / "book.json" if folder.is_dir() else folder
    folder = path.parent
    raw = path.read_bytes()
    data = json.loads(raw)
    errors = sorted(
        jsonschema.Draft202012Validator(book_schema()).iter_errors(data),
        key=lambda e: list(map(str, e.path)),
    )
    if errors:
        first = errors[0]
        raise BookLoadError(
            f"{path.name} does not match the universal-book schema "
            f"({len(errors)} errors); first at "
            f"{'/'.join(map(str, first.path))}: {first.message}"
        )
    manifest = folder / "manifest.json"
    if check_manifest and manifest.exists():
        files = json.loads(manifest.read_text("utf-8")).get("files", {})
        items = files.items() if isinstance(files, dict) else [(f["path"], f) for f in files]
        for rel, entry in items:
            if rel.startswith("review/"):
                continue
            sha = entry["sha256"] if isinstance(entry, dict) else entry
            target = folder / rel
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                raise BookLoadError(f"{rel} is missing or does not match manifest.json")
    book = LoadedBook(folder, data, hashlib.sha256(raw).hexdigest())
    index_records(book)
    return book


def index_records(book: LoadedBook) -> None:
    """Every text record of the content tree in reading order, with a stable address."""
    counter = [0]

    def add(addr: str, content: dict, marker: bool = False):
        book.records[addr] = content
        book.order[addr] = counter[0]
        counter[0] += 1
        if marker:
            book.markers.add(addr)

    def walk(unit: dict):
        uid = unit.get("id")
        if uid:
            book.units[uid] = unit
        kind = unit.get("type")
        marker = unit.get("marker")
        if marker and marker.get("text"):
            add(f"{uid}#marker", {"text": marker["text"], "joins": [], "spans": []}, True)
        if kind == "table":
            if unit.get("title"):
                add(f"{uid}/title", unit["title"]["content"])
            for cell in unit.get("cells") or ():
                for k, item in enumerate(cell.get("content") or ()):
                    if item.get("type") == "text":
                        add(f"{uid}/cell/{cell['id']}/{k}", item["content"])
                    else:
                        walk(item)
            for i, note in enumerate(unit.get("notes") or ()):
                add(f"{uid}/note/{i}", note["content"])
            return
        if kind == "figure":
            for key, name in (("captions", "caption"), ("text", "text"), ("credits", "credit")):
                for i, item in enumerate(unit.get(key) or ()):
                    add(f"{uid}/{name}/{i}", item["content"])
            return
        content = unit.get("content")
        if isinstance(content, dict) and "text" in content:
            add(uid, content)
        for key in ("items", "children"):
            for child in unit.get(key) or ():
                walk(child)

    for unit in book.data.get("content") or ():
        walk(unit)
