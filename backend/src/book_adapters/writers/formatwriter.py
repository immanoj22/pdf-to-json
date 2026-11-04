"""Base of the standard format writers (DTBook/NIMAS, DAISY 3, JATS, BITS).

``write`` runs the shared content pass (:class:`SemanticWriter`), hands the tree to the
format's transformer and fills the delivery. Everything format-specific comes from the
profile's section of the same name."""

from __future__ import annotations

from ..engine.format_profile import format_section, has_section
from ..engine.model import Document
from .base import Delivery, WriteContext
from .semantic import SemanticWriter


class FormatWriter:
    name = ""  # profile section and format name
    root_pattern = "{isbn}_{name}"

    def write(self, doc: Document, ctx: WriteContext) -> Delivery:
        from ..formats.source import Source

        sem = SemanticWriter()
        delivery = sem.write(doc, ctx)
        self.cfg = format_section(ctx.profile, self.name)
        self.cfg["images_folder"] = ctx.profile.get("delivery.images_folder") or "images"
        self.has_section = has_section(ctx.profile, self.name)
        self.ctx = ctx
        self.src = Source(sem, doc, ctx, delivery)
        self.isbn = sem.isbn
        delivery.root = self.root_pattern.format(isbn=self.isbn, name=self.name)
        delivery.generated_files = set()
        delivery.spine = []
        self.build(delivery)
        delivery.images = sem.images
        return delivery

    def build(self, delivery: Delivery) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def to_supply(self, what: str, why: str):
        from ..engine.model import ReviewEntry

        self.src.reviews.append(
            ReviewEntry("settings", f"{what} to supply: {why}", severity="must_check")
        )
