"""BITS writer."""

from __future__ import annotations

from ..formats import bits as b
from .jats_writer import JatsWriter


class BitsWriter(JatsWriter):
    name = "bits"
    root_pattern = "{isbn}_bits"
    root_tag = "book"
    public_id = b.PUBLIC_ID
    system_id = b.SYSTEM_ID
    dtd_version = "2.2"

    def make(self):
        cfg = dict(self.cfg)
        cfg.setdefault("mode", "single")
        cfg["files"] = {
            "article": self.cfg["files"]["book"],
            "per_article": self.cfg["files"]["book"],
        }
        self.cfg = cfg
        conv = b.BitsConverter(self.src, cfg)
        return conv, conv.build()
