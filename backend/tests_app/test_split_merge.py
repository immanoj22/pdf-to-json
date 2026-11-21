"""Split here (a block becomes two at a word the reviewer clicks) and merge (blocks across a page
break become one paragraph): every letter and digit stays, the book stays valid, and the two
changes undo each other."""

import json

import pytest

from book_app import edit_ops, overlay
from tests_adapters.adapter_fixtures import BookBuilder

from .test_edit_ops import apply_tokens, paragraphs, read, unit


def three_pages(tmp_path):
    b = BookBuilder()
    s = b.section("chapter", "body")
    texts = ["The Analysemo-\ndell is used when the", "model grows, and it does so on every page of the",
             "book until the end of this chapter."]  # fmt: skip
    paras = []
    for n, t in enumerate(texts, 1):
        p = b.page(str(n), "body", s)
        paras.append(b.para(p, t))
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    return data, [u["id"] for u in paras]


def start_of(unit_, word):
    return next(at for w, at in edit_ops.reading_words(unit_["content"]) if w == word)


def test_the_words_are_the_words_the_book_reads(tmp_path):
    data, ids = three_pages(tmp_path)
    one = unit(data, ids[0])
    one["content"]["joins"] = [{"at": 14, "decision": "join", "hyphen_at": 13, "confidence": 1, "review_status": "ok"}]
    got = edit_ops.reading_words(one["content"])
    assert [w for w, _ in got] == ["The", "Analysemodell", "is", "used", "when", "the"]
    assert got[1][1] == 4  # a word cut at a line end starts at its first part


def test_split_a_paragraph_at_a_word(tmp_path):
    data, ids = three_pages(tmp_path)
    at = start_of(unit(data, ids[1]), "and")
    out = apply_tokens(data, {"op": "split_word", "unit": ids[1], "offset": at})
    first, second = [u for u in paragraphs(out)][1:3]
    assert first["id"] == ids[1] and second["id"] != ids[1]
    assert read(first) == "model grows," and read(second) == "and it does so on every page of the"
    assert paragraphs(out)[3]["id"] == ids[2]  # the new block sits right after the first, before the next one


def test_split_in_the_middle_of_a_hyphenated_text_keeps_every_letter(tmp_path):
    data, ids = three_pages(tmp_path)
    at = start_of(unit(data, ids[0]), "is")
    out = apply_tokens(data, {"op": "split_word", "unit": ids[0], "offset": at})
    assert read(paragraphs(out)[0]) == "The Analysemo- dell"
    assert read(paragraphs(out)[1]) == "is used when the"


def test_split_needs_a_word_after_the_first_and_a_block_that_can_split(tmp_path):
    data, ids = three_pages(tmp_path)
    for bad in (0, -3, 10_000, "x"):
        _, _, failed = overlay.apply_edits(data, [{"id": "e", "op": "split_word", "unit": ids[1], "offset": bad}])
        assert failed, bad
    head = {**data}
    data["content"][1]["type"]  # a page marker is not a block of text either
    _, _, failed = overlay.apply_edits(head, [{"id": "e", "op": "split_word", "unit": data["content"][0]["id"], "offset": 3}])
    assert failed


def test_split_a_list_item_and_a_footnote(tmp_path):
    b = BookBuilder()
    s = b.section("chapter", "body")
    p = b.page("1", "body", s)
    mark = lambda m: {"text": m, "type": "decimal", "punctuation": ".", "value": int(m[0])}  # noqa: E731
    lst = b.list(p, [b.item(p, "First point and more", mark("1.")), b.item(p, "Second point", mark("2."))], "numbered")
    note = b.para(p, "Source: a long note about it")
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    item = lst["items"][0]
    at = start_of(unit(data, item["id"]), "and")
    out = apply_tokens(data, {"op": "split_word", "unit": item["id"], "offset": at})
    items = unit(out, lst["id"])["items"]
    assert [read(i) for i in items] == ["First point", "and more", "Second point"]
    assert items[0]["marker"]["text"] == "1." and items[1]["marker"] is None
    out = apply_tokens(data, {"op": "footnote", "unit": note["id"]})
    at = start_of(unit(out, note["id"]), "a")
    out = apply_tokens(out, {"op": "split_word", "unit": note["id"], "offset": at})
    notes = [u for u in overlay.walk(out["content"]) if u[0]["type"] == "footnote"]
    assert len(notes) == 2


def test_merge_three_blocks_across_page_breaks_into_one_paragraph(tmp_path):
    data, ids = three_pages(tmp_path)
    out = apply_tokens(data, {"op": "merge", "units": [ids[2], ids[0], ids[1]]})  # any order: the text keeps its own
    kinds = [u["type"] for u in out["content"]]
    assert kinds.count("paragraph") == 1 and kinds.count("page_marker") == 3
    merged = paragraphs(out)[0]
    assert merged["id"] == ids[0] and merged["pages"] == [1, 2, 3]
    assert read(merged) == ("The Analysemo- dell is used when the model grows, and it does so on every page of the "
                            "book until the end of this chapter.")


def test_a_hyphen_cut_across_a_page_break_is_one_word_and_a_compound_stays(tmp_path):
    b = BookBuilder()
    s = b.section("chapter", "body")
    texts = ["Das Analysemo-", "dell trägt. Der Nord-", "Süd-Konflikt dauert"]
    paras = [b.para(b.page(str(n), "body", s), t) for n, t in enumerate(texts, 1)]
    data = json.loads((b.finish(tmp_path / "bk") / "book.json").read_text())
    out = apply_tokens(data, {"op": "merge", "units": [p["id"] for p in paras]})
    assert read(paragraphs(out)[0]) == "Das Analysemodell trägt. Der Nord-Süd-Konflikt dauert"


def test_split_then_merge_gives_back_the_text(tmp_path):
    data, ids = three_pages(tmp_path)
    before = read(unit(data, ids[1]))
    at = start_of(unit(data, ids[1]), "does")
    out = apply_tokens(data, {"op": "split_word", "unit": ids[1], "offset": at})
    new = paragraphs(out)[2]["id"]
    back = apply_tokens(out, {"op": "merge", "units": [ids[1], new]})
    assert read(unit(back, ids[1])) == before


@pytest.mark.parametrize("op", ["split_word"])
def test_the_change_is_known_to_the_log(op):
    from book_app import decisions

    assert op in decisions.EDIT_OPS
