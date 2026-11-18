"""The review item "Hyphen followed by a space — remove the space?".

A hyphen and a space inside a text ("acid- base") is in the PDF's own text layer, so it is never
rewritten automatically: the export keeps it, and each place is a review item with the offset of
the space (the app's one-click fix removes it). The profile setting ``characters.hyphen_space``
turns the items off."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from book_adapters import qc
from book_adapters.engine.load import load_book

from .test_adapter_b import assert_lossless, base_book, export


def build(tmp_path, *paragraphs):
    b, pages = base_book()
    for text in paragraphs:
        b.para(pages[0], text)
    return b.finish(tmp_path / "book")


def items(tmp_path):
    return [i for i in json.loads((tmp_path / "out/report/review_list.json").read_text()) if i.get("rule") == "hyphen_space"]


def test_a_hyphen_and_a_space_is_a_review_item_never_a_rewrite(tmp_path, store):
    one = "Disorders of acid- base balance are common."
    book = build(tmp_path, one, "The acid-base balance is kept.", "pre- and post-operative care", "a well-known fact")
    report, _, xml = export(book, tmp_path, store)
    found = items(tmp_path)
    assert len(found) == 1  # "pre- and post-operative" is a suspended hyphen: no item
    reason = found[0]["reason"]
    assert reason.startswith("Hyphen followed by a space at offset") and "“acid- base”" in reason
    assert "written “acid-base” elsewhere in the book" in reason and found[0]["kind"] == "character"
    offset = int(re.search(r"offset (\d+)", reason).group(1))
    assert one[offset] == " " and one[offset - 1] == "-"  # the offset is the space itself
    text = " ".join("".join(xml.itertext()).split())
    assert "acid- base" in text and "pre- and post-operative" in text  # nothing rewritten
    assert_lossless(report)


def test_the_profile_switch_and_the_skip_words(tmp_path):
    book = load_book(build(tmp_path, "A non- judgmental tone.", "Two- or three-day stay."))

    def profile(**settings):
        return SimpleNamespace(get=lambda key, default=None: settings.get(key, default))

    only = qc.hyphen_space_items(book, profile())
    assert len(only) == 1 and "“non- judgmental”" in only[0]["reason"]  # "Two- or" is a suspended hyphen
    assert qc.hyphen_space_items(book, profile(**{"characters.hyphen_space": "off"})) == []
    # the skip list is the profile's: with "or" removed from it, "Two- or" is offered too
    more = qc.hyphen_space_items(book, profile(**{"characters.hyphen_space_skip_before": ["and", "to", "nor"]}))
    assert len(more) == 2
