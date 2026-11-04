"""The writer interface. A writer turns the adapter document tree into delivery files; it
knows its output format but no client: every client choice comes from the profile."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..engine.ledger import Ledger
from ..engine.model import Document, ReviewEntry


@dataclass
class ImageJob:
    """One image file to write: source image, output name, size limit, and whether a
    full-size copy goes to the big-images folder."""

    source: str  # file name in the book's images/ folder
    name: str  # output file name
    big: bool
    page: int
    unit: str


@dataclass
class Delivery:
    root: str  # delivery folder name
    files: dict[str, bytes] = field(default_factory=dict)  # path in root -> bytes
    images: list[ImageJob] = field(default_factory=list)
    ledger: Ledger = field(default_factory=Ledger)
    reviews: list[ReviewEntry] = field(default_factory=list)
    main_file: str = ""
    split_files: dict[str, str] = field(default_factory=dict)  # path -> role (chapter id...)
    divisions: list[dict] = field(default_factory=list)  # chapter page ranges etc.
    anchors: dict[int, str] = field(default_factory=dict)  # physical page -> anchor id
    alt_placeholders: list[str] = field(default_factory=list)  # units with no alt text
    generated_files: set[str] = field(default_factory=set)  # ePub pages not made of book text
    spine: list[str] = field(default_factory=list)  # ePub pages in reading order
    nav_path: str = ""  # ePub navigation document


@dataclass
class WriteContext:
    profile: object
    settings: object
    rules_on: set[str]
    book: object  # LoadedBook
    options: dict = field(default_factory=dict)  # per-run values (the ePub's modified time)


class Writer(Protocol):
    name: str

    def write(self, doc: Document, ctx: WriteContext) -> Delivery: ...
