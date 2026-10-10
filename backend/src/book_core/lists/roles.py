"""List roles from structure and punctuation, never from book-specific labels or words.

- **questions**: most items end with a question mark (of any script);
- **question_answer**: question items each followed, in their stream, by running text before
  the next item (the answers stay paragraph units);
- **activities**: a numbered list set in a box (sidebar, callout, note or card stream), or
  one whose items open with a heavier lead term after the number;
- **objectives**: a marked list in the main flow opened by a lead-in ending with a colon,
  right after a Step 10 heading (within two units);
- **general** otherwise.
"""

from __future__ import annotations

BOXES = frozenset({"sidebar", "callout", "note", "card"})


def list_role(lst, items, units, position, context, evidence, config):
    """(role, reason) of one page-local list."""
    if lst.kind not in {"bulleted", "numbered", "lettered", "unmarked"}:
        return "general", "entry list"
    questions = sum(u.item_role == "question" for u in items)
    if items and questions / len(items) >= config["question_share"]:
        answered = 0
        for item in items:
            index = position[item.id]
            following = units[index + 1] if index + 1 < len(units) else None
            answered += bool(
                following is not None and following.stream_id == item.stream_id
                and following.kind == "paragraph"
            )  # fmt: skip
        if answered == len(items) and len(items) >= 2:
            return "question_answer", "each question item is followed by running text"
        return "questions", f"{questions} of {len(items)} items end with a question mark"
    if lst.kind == "numbered":
        if items and items[0].stream_kind in BOXES:
            return "activities", "numbered list set in a box"
        leads = sum(bool(evidence[u.line_ids[0]].term_end) for u in items)
        if items and leads / len(items) >= 0.5:
            return "activities", "numbered items open with a heavier lead term"
    first = items[0] if items else None
    if first is not None and first.stream_kind == "main":
        same = [u for u in units[: position[first.id]] if u.stream_id == first.stream_id]
        if same and evidence[same[-1].line_ids[-1]].text.rstrip().endswith((":", "：")):
            if any(set(u.source_unit_ids) & context.heading_units for u in same[-3:-1]):
                return "objectives", "a lead-in with a colon right after a heading opens it"
    return "general", "no role evidence"
