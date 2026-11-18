"""The one-click fix of the review item "Hyphen followed by a space — remove the space?":
``remove_char`` takes out the one space after a hyphen between two letters and moves the spans
and line-end join records behind it; nothing else changes, and a place that is no longer a
hyphen and a space is refused."""

from __future__ import annotations

import json

import pytest

from book_app import edit_ops, overlay
from book_app.decisions import EDIT_OPS
from tests_adapters.adapter_fixtures import BookBuilder

SOFT = "­"


def make(tmp_path, text, spans=(), joins=()):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    unit = b.para(p, text, spans=spans, joins=joins)
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    return data, unit["id"]


def remove(data, uid, offset):
    out, applied, failed = overlay.apply_edits(data, [{"id": "e1", "op": "remove_char", "unit": uid, "offset": offset}])
    return out, applied, failed


def content(data, uid):
    return overlay.index_units(data)[uid][0]["content"]


def test_the_space_after_a_hyphen_goes_and_spans_and_joins_follow(tmp_path):
    text = f"Disorders of acid- base balance and militar{SOFT}\nily ok"
    bold = {"kind": "bold", "start": 0, "end": len("Disorders of acid- base")}  # runs across the space
    italic = {"kind": "italic", "start": text.index("balance"), "end": text.index("balance") + 7}
    join = {"at": text.index("\n"), "decision": "soft_join", "hyphen_at": text.index(SOFT), "confidence": 0.9}
    data, uid = make(tmp_path, text, spans=[bold, italic], joins=[join])
    out, applied, failed = remove(data, uid, text.index("- base") + 1)
    assert not failed and applied
    c = content(out, uid)
    assert c["text"] == f"Disorders of acid-base balance and militar{SOFT}\nily ok"
    assert [(s["kind"], c["text"][s["start"] : s["end"]]) for s in c["spans"]] == [
        ("bold", "Disorders of acid-base"), ("italic", "balance")]  # the bold span is one span again
    assert c["joins"][0]["at"] == c["text"].index("\n") and c["joins"][0]["hyphen_at"] == c["text"].index(SOFT)
    assert not overlay.schema_errors(out)
    assert edit_ops.touched(applied[0]) == [uid] and "remove_char" in EDIT_OPS
    assert content(data, uid)["text"] == text  # the base book is untouched


@pytest.mark.parametrize("offset", [0, 3, 5])
def test_only_a_space_after_a_hyphen_between_letters_is_refused_elsewhere(tmp_path, offset):
    data, uid = make(tmp_path, "an acid- base mix - x")
    _, applied, failed = remove(data, uid, offset)
    assert failed and not applied and "no longer after a hyphen" in failed[0]["reason"]


def test_a_dash_between_words_and_a_second_run_are_refused(tmp_path):
    data, uid = make(tmp_path, "one - two")  # a spaced dash: no letter before the hyphen
    assert remove(data, uid, 5)[2]  # the space is there, but no letter stands before the hyphen
    data, uid = make(tmp_path, "pre- and post-")  # the space is there, but the text after is checked by the card, not here
    out, _, failed = remove(data, uid, 4)
    assert not failed and content(out, uid)["text"] == "pre-and post-"  # the review item skips these; the op follows the person
