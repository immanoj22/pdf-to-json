"""Words broken at a line end by a soft hyphen: the export writes them whole, and the lossless
check catches a word that was written in two parts ("militar ily").

The ledger only knows what the writer wrote, so a word written apart matched its own ledger and
every other check passed. ``split_words`` compares the written words with the source text."""

from __future__ import annotations

from types import SimpleNamespace

from book_adapters import qc
from book_adapters.engine import joins
from book_adapters.validate import lossless

from .test_adapter_b import base_book, export

SOFT = "­"


def soft_book(tmp_path, *paragraphs):
    b, pages = base_book()
    for text, joins in paragraphs:
        b.para(pages[0], text, joins=joins)
    return b.finish(tmp_path / "book")


def join_at(text, n=0):
    """The join record Stage 1 writes for the n-th soft hyphen at a line end."""
    at = -1
    for _ in range(n + 1):
        at = text.index(SOFT + "\n", at + 1)
    return {"at": at + 1, "decision": "soft_join", "hyphen_at": at, "confidence": 0.98}


def test_export_writes_a_soft_hyphen_word_whole(tmp_path, store):
    one = f"The army acted militar{SOFT}\nily and the pub{SOFT}\nlic agreed."
    book = soft_book(tmp_path, (one, [join_at(one, 0), join_at(one, 1)]))
    report, _, xml = export(book, tmp_path, store)
    text = " ".join("".join(xml.itertext()).split())
    assert "militarily" in text and "public" in text
    assert "militar ily" not in text and "pub lic" not in text and SOFT not in text
    split = report["checks"]["lossless"]["split_words"]
    assert (split["soft_hyphen_line_ends"], split["joined"], split["split"]) == (2, 2, 0)
    assert split["unjoined_known_word"] == 0


def test_a_line_end_without_a_record_is_joined_by_the_books_own_words(tmp_path, store):
    whole = "He acted militarily at once."
    # no join record, but the whole word is a word of the book: the loader decides the join
    apart = f"They advanced militar{SOFT}\nily and quickly."
    book = soft_book(tmp_path, (whole, []), (apart, []))
    report, _, xml = export(book, tmp_path, store)
    text = " ".join("".join(xml.itertext()).split())
    assert "militar ily" not in text and text.count("militarily") == 2
    split = report["checks"]["lossless"]["split_words"]
    assert (split["joined"], split["split"], split["unjoined_known_word"]) == (1, 0, 0)


def test_a_line_end_that_is_not_a_continuation_stays_apart(tmp_path, store):
    # "labora" is not the start of any word the book has: the next line is not its continuation
    apart = f"in the labora{SOFT}\nsafeguard that follows"
    book = soft_book(tmp_path, (apart, []), ("The laboratory is open.", []))
    report, _, xml = export(book, tmp_path, store)
    assert "laborasafeguard" not in "".join(xml.itertext())
    split = report["checks"]["lossless"]["split_words"]
    assert (split["split"], split["unjoined_known_word"], split["unjoined_other"]) == (0, 0, 1)
    _, reasons = qc.verdict(report)
    assert not any("written apart" in r for r in reasons)


def read(text, *others):
    """The text records as the loader sees them, after the missing joins were decided."""
    records = [{"text": t, "joins": [], "spans": []} for t in (text, *others)]
    added = joins.infer_joins(records)
    return records[0], added


def test_inferred_joins_use_the_three_stage_1_decisions():
    # a soft hyphen: the whole word is a word of the book
    c, added = read(f"the Polysac{SOFT}\ncharides", "polysaccharides are sugars")
    assert [(j["decision"], j["hyphen_at"]) for j in c["joins"]] == [("soft_join", c["text"].index(SOFT))]
    # a real hyphen stays (the compound is in the book, or the whole word is not)
    c, added = read("levels of CK-\nMB and", "the CK-MB fraction")
    assert [j["decision"] for j in c["joins"]] == ["keep"] and c["joins"][0]["hyphen_at"] is None
    c, _ = read("a well-\nknown fact")
    assert [j["decision"] for j in c["joins"]] == ["keep"]
    # a hyphen that only breaks a word the book otherwise writes whole drops the hyphen
    c, _ = read("the pub-\nlic agreed", "a public matter, the public")
    assert [j["decision"] for j in c["joins"]] == ["join"]
    # a word split with no hyphen: the first part is not a word of the book, the whole word is
    c, _ = read("6-phosphoglucon\nate +", "phosphogluconate is formed")
    assert [j["decision"] for j in c["joins"]] == ["word"]
    # two words that make a third stay two words: "some" is a word of the book
    c, _ = read("we need some\none else", "someone knows", "some people", "one day")
    assert c["joins"] == []
    # not a continuation: nothing is glued, and a record that exists is never changed
    c, _ = read(f"labora{SOFT}\nsafeguard that", "the laboratory")
    assert c["joins"] == []
    record = {"text": f"militar{SOFT}\nily", "joins": [join_at(f"militar{SOFT}\nily")], "spans": []}
    before = [dict(j) for j in record["joins"]]
    assert not joins.infer_joins([record, {"text": "militarily", "joins": [], "spans": []}])
    assert record["joins"] == before


def doc(*texts_and_joins):
    return SimpleNamespace(records={f"u{i}": {"text": t, "joins": j} for i, (t, j) in enumerate(texts_and_joins)})


def test_split_words_compares_the_source_with_the_written_words():
    text = f"militar{SOFT}\nily"
    joined = doc((text, [join_at(text)]))
    assert lossless.split_words(joined, ["militarily"])["split"] == 0
    # the source joined the parts; the writer wrote them apart (or lost them): an error
    assert lossless.split_words(joined, ["militar", "ily"])["split"] == 1
    # no join record, and the whole word is not in the book: the next line is not the
    # continuation (text order or columns); listed, not an error
    other = doc((f"labora{SOFT}\nsafeguard that", []))
    r = lossless.split_words(other, ["labora", "safeguard", "that"])
    assert (r["split"], r["unjoined_known_word"], r["unjoined_other"]) == (0, 0, 1)
    # a word with more than one break, and a break with nothing after it
    twice = f"a{SOFT}\nb x c{SOFT}\n"
    assert lossless.split_words(doc((twice, [])), ["ab", "x", "c"])["soft_hyphen_line_ends"] == 1
