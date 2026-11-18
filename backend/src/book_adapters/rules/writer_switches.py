"""Writer switches: yes/no answers the writer asks at one place each. ``ctx`` gives the
container the writer is filling (``container``) and what it is about to write (``block``)."""

from __future__ import annotations


def sidebar_children_in_para(ctx: dict) -> bool:
    """Item 27: inside a sidebar, lists, figures, tables and other embedded blocks go in a
    para."""
    return ctx.get("container") == "sidebar" and ctx.get("block") in (
        "list",
        "figure",
        "table",
        "equation",
    )


def nested_list_in_para(ctx: dict) -> bool:
    """Item 29: a list nested in a list item is wrapped in a para."""
    return ctx.get("container") == "listitem" and ctx.get("block") == "list"


def list_in_entry_in_para(ctx: dict) -> bool:
    """Item 29: a list inside a table entry is wrapped in a para."""
    return ctx.get("container") == "entry" and ctx.get("block") == "list"


def no_italic_heading_level3(ctx: dict) -> bool:
    """Item 3: italic markup is dropped from level-3 section titles."""
    return (
        ctx.get("container") == "section_title"
        and ctx.get("depth") == 3
        and ctx.get("span") in ("italic", "bold_italic")
    )


def structured_references(ctx: dict) -> bool:
    """BITS/JATS: references are written as element-citation (the writer reads the switch once)."""
    return True
