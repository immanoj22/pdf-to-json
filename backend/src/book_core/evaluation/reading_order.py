"""Reading-order evaluation against provisional derived gold (reference unit order).

Reference units are in XML order; each references retained PDF tokens as (page, ordinal). Per
page, a unit belongs to the stream holding most of its tokens on that page. Then:

- main flow: pairwise order agreement and Kendall tau between main units (unit position = median
  rank of its tokens in the main flow), plus adjacent-pair agreement over reference neighbours;
- float anchors: per float stream, the reference anchor is the last main unit that precedes the
  stream's first reference unit on that page (or the page start); the prediction is the unit
  owning the last aligned main token before the stream's anchor. Paragraphs are not decided yet,
  so an anchor inside the right unit is correct;
- within floats: pairwise order agreement of units inside one float stream;
- conventions: where the reference reads each stream kind relative to the page's main units.

Floats and the main flow are scored separately, per book, never combined into an overall score.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

from book_core.ledger.tokenization import line_tokens
from book_core.reference.pdf_tokens import page_tokens


@dataclass(frozen=True)
class PageOrder:
    main: list[int]  # token ordinals in main-flow order
    streams: dict[str, dict]  # stream id -> {kind, tokens: [ordinals], anchor: main index}
    stream_of: dict[int, str]


@dataclass(frozen=True)
class ReadingOrderOutput:
    """A reading-order stage output; also usable by the token-ownership metrics."""

    stage: str
    book: str
    owners: dict[int, list[str | None]]
    token_digests: dict[int, str]
    pages: dict[int, PageOrder] = field(default_factory=dict)


def page_order(page, layout, order):
    """Token-level view of one page's reading order (tokens map to lines through their spans)."""
    span_line = {sid: line.id for line in layout.lines for sid in line.span_ids}
    store = page.store
    tokens_of = defaultdict(list)
    ordinal = 0
    for line in store.lines:
        raw = store.raw_line_text(line)
        if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
            continue
        for token in line_tokens(store, line):
            visual = next((span_line[s] for s in token.span_ids if s in span_line), None)
            tokens_of[visual].append(ordinal)
            ordinal += 1
    main_ids = order.main.line_ids
    main = [t for lid in main_ids for t in tokens_of.get(lid, [])]
    streams, stream_of = {}, {}
    for stream in order.streams:
        tokens = [t for lid in stream.line_ids for t in tokens_of.get(lid, [])]
        for t in tokens:
            stream_of[t] = stream.id
        anchor = None
        if stream.anchor is not None:
            before = main_ids[: stream.anchor.position + 1]
            anchor = sum(len(tokens_of.get(lid, [])) for lid in before)
        streams[stream.id] = {"kind": stream.kind, "tokens": tokens, "anchor": anchor}
    return PageOrder(main, streams, stream_of), ordinal


def reading_order_output(book, items):
    """Build the stage output from (ExtractedPage, PageLayout, PageReadingOrder) triples."""
    owners, digests, pages = {}, {}, {}
    for page, layout, order in items:
        view, count = page_order(page, layout, order)
        number = page.geometry.page
        reference = page_tokens(page)
        if count != len(reference.tokens):
            raise ValueError(f"page {number}: token count differs from the benchmark view")
        owners[number] = [view.stream_of.get(i) for i in range(count)]
        digests[number] = reference.digest
        pages[number] = view
    return ReadingOrderOutput("reading_order", book, owners, digests, pages)


def _pairs(sequence):
    """Concordant/discordant pairs of predicted positions listed in reference order."""
    concordant = discordant = 0
    for i, a in enumerate(sequence):
        for b in sequence[i + 1 :]:
            if a < b:
                concordant += 1
            elif a > b:
                discordant += 1
    return concordant, discordant


def _ratio(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def reading_order_scores(gold, output, min_confidence=0.0):
    pages = output.pages
    units_on = defaultdict(list)
    for unit in gold.units:
        if unit["confidence"] < min_confidence:
            continue
        for page, first, length in unit["pdf"]:
            if page in pages:
                units_on[page].append((unit["unit"], unit["kind"], range(first, first + length)))
    totals = Counter()
    per_page = {}
    conventions = defaultdict(Counter)
    anchor_misses = []
    for number, view in sorted(pages.items()):
        merged = defaultdict(list)
        kinds = {}
        for unit, kind, tokens in units_on.get(number, []):
            merged[unit].extend(tokens)
            kinds[unit] = kind
        rank = {t: i for i, t in enumerate(view.main)}
        placed = {}  # unit -> stream id
        for unit, tokens in merged.items():
            votes = Counter(view.stream_of.get(t) for t in tokens)
            stream = votes.most_common(1)[0][0]
            if stream is not None:
                placed[unit] = stream
                if len(votes) > 1:
                    totals["units_split_across_streams"] += 1
        main_stream = next((s for s, v in view.streams.items() if v["kind"] == "main"), None)
        main_units = sorted(u for u, s in placed.items() if s == main_stream)
        positions = [median(rank[t] for t in merged[u] if t in rank) for u in main_units]
        concordant, discordant = _pairs(positions)
        adjacent = sum(1 for a, b in zip(positions, positions[1:], strict=False) if a < b)
        totals["main_units"] += len(main_units)
        totals["main_concordant"] += concordant
        totals["main_discordant"] += discordant
        totals["main_adjacent_pairs"] += max(0, len(positions) - 1)
        totals["main_adjacent_agree"] += adjacent
        owner_of_main = {}
        for unit in main_units:
            for t in merged[unit]:
                if t in rank:
                    owner_of_main.setdefault(rank[t], unit)
        page_anchor = [0, 0]
        page_inner = [0, 0]
        for stream_id, info in view.streams.items():
            kind = info["kind"]
            members = sorted(u for u, s in placed.items() if s == stream_id)
            if not members or kind == "main":
                continue
            totals[f"units_in_{kind}"] += len(members)
            first = members[0]
            before = [u for u in main_units if u < first]
            after = [u for u in main_units if u > first]
            category = (
                "no_main_units"
                if not main_units
                else "before_main"
                if not before
                else "after_main"
                if not after
                else "interleaved"
            )
            conventions[kind][category] += 1
            if len(members) > 1:
                inner = [
                    median(
                        info["tokens"].index(t)
                        for t in merged[u]
                        if view.stream_of.get(t) == stream_id
                    )
                    for u in members
                ]
                c, d = _pairs(inner)
                page_inner[0] += c
                page_inner[1] += c + d
            if info["anchor"] is None:
                continue
            expected = before[-1] if before else None
            predicted = None
            for index in range(info["anchor"] - 1, -1, -1):
                if index in owner_of_main:
                    predicted = owner_of_main[index]
                    break
            correct = predicted == expected
            page_anchor[0] += correct
            page_anchor[1] += 1
            totals[f"anchors_{kind}"] += 1
            totals[f"anchors_{kind}_correct"] += correct
            if not correct:
                anchor_misses.append(
                    {
                        "page": number,
                        "kind": kind,
                        "expected_after_unit": expected,
                        "predicted_after_unit": predicted,
                        "first_unit": first,
                    }
                )
        totals["anchor_correct"] += page_anchor[0]
        totals["anchor_total"] += page_anchor[1]
        totals["inner_concordant"] += page_inner[0]
        totals["inner_pairs"] += page_inner[1]
        pairs = concordant + discordant
        per_page[number] = {
            "main_units": len(main_units),
            "main_pairwise": _ratio(concordant, pairs),
            "main_kendall_tau": _ratio(concordant - discordant, pairs),
            "main_adjacent": _ratio(adjacent, len(positions) - 1),
            "float_anchor": _ratio(*page_anchor),
            "float_inner_pairwise": _ratio(*page_inner),
        }
    pairs = totals["main_concordant"] + totals["main_discordant"]
    scored = [p for p in per_page.values() if p["main_pairwise"] is not None]
    kinds = sorted(
        {
            k[len("anchors_") :]
            for k in totals
            if k.startswith("anchors_") and not k.endswith("_correct")
        }
    )
    return {
        "pages": len(per_page),
        "main_flow": {
            "units": totals["main_units"],
            "pairwise_agreement_pooled": _ratio(totals["main_concordant"], pairs),
            "kendall_tau_pooled": _ratio(
                totals["main_concordant"] - totals["main_discordant"], pairs
            ),
            "adjacent_agreement_pooled": _ratio(
                totals["main_adjacent_agree"], totals["main_adjacent_pairs"]
            ),
            "pages_scored": len(scored),
            "pages_perfect": sum(p["main_pairwise"] == 1.0 for p in scored),
            "pairwise_agreement_page_mean": _ratio(
                sum(p["main_pairwise"] for p in scored), len(scored)
            ),
        },
        "float_anchors": {
            "anchored_streams": totals["anchor_total"],
            "accuracy": _ratio(totals["anchor_correct"], totals["anchor_total"]),
            "by_kind": {
                kind: {
                    "streams": totals[f"anchors_{kind}"],
                    "accuracy": _ratio(
                        totals[f"anchors_{kind}_correct"], totals[f"anchors_{kind}"]
                    ),
                }
                for kind in kinds
            },
        },
        "within_floats": {
            "pairs": totals["inner_pairs"],
            "pairwise_agreement": _ratio(totals["inner_concordant"], totals["inner_pairs"]),
        },
        "unit_streams": {
            k[len("units_in_") :]: v for k, v in sorted(totals.items()) if k.startswith("units_in_")
        },
        "units_split_across_streams": totals["units_split_across_streams"],
        "reference_conventions": {kind: dict(c) for kind, c in sorted(conventions.items())},
        "per_page": per_page,
        "anchor_misses": anchor_misses,
        "min_confidence": min_confidence,
    }
