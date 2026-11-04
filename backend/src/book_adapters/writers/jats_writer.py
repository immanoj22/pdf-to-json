"""JATS writer: the book as one article, or one article per division."""

from __future__ import annotations

from ..formats import jats as j
from ..formats.jatsbase import MML, PREFIXES, XLINK
from ..formats.markup import serialize
from .base import Delivery
from .formatwriter import FormatWriter


class JatsWriter(FormatWriter):
    name = "jats"
    root_pattern = "{isbn}_jats"
    root_tag = "article"
    public_id = j.PUBLIC_ID
    system_id = j.SYSTEM_ID
    dtd_version = "1.4"

    def make(self):
        conv = j.JatsConverter(self.src, self.cfg)
        return conv, conv.build()

    def build(self, delivery: Delivery) -> None:
        conv, articles = self.make()
        cfg, isbn = self.cfg, self.isbn
        lang = self.src.language(cfg["metadata"]["language"])
        multi = len(articles) > 1
        for key, root in articles:
            name = (
                cfg["files"]["per_article"].format(isbn=isbn, key=key)
                if multi
                else cfg["files"]["article"].format(isbn=isbn)
            )
            delivery.files[name] = self.document(root, lang)
            delivery.split_files[name] = self.root_tag
            delivery.spine.append(name)
        delivery.main_file = delivery.spine[0]
        delivery.page_labels = len(conv.page_list)
        delivery.notes = conv.notes
        delivery.continued_secs = conv.continued
        if conv.continued:
            self.src.reviews.append(
                __import__("book_adapters.engine.model", fromlist=["ReviewEntry"]).ReviewEntry(
                    "structure",
                    f"{conv.continued} continuation section(s) written: text that follows a "
                    "subsection in the source cannot stay in the parent section "
                    "(JATS content model)",
                )
            )

    def document(self, root, lang: str) -> bytes:
        from ..formats.jatsbase import BLOCK

        text = serialize(root, BLOCK, prefixes=PREFIXES, declared=frozenset({XLINK, MML}))
        ns = (
            f' xmlns:xlink="{XLINK}" xmlns:mml="{MML}" dtd-version="{self.dtd_version}"'
            f' xml:lang="{lang}"'
        )
        text = text.replace(f"<{self.root_tag}", f"<{self.root_tag}{ns}", 1)
        head = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE {self.root_tag} PUBLIC "{self.public_id}" "{self.system_id}">\n'
        )
        return (head + text + "\n").encode("utf-8")
