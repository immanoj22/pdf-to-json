"""List and entry evaluation against provisional derived gold, per book (no overall score).

Our side is a token view of the Step 11 units: ``Ours.unit_of`` maps each scored PDF token
(page, ordinal) owned by a text unit to its unit, with the unit's kind, list, nesting level
and cross-page chain root, and the set of tokens inside definition or index terms. Reference
units carry their kind, list membership (path and depth) and table membership.

- **List items**: reference list items outside tables (table lists wait for the tables step;
  a dialect without list-item units contributes its paragraphs inside lists, ``list_items``):
  exact match, item boundary precision/recall/F1 (``paragraphs.paragraph_scores`` restricted
  to them), by zone; kind agreement (the item's tokens sit in a list-kind unit of ours).
- **List boundaries**: over consecutive scored tokens of reference list items, a boundary is a
  change of list (reference list path; our list id, a unit outside lists being its own list).
- **Nesting**: for exactly matched items, our level vs the reference list depth, absolute and
  relative to each side's shallowest level in that list.
- **Definitions**: a reference term is exact when the term tokens of our unit holding it equal
  its tokens; a description when the rest of that unit's tokens equals it.
- **Index entries**: reference index entries (index-entry units, or list items on index pages
  when the dialect writes the index as nested lists) exact match, and sub-entry level accuracy
  (levels from ``reference_dialects/entry_levels.json``, else list depth).
- **Bibliography entries**: exact match.
- **Cross-page entries**: a reference entry with tokens on two pages is missed unless one
  chain of ours holds it; a link of ours between two entries is false unless the same
  reference unit holds both sides.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from book_core.evaluation.paragraphs import paragraph_scores

LEVELS_DATA = Path(__file__).resolve().parents[3] / "reference_dialects" / "entry_levels.json"
LIST_KINDS = frozenset(
    {"list_item", "definition_entry", "index_entry", "bibliography_entry", "contents_entry"}
)
ENTRY_GOLD = frozenset(
    {"list_item", "definition_term", "definition_description", "index_entry",
     "bibliography_entry"}
)  # fmt: skip


@dataclass
class Ours:
    unit_of: dict  # (page, ordinal) -> unit id
    kind_of: dict = field(default_factory=dict)  # unit id -> kind
    list_of: dict = field(default_factory=dict)  # unit id -> list id
    level_of: dict = field(default_factory=dict)  # unit id -> level
    chain_of: dict = field(default_factory=dict)  # unit id -> chain root
    terms: set = field(default_factory=set)  # tokens inside term spans
    links: list = field(default_factory=list)  # (from unit, to unit) cross-page links


def _ratio(a, b):
    return round(a / b, 6) if b else None


def _tokens(unit):
    return [(page, ordinal) for page, first, length in unit["pdf"]
            for ordinal in range(first, first + length)]  # fmt: skip


def _scored(unit, ours):
    return [t for t in _tokens(unit) if t in ours.unit_of]


def _majority(tokens, ours):
    votes = Counter(ours.unit_of[t] for t in tokens)
    return votes.most_common(1)[0][0] if votes else None


def _exact(tokens, ours, members):
    units = {ours.unit_of[t] for t in tokens}
    return len(units) == 1 and members[next(iter(units))] == set(tokens)


def _members(ours, scored_tokens):
    members = defaultdict(set)
    for t in scored_tokens:
        members[ours.unit_of[t]].add(t)
    return members


def list_items(gold, index_pages=()):
    """Reference list items outside tables and off index pages. A dialect that writes list
    items as paragraphs inside list elements (DocBook ``listitem/para``) has no list-item
    units; its paragraphs with list membership are the items (one per paragraph)."""
    pages = set(index_pages)
    items = [u for u in gold.units if u["kind"] == "list_item"]
    if not items:
        items = [{**u, "kind": "list_item"} for u in gold.units
                 if u["kind"] == "paragraph" and u["list"] is not None]  # fmt: skip
    return [u for u in items if u["table"] is None and (u["start"] or [None])[0] not in pages]


def list_item_scores(gold, ours, index_pages=()):
    items = list_items(gold, index_pages)
    view = SimpleNamespace(units=items)
    boundaries = paragraph_scores(view, ours.unit_of, kinds={"list_item"})
    by_zone = {}
    for zone in sorted({u["zone"] for u in items}):
        subset = SimpleNamespace(units=[u for u in items if u["zone"] == zone])
        row = paragraph_scores(subset, ours.unit_of, kinds={"list_item"})
        by_zone[zone] = {k: row[k] for k in ("reference_units_scored", "exact_unit_match",
                                             "boundary_f1")}  # fmt: skip
    # Kind agreement and list boundaries.
    kind_ok = scored_units = 0
    sequence = []
    for unit in items:
        tokens = _scored(unit, ours)
        if not tokens:
            continue
        scored_units += 1
        kind_ok += ours.kind_of.get(_majority(tokens, ours)) in LIST_KINDS
        sequence += [(t, unit["list"]["list"]) for t in tokens]
    counts = Counter()
    for (t1, l1), (t2, l2) in zip(sequence, sequence[1:], strict=False):
        u1, u2 = ours.unit_of[t1], ours.unit_of[t2]
        ref = l1 != l2
        mine = ours.list_of.get(u1, ("unit", u1)) != ours.list_of.get(u2, ("unit", u2))
        counts["tp"] += ref and mine
        counts["fp"] += mine and not ref
        counts["fn"] += ref and not mine
    p = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    r = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    f1 = round(2 * p * r / (p + r), 6) if p and r else None
    return {
        "reference_items": len(items),
        "items_scored": boundaries["reference_units_scored"],
        "exact_match": boundaries["exact_unit_match"],
        "item_boundary_precision": boundaries["boundary_precision"],
        "item_boundary_recall": boundaries["boundary_recall"],
        "item_boundary_f1": boundaries["boundary_f1"],
        "split_errors": boundaries["split_errors"],
        "merge_errors": boundaries["merge_errors"],
        "kind_agreement": _ratio(kind_ok, scored_units),
        "list_boundary": {"precision": p, "recall": r, "f1": f1,
                          "reference_boundaries": counts["tp"] + counts["fn"]},
        "nesting": nesting_scores(items, ours),
        "by_zone": by_zone,
    }  # fmt: skip


def nesting_scores(items, ours):
    scored = [t for u in items for t in _scored(u, ours)]
    members = _members(ours, scored)
    pairs = []
    for unit in items:
        tokens = _scored(unit, ours)
        if tokens and _exact(tokens, ours, members):
            mine = ours.unit_of[tokens[0]]
            if ours.level_of.get(mine) is not None:
                pairs.append((unit["list"]["list"], unit["list"]["depth"], ours.list_of.get(mine),
                              ours.level_of[mine]))  # fmt: skip
    if not pairs:
        return {"items": 0, "exact": None, "relative_exact": None}
    ref_min, our_min = defaultdict(lambda: 99), defaultdict(lambda: 99)
    for ref_list, depth, our_list, level in pairs:
        ref_min[ref_list] = min(ref_min[ref_list], depth)
        our_min[our_list] = min(our_min[our_list], level)
    exact = sum(depth == level for _, depth, _, level in pairs)
    relative = sum(depth - ref_min[rl] == level - our_min[ol] for rl, depth, ol, level in pairs)
    depths = Counter(depth for _, depth, _, _ in pairs)
    return {"items": len(pairs), "exact": _ratio(exact, len(pairs)),
            "relative_exact": _ratio(relative, len(pairs)),
            "reference_depths": dict(sorted(depths.items()))}  # fmt: skip


def definition_scores(gold, ours):
    units = [u for u in gold.units if u["kind"] in {"definition_term", "definition_description"}]
    scored = [t for u in units for t in _scored(u, ours)]
    # Our unit members over all scored tokens of the page (term + description).
    members = defaultdict(set)
    for t, unit in ours.unit_of.items():
        members[unit].add(t)
    rows = defaultdict(Counter)
    for unit in units:
        tokens = set(_scored(unit, ours))
        if not tokens:
            continue
        row = rows[unit["kind"]]
        row["scored"] += 1
        mine = _majority(tokens, ours)
        whole = members[mine]
        terms = {t for t in whole if t in ours.terms}
        if unit["kind"] == "definition_term":
            row["exact"] += terms == tokens
        else:
            description = {t for t in whole - terms if t in set(scored) or t in tokens}
            row["exact"] += description == tokens
    return {
        kind: {"scored": row["scored"], "exact": _ratio(row["exact"], row["scored"])}
        for kind, row in sorted(rows.items())
    }


def _levels():
    return json.loads(LEVELS_DATA.read_text("utf-8"))["index_entry_levels"]


def index_scores(gold, ours, index_pages=()):
    """Index entries: index-entry units, else list items on the given index pages."""
    pages = set(index_pages)
    entries = [u for u in gold.units if u["kind"] == "index_entry"]
    source = "index_entry units"
    if not entries and pages:
        entries = [u for u in gold.units if u["kind"] == "list_item" and u["start"]
                   and u["start"][0] in pages]  # fmt: skip
        source = "list items on index pages"
    levels = _levels()
    scored = [t for u in entries for t in _scored(u, ours)]
    members = _members(ours, scored)
    counts = Counter()
    for unit in entries:
        tokens = _scored(unit, ours)
        if not tokens:
            continue
        counts["scored"] += 1
        if not _exact(tokens, ours, members):
            continue
        counts["exact"] += 1
        reference = levels.get(unit["element"]) or (unit["list"] or {}).get("depth") or 1
        level = ours.level_of.get(ours.unit_of[tokens[0]])
        counts["level_scored"] += level is not None
        counts["level_exact"] += level == reference
        counts[f"reference_level_{reference}"] += 1
    return {
        "source": source,
        "reference_entries": len(entries),
        "scored": counts["scored"],
        "exact_match": _ratio(counts["exact"], counts["scored"]),
        "sub_entry_level_accuracy": _ratio(counts["level_exact"], counts["level_scored"]),
        "reference_levels": {k[16:]: v for k, v in counts.items()
                             if k.startswith("reference_level_")},
    }  # fmt: skip


def bibliography_scores(gold, ours):
    entries = [u for u in gold.units if u["kind"] == "bibliography_entry"]
    view = SimpleNamespace(units=entries)
    row = paragraph_scores(view, ours.unit_of, kinds={"bibliography_entry"})
    return {k: row[k] for k in ("reference_units_scored", "exact_unit_match", "boundary_f1",
                                "split_errors", "merge_errors")}  # fmt: skip


def cross_page_scores(gold, ours):
    entries = [u for u in gold.units if u["kind"] in ENTRY_GOLD]
    missed = held = 0
    owner = {}
    for unit in entries:
        tokens = _scored(unit, ours)
        for t in tokens:
            owner[t] = unit["unit"]
        if len({p for p, _ in tokens}) < 2:
            continue
        roots = {ours.chain_of.get(ours.unit_of[t], ours.unit_of[t]) for t in tokens}
        held += len(roots) == 1
        missed += len(roots) > 1
    tokens_of = defaultdict(list)
    for t, unit in ours.unit_of.items():
        tokens_of[unit].append(t)
    false = right = 0
    for a, b in ours.links:
        left = Counter(owner[t] for t in tokens_of.get(a, []) if t in owner)
        right_side = Counter(owner[t] for t in tokens_of.get(b, []) if t in owner)
        if not left or not right_side:
            continue
        same = left.most_common(1)[0][0] == right_side.most_common(1)[0][0]
        right += same
        false += not same
    return {"reference_cross_page_entries": held + missed, "held_in_one_chain": held,
            "missed_continuations": missed, "our_entry_links": false + right,
            "false_joins": false, "correct_links": right,
            "errors": missed + false}  # fmt: skip
