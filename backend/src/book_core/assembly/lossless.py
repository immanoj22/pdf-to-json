"""Lossless check: the token multiset rebuilt from the book JSON alone, by section.

Every retained source token is in content, furniture or ``suppressed`` (hidden text,
retained by the ledger); TrimBox discards are in ``suppressed`` with
``retained_by_ledger: false``. The tokenizer is the ledger's (case-sensitive NFKC
``[\\p{L}\\p{M}\\p{N}]+``). Line ends inside a unit's text (``"\\n"``) separate tokens, as
source lines do in the ledger.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from book_core.ledger.tokenization import token_counter


def _records(node):
    """Every text of a published node (dict form), depth first."""
    if isinstance(node, dict):
        if node.get("type") == "equation":
            if node.get("content"):
                yield node["content"]
            return
        marker = node.get("marker")
        if marker:
            yield marker
        content = node.get("content")
        if isinstance(content, dict) and "text" in content:
            yield content
        elif isinstance(content, list):  # cell content
            for item in content:
                yield from _records(item)
        for key in ("items", "children"):
            for child in node.get(key) or ():
                yield from _records(child)
        for key in ("captions", "credits", "text", "notes"):
            value = node.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and "content" in item:
                        yield item["content"]
        if isinstance(node.get("title"), dict):
            yield node["title"]["content"]
        for cell in node.get("cells") or ():
            yield from _records({"content": cell["content"]})


def _texts(node):
    """Rendered texts, retained for evaluation callers."""
    for record in _records(node):
        yield record["text"]


def json_tokens(book):
    """{section: Counter} of a book dict: content, furniture, suppressed_retained,
    suppressed_discarded."""
    found = {k: Counter() for k in ("content", "furniture", "suppressed_retained",
                                    "suppressed_discarded")}  # fmt: skip
    lines = defaultdict(list)

    def add(record, section):
        text = record["text"]
        runs = sorted(record.get("source_runs") or [], key=lambda r: r["start"])
        at = 0
        for run in runs:
            if not at <= run["start"] < run["end"] <= len(text):
                raise ValueError("Overlapping or invalid source runs in lossless view")
            found[section].update(token_counter(text[at:run["start"]]))
            lines[(run["page"], run["line"], section == "suppressed_discarded")].append(
                (run["position"], run["source_start"], text[run["start"]:run["end"]], section))
            at = run["end"]
        found[section].update(token_counter(text[at:]))

    for unit in book["content"]:
        for record in _records(unit):
            add(record, "content")
    for item in book.get("furniture") or ():
        add(item["content"], "furniture")
    for item in book.get("suppressed") or ():
        key = "suppressed_retained" if item["retained_by_ledger"] else "suppressed_discarded"
        add(item, key)
    # A hidden glyph can split one source token between content and suppression. The
    # references reconstruct that source line without copying or restoring hidden text
    # to the rendered content. Mixed lines count under their visible owning section.
    priority = {"content": 0, "furniture": 1, "suppressed_retained": 2,
                "suppressed_discarded": 3}
    for pieces in lines.values():
        section = min((p[3] for p in pieces), key=priority.__getitem__)
        found[section].update(token_counter("".join(p[2] for p in sorted(pieces))))
    return found


def compare(book, retained, discarded=None):
    """Missing and extra tokens of the JSON against the ledger's retained multiset (and
    its TrimBox discards, when given)."""
    found = json_tokens(book)
    kept = found["content"] + found["furniture"] + found["suppressed_retained"]
    result = {
        "ledger_retained": sum(retained.values()),
        "json_content": sum(found["content"].values()),
        "json_furniture": sum(found["furniture"].values()),
        "json_suppressed_retained": sum(found["suppressed_retained"].values()),
        "json_suppressed_discarded": sum(found["suppressed_discarded"].values()),
        "missing": sum((retained - kept).values()),
        "extra": sum((kept - retained).values()),
        "missing_examples": sorted((retained - kept).items())[:20],
        "extra_examples": sorted((kept - retained).items())[:20],
    }
    if discarded is not None:
        result["ledger_discarded"] = sum(discarded.values())
        result["discard_missing"] = sum((discarded - found["suppressed_discarded"]).values())
        result["discard_extra"] = sum((found["suppressed_discarded"] - discarded).values())
    return result
