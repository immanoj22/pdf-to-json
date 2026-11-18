"""Browse and the review card show wrapped text as the book reads it: a word broken at a line end
by a soft hyphen is one word again (the soft hyphen is invisible, so it used to read "militar ily").
The text follows the converter's join decisions, exactly as the export does."""

from __future__ import annotations

from book_app.service import Service

SOFT = "­"


def content(text, *joins):
    return {"text": text, "joins": list(joins), "spans": []}


def join(text, nth=0, decision="soft_join"):
    at = -1
    for _ in range(nth + 1):
        at = text.index("\n", at + 1)
    return {"at": at, "decision": decision, "hyphen_at": at - 1 if decision != "keep" else None}


def test_a_soft_hyphen_word_reads_whole():
    text = f"both diplomatically and militar{SOFT}\nily. Cam{SOFT}\neron agreed."
    c = content(text, join(text, 0), join(text, 1))
    assert Service.clean_text(text, c) == "both diplomatically and militarily. Cameron agreed."


def test_a_kept_hyphen_stays_and_a_line_end_without_a_decision_is_a_space():
    text = "a well-\nknown fact and pub\nlic"
    c = content(text, join(text, 0, "keep"))
    assert Service.clean_text(text, c) == "a well-known fact and pub lic"
    # the converter did not join this soft hyphen (the next line is not its continuation):
    # the text says so; the soft hyphen itself never shows
    text = f"labora{SOFT}\nsafeguard that"
    assert Service.clean_text(text, content(text)) == "labora safeguard that"


def test_without_the_record_a_soft_hyphen_joins_its_parts():
    text = f"militar{SOFT}\nily and well-\nknown"
    assert Service.clean_text(text) == "militarily and well-known"


def test_browse_rows_and_review_items_carry_the_clean_text():
    text = f"militar{SOFT}\nily"
    unit = {"id": "u1", "type": "paragraph", "pages": [1], "content": content(text, join(text))}
    assert Service.unit_summary(unit)["clean"] == "militarily"  # the review card's current text
    assert Service.clean_fields(unit, text)["clean"] == "militarily"  # the Browse row
    item = {"type": "list_item", "id": "i1", "level": 1, "content": content(text, join(text))}
    listing = {"type": "list", "id": "l1", "items": [item], "content": None}
    assert Service.clean_fields(listing, "")["items"][0]["text"] == "militarily"
