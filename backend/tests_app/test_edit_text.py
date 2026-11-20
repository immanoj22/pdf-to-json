"""``edit_text``: the typed text replaces one block's text (a reference with a missing character);
its spans and line-end records go, the block says who corrected it, an empty text is refused."""

from __future__ import annotations

import json

from book_app import edit_ops, overlay
from book_app.decisions import EDIT_OPS
from tests_adapters.adapter_fixtures import BookBuilder


def make(tmp_path, text, spans=(), joins=()):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    unit = b.para(p, text, spans=spans, joins=joins)
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    return data, unit["id"]


def run(data, uid, text, who="Asha"):
    return overlay.apply_edits(data, [{"id": "e1", "op": "edit_text", "unit": uid, "text": text, "who": who}])


def test_the_text_is_replaced_and_the_block_says_who_corrected_it(tmp_path):
    text = "[4]\nHarlan JR. Crops and man Agron J 1992; 5(1): 10-5."
    join = {"at": text.index("\n"), "decision": "keep", "hyphen_at": None, "confidence": 0.9}
    data, uid = make(tmp_path, text, spans=[{"kind": "italic", "start": 4, "end": 10}], joins=[join])
    out, applied, failed = run(data, uid, "[4]\n  Harlan JR. Crops and man.   Agron J 1992; 5(1): 10-5.\n\n")
    assert not failed and applied and "edit_text" in EDIT_OPS and edit_ops.touched(applied[0]) == [uid]
    unit = overlay.index_units(out)[uid][0]
    assert unit["content"]["text"] == "[4]\nHarlan JR. Crops and man. Agron J 1992; 5(1): 10-5."
    assert unit["content"]["spans"] == [] and unit["content"]["joins"] == []
    assert "text corrected by Asha" in unit["provenance"]["reasons"]
    assert not overlay.schema_errors(out)


def test_an_empty_text_is_refused(tmp_path):
    data, uid = make(tmp_path, "Some text.")
    out, applied, failed = run(data, uid, "  \n ")
    assert failed and not applied and "Type the text" in failed[0]["reason"]
