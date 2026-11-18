"""Page turns inside a reference list and number ranges broken at a line end.

A page marker that opens a reference stands between the references (a paragraph holding the
target), not inside the reference text; the ids stay unique. A dash between two numbers at a
line end ("2918–" "2928") keeps the dash and loses the line end: no space inside the range."""

from __future__ import annotations

import re

from book_adapters.engine import joins
from book_adapters.engine.formats_run import run_format

from .adapter_fixtures import BookBuilder


def read(text):
    records = [{"text": text, "joins": [], "spans": []}]
    joins.infer_joins(records)
    return records[0]


def test_a_line_end_after_a_dash_between_numbers_keeps_the_dash_and_no_space():
    c = read("J. Phys. Chem. B 103, pp. 2918–\n2928. Next.")
    assert [(j["decision"], j["hyphen_at"]) for j in c["joins"]] == [("keep", None)]
    assert read("pp. 94-\n96")["joins"][0]["decision"] == "keep"
    # a dash between words, or a number then words, is not a range: no record is invented
    assert read("well–\nknown fact")["joins"] == []
    assert read("in 1999–\nthen came")["joins"] == []
    assert read("a number 12–\nA")["joins"] == []


def test_bits_writes_the_range_whole_and_the_page_marker_between_references(tmp_path, store, settings_file):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p1 = b.page("1", "body", s)
    b.heading(p1, "Chapter title", 1, "chapter")
    b.para(p1, "Words of the chapter alpha beta.")
    b.heading(p1, "REFERENCES", 2, "section")
    p2 = b.page("2", "body", s)
    items = [b.item(p1, "Smith, J. A paper. (2020) Nature 1, pp. 10\u2013\n20.",
                    marker={"text": "1.", "type": "decimal", "value": 1, "punctuation": "period"},
                    kind="bibliography_entry"),
             b.item(p2, "Jones, K. Another paper. (2021) Science 2, pp. 5\u20139.",
                    marker={"text": "2.", "type": "decimal", "value": 2, "punctuation": "period"},
                    kind="bibliography_entry")]  # fmt: skip
    b.list(p1, items, list_type="bibliography", marker_type="decimal")
    book = b.finish(tmp_path / "book")
    report = run_format("bits", book, tmp_path / "out", settings_file, "bits_base", store,
                        allow_alt_text_placeholders=True)  # fmt: skip
    data = next((tmp_path / "out").rglob("*.xml")).read_text("utf-8")
    text = " ".join(re.sub(r"<[^>]+>", " ", data).split())
    assert "pp. 10\u201320" in text.replace(" \u2013 ", "\u2013") or "10\u201320" in data
    assert "10\u2013 20" not in data and "10\u2013\n20" not in data
    refs = re.findall(r"<ref[ >].*?</ref>", data, re.S)
    assert len(refs) == 2 and not any("page-break" in r for r in refs), refs
    # the page turn is a paragraph with the target in the reference list, outside every reference
    assert re.search(r'<p><target id="page2" target-type="page-break"/></p>', data)
    ids = re.findall(r' id="([^"]+)"', data)
    assert len(ids) == len(set(ids))
    checks = report["checks"]
    assert checks["dtd"]["errors"] == 0
    loss = checks["lossless"]
    assert (loss["missing"], loss["extra"]) == (0, 0)
