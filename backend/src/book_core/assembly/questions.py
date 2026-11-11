"""Question entries: a numbered stem, its lettered options and its printed answer as one unit.

A question bank prints each question as a numbered item (the stem), then its options lettered
in sequence, often in two columns (a and b on one row, c and d on the next), then an answer
line that names the key ("Ans. is 'd' ...", in any language: a short label and a quoted or
bracketed letter) and an explanation. Lists read the stem and the options as separate lists
(one per column or row) and the answer line as its own paragraph (``lists`` stops an item
at a printed answer line). This pass, over the assembled content in reading order, makes:

- the **question**: the stem item (the last item of a numbered list), anything printed
  between the stem and its options (a figure, a page marker), and one list holding every
  option in the order of its letters, whichever column it was read from;
- the **answer**: the answer line (its key must be one of the option letters) and the
  explanation units that follow, up to the next question, heading or the end of the run.

Consecutive entries form a question set. Evidence is layout and print only (numbering,
option lettering, the key); no words of any language are assumed. Units are moved, never
copied or changed, so every token stays in exactly one node.
"""

from __future__ import annotations

from book_core.assembly import schema as S
from book_core.assembly.build import sid
from book_core.lists.lines import answer_key, read_marker

LETTERED = {"lower_alpha", "upper_alpha"}
NUMBERED = {"decimal"}
BETWEEN = (S.PageMarker, S.Figure, S.Caption, S.Equation)  # may sit inside a question
ASIDE_TOKENS = 6  # a short line between a stem and its options belongs to the question


def _list_kind(unit):
    if isinstance(unit, S.Paragraph | S.Heading) and unit.content.text:
        marker = read_marker(unit.content.text)
        return "stem" if marker is not None and marker.type in NUMBERED else None
    if not isinstance(unit, S.ListNode) or not unit.items:
        return None
    types = {(item.marker.type if item.marker else None) for item in unit.items}
    if types <= NUMBERED:
        return "stem"
    if types <= LETTERED:
        return "options"
    return None


def _aside(unit):
    """A short paragraph between a stem and its options (a source note: "(NEET 2022)")."""
    return (isinstance(unit, S.Paragraph) and len(unit.content.text.split()) <= ASIDE_TOKENS
            and answer_key(unit.content.text) is None)  # fmt: skip


def _key_of(unit):
    if isinstance(unit, S.Paragraph) and unit.content.text:
        return answer_key(unit.content.text)
    return None


def _letters(items):
    return {(item.marker.text or "").strip(" .)(").casefold() for item in items if item.marker}


def _merged_options(lists):
    """One list of every option, ordered by its letter's value (stable for equal values)."""
    items = [item for node in lists for item in node.items]
    items.sort(key=lambda item: (item.marker.value or 0))
    first, last = lists[0], lists[-1]
    return first.model_copy(update={
        "items": items,
        "start": items[0].marker.value if items[0].marker else first.start,
        "pages": sorted({p for node in lists for p in node.pages}),
        "boxes": [b for node in lists for b in node.boxes],
        "continues_to": last.continues_to,
    })  # fmt: skip


def _complete(items):
    values = sorted(item.marker.value for item in items if item.marker and item.marker.value)
    return len(values) >= 2 and values == list(range(values[0], values[0] + len(values)))


def _match(content, i):
    """(entry parts, next index) for a question starting at ``content[i]``, or None."""
    stem_list = content[i]
    if _list_kind(stem_list) != "stem":
        return None
    j, between = i + 1, []
    while j < len(content) and (isinstance(content[j], BETWEEN) or _aside(content[j])):
        between.append(content[j])
        j += 1
    options = []
    while j < len(content) and _list_kind(content[j]) == "options":
        options.append(content[j])
        j += 1
        while (j < len(content) and isinstance(content[j], S.PageMarker)
               and j + 1 < len(content) and _list_kind(content[j + 1]) == "options"):  # fmt: skip
            options.append(content[j])  # a page break inside the options
            j += 1
    option_lists = [o for o in options if isinstance(o, S.ListNode)]
    option_items = [item for node in option_lists for item in node.items]
    if option_lists and not _complete(option_items):
        return None
    between += [o for o in options if not isinstance(o, S.ListNode)]  # page breaks inside
    pending = []
    while j < len(content) and isinstance(content[j], S.PageMarker):
        pending.append(content[j])
        j += 1
    key = _key_of(content[j]) if j < len(content) else None
    if key is not None and option_items and key not in _letters(option_items):
        key = None
    if key is None and not option_lists:
        return None
    answer_units = []
    if key is not None:
        answer_units.append(content[j])
        j += 1
        while j < len(content) and not _stops(content, j):
            answer_units.append(content[j])
            j += 1
    else:
        j -= len(pending)  # page markers after the options stay outside the entry
        pending = []
    return (stem_list, between, option_lists, pending, key, answer_units), j


def _stops(content, j):
    unit = content[j]
    if isinstance(unit, S.Heading | S.QuestionSet):
        return True
    return _list_kind(unit) == "stem" and _match_head(content, j)


def _match_head(content, j):
    """A numbered list that opens another question: options or an answer line follow it."""
    k = j + 1
    while k < len(content) and (isinstance(content[k], BETWEEN) or _aside(content[k])):
        k += 1
    return k < len(content) and (_list_kind(content[k]) == "options" or _key_of(content[k]))


def _part(kind, children, key=None):
    pages = sorted({p for c in children for p in c.pages})
    return S.QuestionPart(
        type=kind, key=key, id=sid(f"{kind}:{children[0].id}"), pages=pages or [1], order=0,
        provenance=S.Provenance(stages=["lists", "assembly"],
                                reasons=[f"question {kind}: numbering, option letters and the "
                                         "printed key"]),
        children=children,
    )  # fmt: skip


def _entry(parts):
    stem_list, between, option_lists, pending, key, answer_units = parts
    leading = []
    if not isinstance(stem_list, S.ListNode):  # a numbered paragraph or heading
        stem = stem_list
    else:
        stem = stem_list.items[-1]
    # Earlier numbered items of the stem's list are not part of this question.
    if isinstance(stem_list, S.ListNode) and len(stem_list.items) > 1:
        leading = [stem_list.model_copy(update={"items": stem_list.items[:-1]})]
        stem_list = stem_list.model_copy(update={"items": [stem]})
    markers = [u for u in between if isinstance(u, S.PageMarker)]
    others = [u for u in between if not isinstance(u, S.PageMarker)]
    question = [stem_list, *others]
    if option_lists:
        question.append(_merged_options(option_lists))
    question += markers  # page breaks inside the question stay in it, in page order
    parts_out = [_part("question", question)]
    if key is not None:
        parts_out.append(_part("answer", [*pending, *answer_units], key))
    marker = getattr(stem, "marker", None) or read_marker(stem.content.text)
    value = marker.value if marker is not None else None
    children = [c for part in parts_out for c in part.children]
    entry = S.QuestionEntry(
        id=sid(f"question-entry:{stem.id}"), number=value,
        pages=sorted({p for c in children for p in c.pages}) or [1], order=0,
        provenance=S.Provenance(stages=["lists", "assembly"],
                                reasons=["a numbered stem, its lettered options and its "
                                         "printed answer"]),
        children=parts_out,
    )  # fmt: skip
    return leading, entry


def group_questions(content):
    """Content with question entries grouped into question sets (top level only)."""
    out, run = [], []

    def close():
        if run:
            out.append(S.QuestionSet(
                id=sid(f"question-set:{run[0].id}"),
                pages=sorted({p for e in run for p in e.pages}), order=0,
                provenance=S.Provenance(stages=["assembly"],
                                        reasons=[f"{len(run)} consecutive question entries"]),
                children=list(run),
            ))  # fmt: skip
            run.clear()

    i = 0
    while i < len(content):
        found = _match(content, i)
        if found is None:
            if run and isinstance(content[i], S.PageMarker):
                run[-1].children[-1].children.append(content[i])  # a page break between
                i += 1
                continue
            close()
            out.append(content[i])
            i += 1
            continue
        leading, entry = _entry(found[0])
        if leading:
            close()
            out.extend(leading)
        run.append(entry)
        i = found[1]
    close()
    return out
