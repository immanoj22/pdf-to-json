"""BITS checks on the written file, re-read from disk: the BITS 2.2 DTD (ids unique, rid
resolve), graphics with alt-text, page-break targets complete and in order with their labels in
the book metadata, titles, and the lossless check."""

from __future__ import annotations

from . import jats_checks as jc


def check(root_dir, delivery, doc, book, profile, cfg) -> dict:
    result = jc.run(root_dir, delivery, doc, book, profile, cfg, ["bits2_2"])
    result["dtd"]["dtd"] = "BITS 2.2 + JATS 1.4 modules + MathML 3 (pinned, offline)"
    return result
