"""Step 21 item 7: a numbered stem, its options and its printed answer group as one entry."""

from book_core.assembly import schema as S
from book_core.assembly.questions import group_questions
from book_core.lists.lines import read_marker

PROV = S.Provenance(stages=["test"])
_count = [0]


def uid():
    _count[0] += 1
    return f"{_count[0]:016x}"


def common(**extra):
    return {"id": uid(), "pages": [1], "order": 0, "provenance": PROV, **extra}


def text(value):
    return S.TextContent(text=value)


def paragraph(value):
    return S.Paragraph(**common(content=text(value)))


def item(marker_text):
    head = marker_text.split()[0]
    if head[0].isalpha():  # an option letter (the lists stage settles "c" as a letter)
        marker = S.Marker(text=head, type="lower_alpha", value=ord(head[0]) - 96)
    else:
        found = read_marker(marker_text)
        marker = S.Marker(text=head, type=found.type, value=found.value)
    return S.ListItem(**common(marker=marker, content=text(marker_text.split(None, 1)[1])))


def numbered(value):
    return S.ListNode(**common(list_id=uid(), segment=0, list_type="numbered", items=[item(value)]))


def options(*values):
    return S.ListNode(**common(list_id=uid(), segment=0, list_type="lettered",
                               items=[item(v) for v in values]))  # fmt: skip


def figure():
    return S.Figure(**common(kind="photo", name="f"))


def entries(content):
    out = group_questions(content)
    return [e for unit in out if isinstance(unit, S.QuestionSet) for e in unit.children]


def test_legend_paragraphs_between_the_stem_and_its_options_stay_in_the_question():
    content = [
        numbered("59. A woodworker presented with a chronic infection"),
        figure(),
        paragraph("Chromoblastomycosis: verrucous dermatitis seen on the limbs"),
        paragraph("Clinical features: warty lesions that resemble florets"),
        options("a. Chromoblastomycosis", "b. Phaeohyphomycosis"),
        options("c. Chromomycosis", "d. Rhinosporidiosis"),
        paragraph("Ans. is 'a' Chromoblastomycosis"),
    ]
    found = entries(content)
    assert [e.number for e in found] == [59]
    question = found[0].children[0]
    assert [c.type for c in question.children][-1] == "list"
    assert len(question.children[-1].items) == 4
    assert found[0].children[1].key == "a"


def test_a_legend_search_stops_at_the_next_question():
    content = [
        numbered("59. A woodworker presented with a chronic infection"),
        paragraph("Some printed explanation that is not an option list at all"),
        numbered("60. Another stem"),
        options("a. One", "b. Two"),
        paragraph("Ans. is 'a' One"),
    ]
    assert [e.number for e in entries(content)] == [60]
