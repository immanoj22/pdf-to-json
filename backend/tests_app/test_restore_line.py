"""Restore a PDF line that the book keeps as page furniture ("Restore as…" in Browse).

The synthetic book checks the rules; ``test_real_pages`` repeats them on real pages of a
converted book. Set ``RESTORE_TEST_PUBLICATION`` to the folder holding its ``book.json`` (a copy
of a job's publication; skipped otherwise): the title lines of pages 86, 181 and 21 must come
back as the PDF's own text at the top of their page with the lossless count unchanged."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest
from book_app import edit_ops, overlay
from book_core.assembly import lossless


def _unit(uid, type_, text, page, box, **extra):
    return {
        "id": uid, "type": type_, "pages": [page], "order": 1, "boxes": [{"page": page, **box}],
        "refs": {"lines": [uid + "-line"], "spans": []}, "flags": [], "source": "native",
        "content": {"text": text, "spans": [], "joins": [], "source_runs": [], "raw": None},
        "provenance": {"stages": ["structure"]}, "review_status": "ok", "confidence": 0.9,
        "continues_from": None, "continues_to": None, **({"role": "body"} if type_ == "paragraph" else {}),
        **extra,
    }


def _furniture(fid, kind, text, page, box):
    return {"id": fid, "kind": kind, "page": page, "boxes": [{"page": page, **box}],
            "refs": {"lines": [fid + "-line"], "spans": []}, "confidence": 0.95, "flags": [],
            "content": {"text": text, "spans": [], "joins": [], "source_runs": [], "raw": None},
            "review_status": "ok"}  # fmt: skip


def book():
    col1 = {"x0": 57, "x1": 227, "y0": 460, "y1": 600}
    col2 = {"x0": 243, "x1": 413, "y0": 460, "y1": 600}
    return {
        "content": [
            {"id": "m1", "type": "page_marker", "page": 1, "pages": [1], "label": "1"},
            _unit("a", "paragraph", "Area: 27 sq. mi.", 1, col1),
            _unit("b", "paragraph", "Recognized language: Irish", 1, col2),
            {"id": "m2", "type": "page_marker", "page": 2, "pages": [2], "label": "2"},
            _unit("c", "paragraph", "Page two text", 2, col1),
        ],
        "furniture": [
            _furniture("t1", "running_head", "The Republic of Ireland", 1, {"x0": 58, "x1": 257, "y0": 54, "y1": 76}),
            _furniture("f1", "folio", "80", 1, {"x0": 322, "x1": 330, "y0": 775, "y1": 787}),
            _furniture("r1", "running_head", "Ireland", 2, {"x0": 58, "x1": 120, "y0": 54, "y1": 76}),
        ],
        "suppressed": [], "pages": [{"zone": "body"}, {"zone": "body"}], "navigation": {},
    }  # fmt: skip


def apply(data, **edit):
    out, applied, failed = overlay.apply_edits(copy.deepcopy(data), [{"id": "e1", "op": "restore_line", **edit}])
    return out, applied, failed


def kept(data):
    f = lossless.json_tokens(data)
    return f["content"] + f["furniture"] + f["suppressed_retained"]


def order(data):
    return [u["id"] for u, _ in overlay.walk(data["content"])]


def test_title_goes_back_at_the_top_of_its_page_as_the_pdf_text():
    data = book()
    out, applied, failed = apply(data, line="t1", **{"as": "chapter"})
    assert not failed and applied
    assert order(out) == ["m1", "t1", "a", "b", "m2", "c"]  # after its page marker, before the first block
    unit = next(u for u, _ in overlay.walk(out["content"]) if u["id"] == "t1")
    assert unit["type"] == "heading" and unit["role"] == "chapter" and unit["level"] == 1
    assert unit["content"] == data["furniture"][0]["content"]  # the PDF's own text, nothing typed
    assert unit["pages"] == [1] and unit["refs"] == data["furniture"][0]["refs"]
    assert [f["id"] for f in out["furniture"]] == ["f1", "r1"]  # it left the furniture
    assert kept(out) == kept(data)  # lossless: the tokens moved from furniture to content, none added


def test_each_kind_and_the_line_can_only_be_restored_once():
    data = book()
    para, _, bad = apply(data, line="t1", **{"as": "paragraph"})
    assert not bad
    p = next(u for u, _ in overlay.walk(para["content"]) if u["id"] == "t1")
    assert p["type"] == "paragraph" and p["role"] == "body"
    part, _, bad = apply(data, line="t1", **{"as": "part"})
    assert not bad and next(u for u, _ in overlay.walk(part["content"]) if u["id"] == "t1")["role"] == "part"
    head, _, bad = apply(data, line="t1", **{"as": "heading", "level": 3})
    h = next(u for u, _ in overlay.walk(head["content"]) if u["id"] == "t1")
    assert not bad and h["type"] == "heading" and h["level"] == 3 and h["role"] != "chapter"
    again, _, bad = overlay.apply_edits(
        para, [{"id": "e2", "op": "restore_line", "line": "t1", "as": "paragraph"}])
    assert bad and "no longer in the page furniture" in bad[0]["reason"]


def test_only_a_running_head_or_foot_can_be_restored():
    data = book()
    for line in ("f1", "nope"):
        _, applied, bad = apply(data, line=line, **{"as": "paragraph"})
        assert bad and not applied
    assert "page numbers" in apply(data, line="f1", **{"as": "paragraph"})[2][0]["reason"]
    assert apply(data, line="t1", **{"as": "title"})[2]  # not one of the four kinds
    assert apply(data, line="t1", **{"as": "heading", "level": 12})[2]


def test_a_line_in_a_column_goes_after_the_block_above_it():
    data = book()
    data["furniture"].append(_furniture("m", "running_head", "Mid-column line", 1,
                                        {"x0": 243, "x1": 400, "y0": 610, "y1": 620}))  # under column 2
    out, _, bad = apply(data, line="m", **{"as": "paragraph"})
    assert not bad and order(out) == ["m1", "a", "b", "m", "m2", "c"]


def test_restore_is_undone_by_dropping_the_edit_and_stays_in_the_audit_shape():
    data = book()
    out, applied, _ = apply(data, line="t1", **{"as": "chapter"})
    assert edit_ops.touched(applied[0]) == ["t1"]  # the row to redraw is the line's own
    back, _, _ = overlay.apply_edits(copy.deepcopy(data), [])  # without the edit: as it was
    assert [f["id"] for f in back["furniture"]] == ["t1", "f1", "r1"] and kept(back) == kept(data)


@pytest.mark.skipif(not os.environ.get("RESTORE_TEST_PUBLICATION"), reason="needs a copy of a converted book")
@pytest.mark.parametrize("page", [86, 181, 21])
def test_real_pages(page):
    data = json.loads((Path(os.environ["RESTORE_TEST_PUBLICATION"]) / "book.json").read_text("utf-8"))
    item = next(f for f in data["furniture"] if f["page"] == page and f["kind"] == "running_head")
    before_order = order(data)
    out, applied, failed = apply(data, line=item["id"], **{"as": "chapter"})
    assert applied and not failed
    assert kept(out) == kept(data)  # lossless counts it once, as content now
    assert not [f for f in out["furniture"] if f["id"] == item["id"]]
    after = order(out)
    assert item["id"] in after and len(after) == len(before_order) + 1
    on_page = [u for u, _ in overlay.walk(out["content"]) if page in (u.get("pages") or []) and u["type"] != "page_marker"]
    assert on_page[0]["id"] == item["id"]  # the title opens its page
    assert overlay.schema_errors(out) == []
