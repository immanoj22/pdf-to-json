"""Quotes are never dropped by BITS and JATS: a quotation is a ``disp-quote``, a pull quote a
``disp-quote`` with specific-use="pull"; an element without a mapping keeps its text in a
paragraph (and is on the review list)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from lxml import etree

from book_app import overlay

from .test_adapter_b import base_book
from .test_formats import make


def quote_book(tmp_path):
    b, pages = base_book()
    plain = b.para(pages[0], "Ordinary text before the quotes.")
    quote = b.para(pages[0], "A quotation worth keeping in the book.")
    pull = b.para(pages[0], "A pull quote repeated from the text.")
    b.para(pages[0], "Ordinary text after the quotes.")
    src = b.finish(tmp_path / "book")
    data = json.loads((src / "book.json").read_text())
    out, _, failed = overlay.apply_edits(data, [
        {"id": "e1", "op": "box", "units": [quote["id"]], "kind": "quote"},
        {"id": "e2", "op": "box", "units": [pull["id"]], "kind": "pull_quote"}])  # fmt: skip
    assert not failed, failed
    dst = tmp_path / "edited"
    shutil.copytree(src, dst)
    (dst / "book.json").write_text(json.dumps(out))
    return dst


@pytest.mark.parametrize("fmt", ["bits", "jats"])
def test_quotes_are_disp_quotes_and_nothing_is_lost(fmt, tmp_path, store, settings_file):
    report = make(fmt, quote_book(tmp_path), tmp_path, store, settings_file)
    loss = report["checks"]["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0), loss
    assert loss["output"]["matches_ledger"], loss["output"]
    assert report["checks"]["dtd"]["errors"] == 0, report["checks"]["dtd"]
    xml = next(p for p in Path(report["root"]).glob("*.xml"))
    root = etree.parse(str(xml)).getroot()
    quotes = root.xpath("//disp-quote")
    assert len(quotes) == 2
    assert sorted(q.get("specific-use") or "" for q in quotes) == ["", "pull"]
    assert {" ".join("".join(q.itertext()).split()) for q in quotes} == {
        "A quotation worth keeping in the book.", "A pull quote repeated from the text."}


def test_an_unmapped_element_keeps_its_text_and_is_reviewed():
    from book_adapters.formats.jatsbase import JatsBase

    conv = JatsBase.__new__(JatsBase)
    conv.reviews, conv.continued = [], 0
    parent = etree.Element("body")
    src = etree.fromstring("<mystery>kept <b>text</b> here</mystery>")
    conv.block(src, parent)
    assert [" ".join(p.text.split()) for p in parent.findall("p")] == ["kept text here"]
    assert any("no mapping" in r.message for r in conv.reviews)
