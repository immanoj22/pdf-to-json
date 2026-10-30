"""Named rules. A profile switches rules on by name (``rules:`` or a book option's ``rule``);
YAML never holds code. Each rule is one small function.

Phases:
- ``characters``: ``f(text, ctx) -> (text, reviews)``; a same-length character substitution
  in a source text before it is written (so span offsets stay valid).
- ``tree``: ``f(doc, ctx) -> None``; rearranges the adapter document tree (declared moves and
  omissions are recorded on the refs/doc).
- ``links``: ``f(text, spans, ctx) -> [(start, end, href)]``; internal links added at render.
- ``writer``: ``f(ctx) -> bool``; a yes/no switch the writer asks at one place.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import characters, links, structure, writer_switches


@dataclass(frozen=True)
class Rule:
    name: str
    phase: str
    item: str  # guideline item (or "delivery")
    func: Callable
    description: str


RULES: dict[str, Rule] = {
    r.name: r
    for r in [
        Rule(
            "apostrophe_straight",
            "characters",
            "18",
            characters.apostrophe_straight,
            "Apostrophes are U+0027; a right single quote stays only as a closing quote.",
        ),
        Rule(
            "double_quotes_curly",
            "characters",
            "19",
            characters.double_quotes_curly,
            "Straight double quotes become U+201C/U+201D by position; unpaired ones go to review.",
        ),
        Rule(
            "minus_sign_by_context",
            "characters",
            "10",
            characters.minus_sign_by_context,
            "An en dash before a number that is a negative value becomes U+2212; "
            "unclear cases go to review.",
        ),
        Rule(
            "index_range_en_dash",
            "characters",
            "9",
            characters.index_range_en_dash,
            "Page ranges in the index use an en dash.",
        ),
        Rule(
            "sidebar_not_in_list",
            "tree",
            "26",
            structure.sidebar_not_in_list,
            "A sidebar inside a list closes the list; the list continues after it.",
        ),
        Rule(
            "set_figures_separate",
            "tree",
            "25",
            structure.set_figures_separate,
            "One image per figure; a caption naming several parts goes to review.",
        ),
        Rule(
            "numbered_figure_alone_in_table",
            "tree",
            "39",
            structure.numbered_figure_alone_in_table,
            "An untitled table holding only numbered figures is replaced by the figures.",
        ),
        Rule(
            "suggested_reading_as_chapter",
            "tree",
            "37",
            structure.suggested_reading_as_chapter,
            "Suggested Reading becomes its own chapter coded as a bullet list.",
        ),
        Rule(
            "continued_figure",
            "tree",
            "13",
            structure.continued_figure,
            "A continued numbered figure keeps formal coding with a blank label and empty title.",
        ),
        Rule(
            "epigraph_as_paras",
            "tree",
            "31",
            structure.epigraph_as_paras,
            "Epigraph text is a noindent para and its source an alignright para.",
        ),
        Rule(
            "qanda_sets",
            "tree",
            "22",
            structure.qanda_sets,
            "Each question set is its own qandadiv.",
        ),
        Rule(
            "color_plate_note_removal",
            "tree",
            "23",
            structure.color_plate_note_removal,
            '"(For color version, see Color Plate N)" notes are removed (listed as omitted).',
        ),
        Rule(
            "link_citations",
            "links",
            "delivery",
            links.link_citations,
            "Superscript reference numbers link to the chapter's bibliography entries.",
        ),
        Rule(
            "link_object_mentions",
            "links",
            "delivery",
            links.link_object_mentions,
            'Mentions such as "Fig. 1" or "Table 2" link to the object in the same chapter.',
        ),
        Rule(
            "sidebar_children_in_para",
            "writer",
            "27",
            writer_switches.sidebar_children_in_para,
            "Lists, figures and tables inside a sidebar are wrapped in para.",
        ),
        Rule(
            "nested_list_in_para",
            "writer",
            "29",
            writer_switches.nested_list_in_para,
            "A nested list inside a list item is wrapped in para.",
        ),
        Rule(
            "list_in_entry_in_para",
            "writer",
            "29",
            writer_switches.list_in_entry_in_para,
            "A list inside a table entry is wrapped in para.",
        ),
        Rule(
            "no_italic_heading_level3",
            "writer",
            "3",
            writer_switches.no_italic_heading_level3,
            "No italic markup in level-3 section titles (the house CSS sets it).",
        ),
    ]
}


def active_rules(profile, settings) -> set[str]:
    """Rules listed in the profile plus rules of book options that are true."""
    on = set(profile.get("rules") or [])
    for name, option in (profile.get("book_options") or {}).items():
        value = settings.data.get("options", {}).get(name, option.get("default"))
        if option.get("rule") and value is True:
            on.add(option["rule"])
    return on
