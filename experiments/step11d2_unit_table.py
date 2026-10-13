"""Step 11d continuation: per-unit before/after table for every changed unit of a variant.

A unit is identified by its kind, stream kind, list membership, level and the stable span IDs
of its lines. A unit that has no identical counterpart in the other version is a changed unit.
Each changed unit is judged against the provisional derived reference with the benchmark's own
definitions (no new scoring rule):

- paragraph-like reference units: pieces, exactness and merge partners as in
  ``paragraph_scores`` (Step 11 per-page view);
- reference list items: kind agreement and exactness as in ``list_item_scores``;
- reference headings: found (at least half the tokens held) and our headings correct, as in
  ``heading_scores``;
- page reading order: page-restricted ``reading_order_scores`` and reference-unit pairs.

Hidden status uses only render-confirmed invisible spans from the after layout. The verdict of
a unit is "worse" when any touched reference outcome degrades for reasons other than hidden
tokens leaving the scored set, "better" when outcomes only improve, otherwise "same".
"""

# ruff: noqa: E402
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step11c_identity as identity
from step11d2_effects import order_pairs
from step11d2_hidden import write
from step11d2_run import BASE, CACHE, CACHE10, CACHE11, read

from book_core.evaluation.derived_harness import DerivedGold
from book_core.evaluation.furniture import token_lines
from book_core.evaluation.lists import LIST_KINDS, list_items
from book_core.evaluation.paragraphs import PARAGRAPH_KINDS
from book_core.evaluation.reading_order import (
    ReadingOrderOutput,
    page_order,
    reading_order_scores,
)
from book_core.layout.models import PageLayout
from book_core.lists.cache import BookListsResult
from book_core.lists.cache import load_page as list_page
from book_core.lists.keys import book_fingerprint
from book_core.lists.models import TEXT_KINDS
from book_core.objects.analysis import verified_read
from book_core.objects.models import ObjectAnalysis
from book_core.paragraphs.text import unit_text
from book_core.structure.evidence import _read as read_evidence
from book_core.structure.models import BookStructure


def load_version(book, version):
    keys = version["keys"]
    list_key = book_fingerprint(keys["lists"])
    lists = verified_read(CACHE11 / "lists/book" / f"{list_key}.json", BookListsResult, list_key)
    structure_key = keys["lists"]["structure_decision_key"]
    structure = verified_read(
        CACHE10 / "structure/book" / f"{structure_key}.json", BookStructure, structure_key
    )
    evidence_key = keys["structure_evidence"]
    evidence = read_evidence(
        CACHE10 / "structure/evidence" / f"{evidence_key}.json.gz", evidence_key
    )
    unit_tokens = {
        u["unit"]: [(p["page"], o) for o in u["token_ordinals"]]
        for p in evidence["pages"]
        for u in p["units"]
    }
    return SimpleNamespace(keys=keys, lists=lists, structure=structure, unit_tokens=unit_tokens)


def heading_tokens(heading, unit_tokens):
    tokens = {t for uid in heading.unit_ids for t in unit_tokens.get(uid, ())}
    if heading.run_in:
        tokens = set(sorted(tokens)[: max(1, heading.evidence.get("run_in_tokens", 1))])
    return tokens


def page_state(book, number, loaded, gold, page):
    keys = loaded.keys
    layout = verified_read(
        CACHE / "layout" / keys["layout"] / f"{number}.json", PageLayout, keys["layout"]
    )
    built = list_page(loaded.lists, number, CACHE11)
    owners = token_lines(page, layout)
    unit_of_line = {lid: u for u in built.units for lid in u.line_ids}
    text_unit = {}
    for ordinal, lid in enumerate(owners):
        unit = unit_of_line.get(lid)
        if unit is not None and unit.kind in TEXT_KINDS:
            text_unit[ordinal] = unit.id
    lines = {line.id: line for line in layout.lines}
    view, _ = page_order(page, layout, built.order)
    units = {}
    for u in built.units:
        spans = frozenset(s for lid in u.line_ids for s in lines[lid].span_ids)
        units[u.id] = {
            "id": u.id,
            "kind": u.kind,
            "stream_kind": u.stream_kind,
            "list": u.list_id is not None,
            "level": u.level,
            "spans": spans,
            "tokens": sorted(i for i, lid in enumerate(owners) if lid in set(u.line_ids)),
            "text": unit_text(page.store, layout, u),
        }
    headings = [
        {
            "id": h.id,
            "level": h.level,
            "role": h.role,
            "tokens": {o for p, o in heading_tokens(h, loaded.unit_tokens) if p == number},
        }
        for h in loaded.structure.headings
        if h.page == number
    ]
    return SimpleNamespace(
        layout=layout,
        units=units,
        text_unit=text_unit,
        view=view,
        headings=headings,
        order=reading_order_scores(
            gold, ReadingOrderOutput("step11", book, {}, {}, {number: view})
        ),
        pairs=order_pairs(gold, number, view),
    )


def signature(unit):
    return (unit["kind"], unit["stream_kind"], unit["list"], unit["level"], unit["spans"])


def reference_outcomes(number, state, gold_units, item_ids, heading_refs):
    """Per reference unit on this page: the benchmark's outcomes for one version."""
    para_tokens = {
        u["unit"]: [o for p, f, n in u["pdf"] if p == number for o in range(f, f + n)]
        for u in gold_units
        if u["kind"] in PARAGRAPH_KINDS
    }
    owner = {o: uid for uid, toks in para_tokens.items() for o in toks}
    scored = {uid: [o for o in toks if o in state.text_unit] for uid, toks in para_tokens.items()}
    ours = defaultdict(set)
    for o in owner:
        if o in state.text_unit:
            ours[state.text_unit[o]].add(o)
    result = {}
    for uid, toks in scored.items():
        if not toks:
            result[uid] = {"scored_tokens": 0}
            continue
        pieces = {state.text_unit[o] for o in toks}
        exact = len(pieces) == 1 and ours[next(iter(pieces))] == set(toks)
        partners = {owner[o] for p in pieces for o in ours[p]} - {uid}
        row = {
            "scored_tokens": len(toks),
            "pieces": len(pieces),
            "exact": exact,
            "merge_partners": sorted(partners),
        }
        if uid in item_ids:
            votes = Counter(state.text_unit[o] for o in toks)
            majority = votes.most_common(1)[0][0]
            row["list_kind_agrees"] = state.units[majority]["kind"] in LIST_KINDS
        result[uid] = row
    held = {}
    for h in state.headings:
        for o in h["tokens"]:
            held[o] = h["id"]
    for uid, toks in heading_refs.items():
        covered = sum(o in held for o in toks)
        result[uid] = {"heading_found": covered * 2 >= len(toks) and bool(toks)}
    return result


def worse(a, b):
    """Reasons a reference outcome degrades from a to b (b keeps scored tokens)."""
    reasons = []
    if "heading_found" in a:
        if a["heading_found"] and not b["heading_found"]:
            reasons.append("reference heading no longer found")
        return reasons
    if not b.get("scored_tokens"):
        return reasons
    if not a.get("scored_tokens"):
        return reasons
    if a["exact"] and not b["exact"]:
        reasons.append("exact match lost")
    if b["pieces"] > a["pieces"]:
        reasons.append(f"split into more pieces ({a['pieces']} -> {b['pieces']})")
    if len(b["merge_partners"]) > len(a["merge_partners"]):
        reasons.append("merged with more reference units")
    if a.get("list_kind_agrees") and b.get("list_kind_agrees") is False:
        reasons.append("list-item kind agreement lost")
    return reasons


def better(a, b):
    reasons = []
    if "heading_found" in a:
        if b["heading_found"] and not a["heading_found"]:
            reasons.append("reference heading now found")
        return reasons
    if not a.get("scored_tokens") or not b.get("scored_tokens"):
        return reasons
    if b["exact"] and not a["exact"]:
        reasons.append("exact match gained")
    if b["pieces"] < a["pieces"]:
        reasons.append(f"fewer pieces ({a['pieces']} -> {b['pieces']})")
    if len(b["merge_partners"]) < len(a["merge_partners"]):
        reasons.append("merged with fewer reference units")
    if a.get("list_kind_agrees") is False and b.get("list_kind_agrees"):
        reasons.append("list-item kind agreement gained")
    return reasons


def our_heading_rows(state, reference_heading_tokens, gold_token_owner):
    rows = []
    for h in state.headings:
        tokens = [o for o in h["tokens"] if o in gold_token_owner]
        if not tokens:
            continue
        inside = sum(o in reference_heading_tokens for o in tokens)
        rows.append({**h, "tokens": sorted(h["tokens"]), "correct": inside * 2 >= len(tokens)})
    return rows


def main(book, variant):
    out = ROOT / "experiments/out/step11d2" / variant
    versions = [read(BASE / f"{book}.json"), read(out / f"after/{book}.json")]
    numbers = sorted(
        int(n)
        for n in versions[0]["pages"]
        if any(
            versions[0]["pages"][n][stage] != versions[1]["pages"][n][stage]
            for stage in ("reading_order", "paragraphs", "lists")
        )
    )
    gold = DerivedGold.load(ROOT / "backend/tests/gold_derived" / book)
    loaded = [load_version(book, v) for v in versions]
    item_ids = {u["unit"] for u in list_items(gold)}
    pages = {}
    totals = Counter()
    for number in numbers:
        key = versions[0]["keys"]["analysis"]
        page = verified_read(
            CACHE / "analysis" / key / f"{number}.json", ObjectAnalysis, key
        ).native.page
        states = [page_state(book, number, x, gold, page) for x in loaded]
        invisible = {
            p.span_id for p in states[1].layout.visibility_evidence if p.decision == "invisible"
        }
        gold_units = [u for u in gold.units if any(p == number for p, _, _ in u["pdf"])]
        gold_token_owner = {
            o: u["unit"]
            for u in gold_units
            for p, f, n in u["pdf"]
            if p == number
            for o in range(f, f + n)
        }
        heading_refs = {
            u["unit"]: [o for p, f, n in u["pdf"] if p == number for o in range(f, f + n)]
            for u in gold_units
            if u["kind"] == "heading"
        }
        reference_heading_tokens = {o for toks in heading_refs.values() for o in toks}
        outcomes = [
            reference_outcomes(number, s, gold_units, item_ids, heading_refs) for s in states
        ]
        hidden_tokens = {
            o for u in states[1].units.values() if u["kind"] == "invisible" for o in u["tokens"]
        }
        signatures = [{signature(u): u for u in s.units.values()} for s in states]
        rows = []
        for side, index in (("before", 0), ("after", 1)):
            other = signatures[1 - index]
            for sig, unit in signatures[index].items():
                if sig in other:
                    continue
                hidden_spans = sorted(unit["spans"] & invisible)
                touched = sorted(
                    {gold_token_owner[o] for o in unit["tokens"] if o in gold_token_owner}
                )
                worse_reasons, better_reasons, left = [], [], []
                for ref in touched:
                    a, b = outcomes[0].get(ref), outcomes[1].get(ref)
                    if a is None or b is None:
                        continue
                    w, g = worse(a, b), better(a, b)
                    if a.get("scored_tokens") and not b.get("scored_tokens"):
                        left.append(ref)
                    worse_reasons += [f"ref {ref}: {r}" for r in w]
                    better_reasons += [f"ref {ref}: {r}" for r in g]
                if worse_reasons:
                    verdict = "worse"
                elif better_reasons:
                    verdict = "better"
                else:
                    verdict = "same"
                visible_tokens = [o for o in unit["tokens"] if o not in hidden_tokens]
                rows.append(
                    {
                        "side": side,
                        "unit": unit["id"],
                        "kind": unit["kind"],
                        "stream_kind": unit["stream_kind"],
                        "in_list": unit["list"],
                        "text": unit["text"],
                        "contains_hidden_line": bool(hidden_spans) or unit["kind"] == "invisible",
                        "hidden_spans": len(hidden_spans),
                        "spans": len(unit["spans"]),
                        "tokens": len(unit["tokens"]),
                        "visible_tokens": len(visible_tokens),
                        "reference_units_touched": touched,
                        "reference_units_leaving_scoring": left,
                        "verdict": verdict,
                        "worse_reasons": worse_reasons,
                        "better_reasons": better_reasons,
                    }
                )
        heading_rows = [
            our_heading_rows(s, reference_heading_tokens, gold_token_owner) for s in states
        ]
        heading_changes = {
            "removed": [
                h
                for h in heading_rows[0]
                if h["tokens"] not in [x["tokens"] for x in heading_rows[1]]
            ],
            "added": [
                h
                for h in heading_rows[1]
                if h["tokens"] not in [x["tokens"] for x in heading_rows[0]]
            ],
        }
        for h in heading_changes["removed"] + heading_changes["added"]:
            h["text"] = " ".join(
                states[0 if h in heading_changes["removed"] else 1].units[u]["text"]
                for u in states[0 if h in heading_changes["removed"] else 1].units
                if set(states[0 if h in heading_changes["removed"] else 1].units[u]["tokens"])
                & set(h["tokens"])
            )[:200]
        pair_changes = {
            kind: {
                "added": sorted(
                    {tuple(p) for p in states[1].pairs[kind]}
                    - {tuple(p) for p in states[0].pairs[kind]}
                ),
                "removed": sorted(
                    {tuple(p) for p in states[0].pairs[kind]}
                    - {tuple(p) for p in states[1].pairs[kind]}
                ),
            }
            for kind in ("concordant", "discordant")
        }
        order_keys = ("main_flow", "float_anchors", "within_floats")
        pages[number] = {
            "rows": rows,
            "reference_outcome_changes": {
                ref: {"before": outcomes[0].get(ref), "after": outcomes[1].get(ref)}
                for ref in sorted(outcomes[0].keys() | outcomes[1].keys())
                if outcomes[0].get(ref) != outcomes[1].get(ref)
            },
            "our_heading_changes": heading_changes,
            "order_pair_changes": pair_changes,
            "page_order_scores": [
                {k: s.order.get(k) for k in order_keys if k in s.order} for s in states
            ],
            "page_anchor_detail": [
                {
                    k: v
                    for k, v in s.order.items()
                    if k in ("float_anchors", "anchor_misses", "within_floats")
                }
                for s in states
            ],
        }
        for row in rows:
            totals[(row["side"], row["contains_hidden_line"], row["verdict"])] += 1
    regressions = [
        {"page": n, **row}
        for n, data in pages.items()
        for row in data["rows"]
        if row["verdict"] == "worse" and not row["contains_hidden_line"]
    ]
    write(
        out / f"unit_table_{book}.json",
        {
            "book": book,
            "variant": variant,
            "pages": pages,
            "totals": {"|".join(map(str, k)): v for k, v in sorted(totals.items())},
            "visible_only_worse": regressions,
        },
    )
    for number, data in pages.items():
        print(f"=== page {number}")
        for row in data["rows"]:
            hidden = "yes" if row["contains_hidden_line"] else "no"
            reasons = row["worse_reasons"] + row["better_reasons"]
            print(
                f"  {row['side']:6} {row['kind']:17} hidden={hidden:3}"
                f" {row['verdict']:6} {row['text'][:60]!r} {reasons}"
            )
        print(
            "  headings",
            {
                k: [(h["text"][:40], h["correct"]) for h in v]
                for k, v in data["our_heading_changes"].items()
            },
        )
        print(
            "  pairs",
            {k: {s: len(x) for s, x in v.items()} for k, v in data["order_pair_changes"].items()},
        )
    print("visible-only worse units:", len(regressions))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=identity.BOOKS, required=True)
    parser.add_argument("--variant", default="hidden")
    args = parser.parse_args()
    main(args.book, args.variant)
