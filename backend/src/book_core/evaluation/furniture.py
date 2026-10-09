"""Furniture-stage evaluation against provisional derived gold, per book (no overall score).

- Page markers: label accuracy (our label on the gold marker's placed page) and placement
  accuracy (the one physical page carrying the gold label is the gold page). Gold markers
  excluded from gates, unplaced, or whose label is not a page label (front/special
  placeholders) are counted separately, never scored.
- Furniture precision: retained tokens on lines given a furniture role that are aligned to a
  reference content unit are false furniture; the rest are presumed true. Reported by class.
- Recall proxy: tokens the aligner diagnosed as furniture/folio candidates that stay content.
  Aligner causes are diagnostics only (confirmed decision), never a gate.
- Navigation: printed TOC targets resolved through the page markers, before and after.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from book_core.furniture.labels import label_candidates
from book_core.ledger.tokenization import line_tokens

FURNITURE = ("running_head", "running_foot", "folio", "production_mark")


def token_lines(page, layout):
    """Visual line id of each retained token ordinal (the benchmark/ledger token order)."""
    span_line = {sid: line.id for line in layout.lines for sid in line.span_ids}
    owners = []
    for line in page.store.lines:
        raw = page.store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        for token in line_tokens(page.store, line):
            owners.append(next((span_line[s] for s in token.span_ids if s in span_line), None))
    return owners


def aligned_tokens(gold):
    """{page: {ordinal: unit kind}} for every PDF token aligned to a reference unit."""
    aligned = defaultdict(dict)
    for unit in gold.units:
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                aligned[page][ordinal] = unit["kind"]
    return aligned


def marker_scores(gold, markers):
    """Label and placement accuracy of page markers against the derived-gold markers."""
    ours = {m.page: m for m in markers}
    pages_of = defaultdict(list)
    for m in markers:
        if m.label is not None:
            pages_of[m.label].append(m.page)
    counts = Counter()
    misses = []
    by_source = defaultdict(Counter)
    for marker in gold.markers:
        if marker["excluded_from_gates"]:
            counts["excluded_from_gates"] += 1
            continue
        if not label_candidates(marker["label"]):
            counts["not_a_page_label"] += 1
            continue
        if marker["pdf_page"] is None:
            counts["unplaced_in_gold"] += 1
            continue
        counts["scored"] += 1
        page = marker["pdf_page"]
        mine = ours.get(page)
        label_ok = mine is not None and mine.label == marker["label"]
        placed = pages_of.get(marker["label"], [])
        place_ok = placed == [page]
        counts["label_correct"] += label_ok
        counts["placement_correct"] += place_ok
        source = mine.source if mine is not None else "none"
        by_source[source]["scored"] += 1
        by_source[source]["label_correct"] += label_ok
        if not (label_ok and place_ok):
            misses.append(
                {
                    "gold_label": marker["label"],
                    "gold_page": page,
                    "our_label": mine.label if mine else None,
                    "our_source": source,
                    "our_pages_with_gold_label": placed,
                }
            )
    scored = counts["scored"]
    return {
        "gold_markers": len(gold.markers),
        **{k: counts[k] for k in ("excluded_from_gates", "not_a_page_label", "unplaced_in_gold")},
        "scored": scored,
        "label_accuracy": round(counts["label_correct"] / scored, 6) if scored else None,
        "placement_accuracy": round(counts["placement_correct"] / scored, 6) if scored else None,
        "by_our_source": {k: dict(v) for k, v in sorted(by_source.items())},
        "misses": misses,
    }


def furniture_precision(gold, token_roles, token_groups, token_text=None, top=15):
    """Furniture tokens aligned to reference units (false furniture) vs not aligned, by class.

    ``token_roles``/``token_groups``: {page: [role or None per retained token ordinal]}.
    """
    aligned = aligned_tokens(gold)
    by_class = defaultdict(Counter)
    false_groups = defaultdict(Counter)
    samples = {}
    for page, roles in token_roles.items():
        for ordinal, role in enumerate(roles):
            if role is None:
                continue
            row = by_class[role]
            row["tokens"] += 1
            kind = aligned.get(page, {}).get(ordinal)
            if kind is None:
                continue
            row["aligned_to_reference"] += 1
            if role in FURNITURE:
                key = (role, token_groups[page][ordinal])
                false_groups[key]["tokens"] += 1
                false_groups[key][f"kind:{kind}"] += 1
                samples.setdefault(key, set()).add(page)
    classes = {}
    for role, row in sorted(by_class.items()):
        tokens, wrong = row["tokens"], row["aligned_to_reference"]
        classes[role] = {
            "tokens": tokens,
            "aligned_to_reference": wrong,
            "not_aligned": tokens - wrong,
            "precision_proxy": round(1 - wrong / tokens, 6)
            if tokens and role in FURNITURE
            else None,
        }
    furniture_tokens = sum(classes[r]["tokens"] for r in FURNITURE if r in classes)
    furniture_wrong = sum(classes[r]["aligned_to_reference"] for r in FURNITURE if r in classes)
    groups = sorted(false_groups.items(), key=lambda kv: -kv[1]["tokens"])[:top]
    return {
        "by_class": classes,
        "furniture_tokens": furniture_tokens,
        "false_furniture_tokens": furniture_wrong,
        "precision_proxy": round(1 - furniture_wrong / furniture_tokens, 6)
        if furniture_tokens
        else None,
        "top_false_groups": [
            {
                "role": role,
                "group_id": group,
                "tokens": counts["tokens"],
                "reference_kinds": {k[5:]: v for k, v in counts.items() if k.startswith("kind:")},
                "pages": sorted(samples[(role, group)])[:10],
                "sample": token_text(role, group) if token_text else None,
            }
            for (role, group), counts in groups
        ],
    }


def recall_proxy(token_roles, causes):
    """Aligner furniture/folio diagnostics on tokens that stay content (diagnostic only).

    ``causes``: {page: [aligner PDF cause per retained token ordinal]}.
    """
    table = defaultdict(Counter)
    for page, roles in token_roles.items():
        page_causes = causes.get(page, [])
        for ordinal, role in enumerate(roles):
            cause = page_causes[ordinal] if ordinal < len(page_causes) else ""
            if cause not in {"furniture_candidate", "folio_candidate"}:
                continue
            table[cause]["tokens"] += 1
            table[cause]["classified_furniture"] += role in FURNITURE
            table[cause][f"role:{role}"] += 1
    return {
        cause: {
            "tokens": row["tokens"],
            "classified_furniture": row["classified_furniture"],
            "kept_as_content_or_box": row["tokens"] - row["classified_furniture"],
            "roles": {k[5:]: v for k, v in row.items() if k.startswith("role:")},
        }
        for cause, row in sorted(table.items())
    }


def toc_resolution(entries, markers):
    """Printed TOC targets: Step 6 resolution (PDF labels) vs resolution through page markers."""
    pages_of = defaultdict(list)
    for m in markers:
        if m.label is not None:
            pages_of[m.label].append(m.page)
    counts = Counter()
    resolved = []
    for entry in entries:
        counts["entries"] += 1
        before = entry.get("target_pages") or []
        counts["before_resolved"] += len(before) == 1
        counts["before_ambiguous"] += len(before) > 1
        label = entry.get("target_label")
        after = sorted(pages_of.get(label, [])) if label else []
        counts["after_resolved"] += len(after) == 1
        counts["after_ambiguous"] += len(after) > 1
        counts["after_unresolved"] += not after
        if before and len(before) == 1 and len(after) == 1:
            counts["both_resolved"] += 1
            counts["both_agree"] += before == after
        resolved.append(
            {**entry, "target_pages": after, "target_page": after[0] if len(after) == 1 else None}
        )
    return dict(counts), resolved
