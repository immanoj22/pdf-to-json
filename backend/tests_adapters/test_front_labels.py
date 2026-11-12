"""Front-matter page labels: a blank page after a roman-numbered page continues the series."""

from book_adapters.engine.outline import continue_front_labels, roman_label


def page(index, label, zone="front"):
    return {"index": index, "label": label, "zone": zone, "label_source": "printed"}


def test_blank_last_front_page_continues_the_roman_series():
    pages = [page(13, "xiii"), page(14, "xiv"), page(15, "xv"), page(16, None),
             page(17, "1", "body")]  # fmt: skip
    labels = [p["label"] for p in continue_front_labels(pages)]
    assert labels == ["xiii", "xiv", "xv", "xvi", "1"]
    assert continue_front_labels(pages)[3]["label_source"] == "inferred"


def test_body_pages_and_a_front_page_after_arabic_labels_stay_unlabelled():
    pages = [page(1, "1", "body"), page(2, None, "body"), page(3, None)]
    assert [p["label"] for p in continue_front_labels(pages)] == ["1", None, None]


def test_uppercase_series_and_input_is_not_changed():
    pages = [page(1, "IX"), page(2, None)]
    assert [p["label"] for p in continue_front_labels(pages)] == ["IX", "X"]
    assert pages[1]["label"] is None
    assert roman_label(14, False) == "xiv"


def test_continued_figure_caption_pattern():
    """A caption ending in a separator and "Continued" marks a continued figure, as
    "(Contd.)" does; ordinary captions with the word do not."""
    import re
    from pathlib import Path

    from book_adapters.engine.profile import load_profile

    root = Path(__file__).resolve().parents[2] / "profiles"
    pattern = load_profile(root / "jaypee/jaypee_v5.yaml").get("figures.continued_pattern")
    for text in ("TO H: Continued", "Fig. 3 (Contd.)", "Findings — continued."):
        assert re.search(pattern, text), text
    for text in ("Continued fraction of the sinus", "Discontinued therapy: results"):
        assert not re.search(pattern, text), text


def test_question_wrappers_are_opened_in_reading_order():
    from book_adapters.engine.outline import flatten_questions

    kinds = ("list", "list", "paragraph", "heading")
    stem, options, key, after = ({"type": t, "id": t} for t in kinds)
    entry = {"type": "question_entry", "id": "e", "children": [
        {"type": "question", "id": "q", "children": [stem, options]},
        {"type": "answer", "id": "a", "children": [key]}]}  # fmt: skip
    units = [{"type": "question_set", "id": "s", "children": [entry]}, after]
    assert [u["id"] for u in flatten_questions(units)] == ["list", "list", "paragraph", "heading"]
