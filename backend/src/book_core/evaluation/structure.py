"""Heading, level, role, zone and contents-link evaluation against provisional derived gold.

Per book, no overall score. Tokens are (page, ordinal) over retained native tokens, as in the
other stage metrics.

- **Detection.** A reference heading is found when at least half of its aligned tokens lie in
  our headings; one of our headings is correct when at least half of its aligned tokens lie in
  reference headings. Precision counts our headings with aligned tokens; recall counts
  reference headings with aligned tokens.
- **Reference conventions.** Our headings whose tokens the reference tags as another kind
  (most often paragraphs) are grouped by our coarse style group and role. A cell of at least
  CONVENTION_MINIMUM headings that the reference never tags as a heading and sets as
  paragraphs at least 80% of the time is reported as a convention class (the reference sets
  that visual title as a paragraph); precision is reported with and without such classes.
  Nothing is tuned to them.
- **Levels.** For each found reference heading, our heading holding most of its tokens:
  exact and within-one level accuracy, split by the reference's level method (declared
  heading element vs nesting depth).
- **Roles.** Confusion of our role (mapped to coarse classes) against a reference role class
  derived from the heading's context (``reference_dialects/heading_roles.json``).
- **Zones.** Per reference unit (the zone of the page of its first token) and per page (the
  majority zone of the page's aligned tokens). A reference metadata zone is reported as is
  and also counted as front matter.
- **Contents links.** Printed entries resolved to a page and to a unit; title and target are
  correct when the linked unit's tokens lie in a reference heading on that page.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROLES_DATA = Path(__file__).resolve().parents[3] / "reference_dialects" / "heading_roles.json"
STRUCTURAL = {"part", "unit", "chapter", "lesson", "section", "subsection"}
CONVENTION_MINIMUM = 20


def _ratio(a, b):
    return round(a / b, 6) if b else None


def _segments(path):
    return [re.sub(r"\[\d+\]$", "", part) for part in path.strip("/").split("/")]


def reference_role(unit, data):
    names = _segments(unit["path"])
    if names[-1] in data["title_roles"]:
        return data["title_roles"][names[-1]]
    for name in reversed(names[:-1]):
        if name in data["container_roles"]:
            return data["container_roles"][name]
    zone = unit["zone"]
    level = unit["heading_level"] or 1
    if zone in data["zone_title_roles"]:
        if level <= data["zone_title_max_level"]:
            return data["zone_title_roles"][zone]
        return data["deeper_role"]
    if zone == "metadata":
        return data["zone_title_roles"].get("front", "structural")
    return data["structural_role"]


def our_role_class(role, zone):
    if role in {"sidebar_title", "feature_title"}:
        return "sidebar_title"
    if role in {"book_title", "front_section_title", "rear_section_title"}:
        return role
    if zone in {"front", "rear"} and role in STRUCTURAL:
        return "subsection"
    return "structural"


def heading_scores(gold, headings, unit_tokens, zone_of_page, roles_data=None):
    """``headings``: [Heading]; ``unit_tokens``: {unit id: [(page, ordinal)]}."""
    data = roles_data or json.loads(ROLES_DATA.read_text("utf-8"))
    kind_of = {}
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                kind_of[(page, ordinal)] = unit["unit"]
    units = {u["unit"]: u for u in gold.units}
    reference = {u["unit"]: {(p, o) for p, f, n in u["pdf"] for o in range(f, f + n)}
                 for u in gold.units if u["kind"] == "heading" and u["pdf"]}  # fmt: skip
    ours = {}
    for heading in headings:
        tokens = {t for uid in heading.unit_ids for t in unit_tokens.get(uid, ())}
        if heading.run_in:
            # Run-in: only the unit's leading tokens; approximate by the first line's share.
            tokens = set(sorted(tokens)[: max(1, heading.evidence.get("run_in_tokens", 1))])
        ours[heading.id] = tokens
    owner = {}
    for hid, tokens in ours.items():
        for token in tokens:
            owner[token] = hid
    in_reference = {t for tokens in reference.values() for t in tokens}
    found, level_rows = 0, defaultdict(Counter)
    confusion = defaultdict(Counter)
    misses = []
    by_id = {h.id: h for h in headings}
    for uid, tokens in reference.items():
        held = Counter(owner[t] for t in tokens if t in owner)
        covered = sum(held.values())
        unit = units[uid]
        if covered * 2 < len(tokens):
            misses.append({"unit": uid, "page": min(tokens)[0], "level": unit["heading_level"],
                           "covered": covered, "tokens": len(tokens)})  # fmt: skip
            continue
        found += 1
        heading = by_id[held.most_common(1)[0][0]]
        method = unit["heading_level_method"] or "unknown"
        row = level_rows[method]
        row["found"] += 1
        row["exact"] += heading.level == unit["heading_level"]
        row["within_one"] += abs(heading.level - (unit["heading_level"] or 0)) <= 1
        zone = zone_of_page.get(heading.page, "body")
        confusion[reference_role(unit, data)][our_role_class(heading.role, zone)] += 1
    correct, scored, wrong = 0, 0, Counter()
    convention, examples = defaultdict(Counter), defaultdict(list)
    for heading in headings:
        tokens = [t for t in ours[heading.id] if t in kind_of]
        if not tokens:
            continue
        scored += 1
        cell = f"{heading.style_group} {heading.role}"
        inside = sum(t in in_reference for t in tokens)
        if inside * 2 >= len(tokens):
            correct += 1
            convention[cell]["heading"] += 1
            continue
        kinds = Counter(units[kind_of[t]]["kind"] for t in tokens)
        kind = kinds.most_common(1)[0][0]
        wrong[kind] += 1
        convention[cell][kind] += 1
        if len(examples[cell]) < 5:
            examples[cell].append(heading.page)
    # Convention classes: one style group in one role that the reference never tags as a
    # heading and mostly sets as paragraphs (a visual title convention of the reference).
    classes = {}
    for cell, counts in convention.items():
        total = sum(counts.values())
        if (total >= CONVENTION_MINIMUM and counts.get("heading", 0) == 0
                and counts.get("paragraph", 0) >= 0.8 * total):  # fmt: skip
            classes[cell] = {**dict(counts), "example_pages": examples[cell]}
    convention_fp = sum(
        sum(v for k, v in c.items() if k != "example_pages") for c in classes.values()
    )
    precision = _ratio(correct, scored)
    recall = _ratio(found, len(reference))
    adjusted = _ratio(correct, scored - convention_fp)
    levels = {}
    for method, row in sorted(level_rows.items()):
        levels[method] = {"found": row["found"], "exact": _ratio(row["exact"], row["found"]),
                          "within_one": _ratio(row["within_one"], row["found"])}  # fmt: skip
    total = Counter()
    for row in level_rows.values():
        total.update(row)
    levels["all"] = {"found": total["found"], "exact": _ratio(total["exact"], total["found"]),
                     "within_one": _ratio(total["within_one"], total["found"])}  # fmt: skip
    return {
        "reference_headings": len(reference),
        "our_headings": len(headings),
        "our_headings_scored": scored,
        "precision": precision,
        "recall": recall,
        "f1": round(2 * precision * recall / (precision + recall), 6)
        if precision and recall
        else None,
        "false_positive_reference_kinds": dict(wrong.most_common()),
        "convention_classes": classes,
        "precision_without_convention_classes": adjusted,
        "f1_without_convention_classes": round(2 * adjusted * recall / (adjusted + recall), 6)
        if adjusted and recall
        else None,
        "levels": levels,
        "role_confusion": {k: dict(v) for k, v in sorted(confusion.items())},
        "misses": misses,
    }


def zone_scores(gold, page_zones):
    """Per unit and per page zone accuracy (metadata also counted as front)."""
    ours = {z.page: z.zone for z in page_zones}
    unit_rows, page_tokens = Counter(), defaultdict(Counter)
    confusion = defaultdict(Counter)
    for unit in gold.units:
        if not unit["pdf"]:
            continue
        page = unit["pdf"][0][0]
        zone = unit["zone"]
        mine = ours.get(page)
        unit_rows["units"] += 1
        unit_rows["exact"] += mine == zone
        unit_rows["metadata_as_front"] += mine == ("front" if zone == "metadata" else zone)
        confusion[zone][mine] += 1
        for p, _, length in unit["pdf"]:
            page_tokens[p][zone] += length
    page_rows = Counter()
    page_misses = []
    for page, zones in sorted(page_tokens.items()):
        zone = zones.most_common(1)[0][0]
        page_rows["pages"] += 1
        page_rows["exact"] += ours.get(page) == zone
        folded = "front" if zone == "metadata" else zone
        page_rows["metadata_as_front"] += ours.get(page) == folded
        if ours.get(page) != folded:
            page_misses.append({"page": page, "reference": zone, "ours": ours.get(page)})
    return {
        "units": unit_rows["units"],
        "unit_accuracy": _ratio(unit_rows["exact"], unit_rows["units"]),
        "unit_accuracy_metadata_as_front": _ratio(unit_rows["metadata_as_front"],
                                                  unit_rows["units"]),
        "pages": page_rows["pages"],
        "page_accuracy": _ratio(page_rows["exact"], page_rows["pages"]),
        "page_accuracy_metadata_as_front": _ratio(page_rows["metadata_as_front"],
                                                  page_rows["pages"]),
        "unit_confusion": {k: {str(m): n for m, n in v.items()} for k, v in confusion.items()},
        "page_misses": page_misses,
    }  # fmt: skip


def toc_scores(gold, links, unit_tokens):
    reference = set()
    for unit in gold.units:
        if unit["kind"] == "heading":
            for page, first, length in unit["pdf"]:
                reference.update((page, o) for o in range(first, first + length))
    rows = defaultdict(Counter)
    for link in links:
        kind = "printed" if link.source_page is not None else "outline"
        row = rows[kind]
        row["entries"] += 1
        row["target_resolved"] += link.target_page is not None
        row["unit_resolved"] += bool(link.unit_ids)
        tokens = [t for u in link.unit_ids for t in unit_tokens.get(u, ())]
        if tokens and sum(t in reference for t in tokens) * 2 >= len(tokens):
            row["title_and_target_correct"] += 1
    return {
        kind: {**dict(row),
               "target_resolved_share": _ratio(row["target_resolved"], row["entries"]),
               "unit_resolved_share": _ratio(row["unit_resolved"], row["entries"]),
               "title_and_target_precision": _ratio(row["title_and_target_correct"],
                                                    row["unit_resolved"])}
        for kind, row in rows.items()
    }  # fmt: skip
