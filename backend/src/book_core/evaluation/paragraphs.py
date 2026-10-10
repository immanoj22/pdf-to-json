"""Paragraph evaluation against provisional derived gold, per book (no overall score).

Reference units of paragraph-like kinds (paragraph, caption, list_item, definition_description)
are compared with our logical paragraphs (a unit plus its cross-page continuations), on PDF
tokens aligned to those reference units and owned by our text units:

- boundary precision/recall/F1 over pairs of consecutive tokens in reference order (both in
  paragraph-like units): the reference has a boundary when the units differ, we have one when
  our logical paragraphs differ;
- exact unit match: a reference unit whose scored tokens equal one logical paragraph's;
- split errors: extra pieces a reference unit is cut into; merge errors: extra reference units
  one logical paragraph holds;
- hyphen decisions vs reference spelling (the aligner maps both fragments to one reference
  token when the reference spells the word joined);
- joins across columns and pages: our join vs whether the reference keeps the text in one unit.
"""

from __future__ import annotations

from collections import Counter, defaultdict

PARAGRAPH_KINDS = frozenset({"paragraph", "caption", "list_item", "definition_description"})


def reference_tokens(gold, kinds=PARAGRAPH_KINDS):
    """[(page, ordinal, unit)] in reference order, and {(page, ordinal): unit}."""
    sequence, owner = [], {}
    for unit in gold.units:
        if unit["kind"] not in kinds:
            continue
        for page, first, length in unit["pdf"]:
            for ordinal in range(first, first + length):
                sequence.append((page, ordinal, unit["unit"]))
                owner[(page, ordinal)] = unit["unit"]
    return sequence, owner


def _ratio(a, b):
    return round(a / b, 6) if b else None


def paragraph_scores(gold, logical, kinds=PARAGRAPH_KINDS):
    """``logical``: {(page, ordinal): logical paragraph id} for tokens in our text units."""
    sequence, owner = reference_tokens(gold, kinds)
    scored = [(p, o, u) for p, o, u in sequence if (p, o) in logical]
    counts = Counter()
    for (p1, o1, u1), (p2, o2, u2) in zip(scored, scored[1:], strict=False):
        ref = u1 != u2
        ours = logical[(p1, o1)] != logical[(p2, o2)]
        counts["pairs"] += 1
        counts["tp"] += ref and ours
        counts["fp"] += ours and not ref
        counts["fn"] += ref and not ours
    precision = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    recall = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    f1 = round(2 * precision * recall / (precision + recall), 6) if precision and recall else None
    ref_tokens = defaultdict(set)
    our_tokens = defaultdict(set)
    for p, o, u in scored:
        ref_tokens[u].add((p, o))
        our_tokens[logical[(p, o)]].add((p, o))
    pieces = {u: {logical[t] for t in tokens} for u, tokens in ref_tokens.items()}
    holds = {g: {owner[t] for t in tokens} for g, tokens in our_tokens.items()}
    exact = sum(
        1 for u, tokens in ref_tokens.items() if len(pieces[u]) == 1
        and our_tokens[next(iter(pieces[u]))] == tokens
    )  # fmt: skip
    by_kind = defaultdict(Counter)
    kind_of = {unit["unit"]: unit["kind"] for unit in gold.units}
    for u, tokens in ref_tokens.items():
        row = by_kind[kind_of[u]]
        row["units"] += 1
        row["exact"] += len(pieces[u]) == 1 and our_tokens[next(iter(pieces[u]))] == tokens
        row["split"] += len(pieces[u]) > 1
    return {
        "reference_units_scored": len(ref_tokens),
        "logical_paragraphs_scored": len(our_tokens),
        "boundary_pairs": counts["pairs"],
        "boundary_precision": precision,
        "boundary_recall": recall,
        "boundary_f1": f1,
        "exact_unit_match": _ratio(exact, len(ref_tokens)),
        "exact_units": exact,
        "split_errors": sum(len(v) - 1 for v in pieces.values()),
        "units_split": sum(len(v) > 1 for v in pieces.values()),
        "merge_errors": sum(len(v) - 1 for v in holds.values()),
        "paragraphs_merging": sum(len(v) > 1 for v in holds.values()),
        "by_kind": {
            k: {"units": v["units"], "exact": _ratio(v["exact"], v["units"]), "split": v["split"]}
            for k, v in sorted(by_kind.items())
        },  # fmt: skip
    }


def join_scores(gold, joins, kinds=PARAGRAPH_KINDS):
    """Precision/recall of joins across columns or pages.

    ``joins``: [(kind, joined?, (page, last ordinal of a), (page, first ordinal of b))] for every
    candidate transition (each column change inside a stream and each page change of the main
    flow), whether or not we joined it.
    """
    sequence, owner = reference_tokens(gold, kinds)
    following = {}
    for (_, _, a), (_, _, b) in zip(sequence, sequence[1:], strict=False):
        if a != b:
            following.setdefault(a, b)
    table = defaultdict(Counter)
    for kind, joined, left, right in joins:
        if left not in owner or right not in owner:
            continue
        ref = owner[left] == owner[right]
        # A reference that splits paragraphs at page breaks keeps the halves as consecutive
        # units; "adjacent" counts joins of the same or of consecutive reference units.
        adjacent = ref or following.get(owner[left]) == owner[right]
        row = table[kind]
        row["candidates"] += 1
        row["tp"] += joined and ref
        row["fp"] += joined and not ref
        row["fn"] += ref and not joined
        row["adjacent"] += joined and adjacent
    return {
        kind: {
            "candidates": row["candidates"],
            "reference_joins": row["tp"] + row["fn"],
            "our_joins": row["tp"] + row["fp"],
            "precision": _ratio(row["tp"], row["tp"] + row["fp"]),
            "recall": _ratio(row["tp"], row["tp"] + row["fn"]),
            "joins_of_adjacent_reference_units": row["adjacent"],
            "adjacency_precision": _ratio(row["adjacent"], row["tp"] + row["fp"]),
        }
        for kind, row in sorted(table.items())
    }


def hyphen_scores(decisions, pdf_xml):
    """Hyphen decisions vs reference spelling.

    ``decisions``: [(choice, (page, left ordinal), (page, right ordinal))];
    ``pdf_xml``: {page: [reference token index or -1 per ordinal]} from the alignment.
    Join is right when both fragments map to one reference token; keep when they map to two.
    """
    counts = Counter()
    for choice, (p1, o1), (p2, o2) in decisions:
        left = pdf_xml.get(p1, [])[o1] if o1 < len(pdf_xml.get(p1, [])) else -1
        right = pdf_xml.get(p2, [])[o2] if o2 < len(pdf_xml.get(p2, [])) else -1
        counts[f"decisions_{choice}"] += 1
        if left < 0 or right < 0:
            counts["unaligned"] += 1
            continue
        reference_joined = left == right
        ours_joined = choice in {"join", "soft_join"}
        counts["scored"] += 1
        counts["correct"] += reference_joined == ours_joined
        counts[f"reference_{'joined' if reference_joined else 'separate'}"] += 1
        counts[f"{choice}_correct"] += reference_joined == ours_joined
    return {
        **dict(counts),
        "accuracy": _ratio(counts["correct"], counts["scored"]),
    }
