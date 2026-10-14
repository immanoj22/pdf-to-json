"""Step 12: caption/credit link precision per rule, from the product linker on cached pages.

Runs ``figures.page`` linking (as the figures stage does, without rendering) over the cached
layout and final units of one book, tags each linked unit with the reference kind owning
most of its tokens (``caption`` = a reference figure caption or title, ``credit`` = a
reference credit unit, otherwise the derived-gold kind or ``unaligned``), and writes
precision per rule plus 20 seeded random links per rule with their text for manual review.

Usage: python step12_links.py --book spanish_us_history [--out links]
"""

# ruff: noqa: E402
import argparse
import json
import random
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import regex

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step12_reference as reference
from step12_evaluate import caption_paths
from step12_measure import gold_tokens, load

OUT = ROOT / "experiments/out/step12"
SAMPLE = 20
SEED = 12


def _norm(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(regex.findall(r"[\p{L}\p{N}]+", text))


LEADING_LABEL = regex.compile(r"^\s*\p{L}+\.?\s*[\p{N}.\p{L}]*\s*[:.]\s*")


def _in_captions(text, captions):
    body = _norm(LEADING_LABEL.sub("", text, count=1))[:60]
    return len(body) >= 8 and any(body in caption for caption in captions)


def run(book, out):
    from book_core.evaluation.furniture import token_lines
    from book_core.figures.page import (
        caption_openings,
        label_votes,
        link_numbered,
        link_page,
        numbered_candidates,
        require_numbers,
    )

    inv = reference.inventory(book)
    gold, pages, _, _ = load(book)
    owner, credit_units = gold_tokens(gold, inv)
    caption_units = set()
    for unit in gold.units:
        for path in caption_paths(inv):
            if unit["path"].startswith(path + "/") and (
                "/caption[" in unit["path"] or unit["element"] == "title"
            ):
                caption_units.add(unit["unit"])
                break
    # Evidence for the reference tag: is the link's text a reference figure title/caption?
    ref_captions = [_norm(text) for f in inv["figures"] for text in (*f["titles"], *f["captions"])]
    linked, votes, candidates, tags, texts = {}, Counter(), {}, defaultdict(Counter), {}
    extent, boxes, figure_box = {}, {}, {}
    openings = {}
    caption_owner = defaultdict(Counter)
    for page, layout, built in pages():
        number = page.geometry.page
        drafts, unlinked = link_page(layout, built)
        votes.update(label_votes(drafts, page.store, layout, built))
        candidates[number] = numbered_candidates(drafts, page.store, layout, built)
        openings[number] = caption_openings(drafts, page.store, layout, built)
        linked[number] = (drafts, unlinked)
        lines = {line.id: line for line in layout.lines}
        unit_of = {lid: u for u in built.units for lid in u.line_ids}
        for u in built.units:
            text = " ".join(
                "".join(page.store.spans[s].raw_text for s in lines[lid].span_ids)
                for lid in u.line_ids
            )
            texts[u.id] = unicodedata.normalize("NFKC", text)[:160]
            ub = [lines[lid].bbox for lid in u.line_ids]
            boxes[u.id] = [min(b.x0 for b in ub), min(b.y0 for b in ub),
                           max(b.x1 for b in ub), max(b.y1 for b in ub)]  # fmt: skip
        content = layout.content_bbox
        area = (content.x1 - content.x0) * (content.y1 - content.y0)
        for d in drafts:
            b = d.region.bbox
            extent[(number, d.region.id)] = round((b.x1 - b.x0) * (b.y1 - b.y0) / area, 3)
            figure_box[(number, d.region.id)] = [b.x0, b.y0, b.x1, b.y1]
        for ordinal, lid in enumerate(token_lines(page, layout)):
            if lid is None:
                continue
            unit = unit_of[lid].id
            hit = owner.get((number, ordinal))
            if hit is None:
                tags[unit]["unaligned"] += 1
                continue
            ref_unit, kind = hit
            if ref_unit in caption_units:
                caption_owner[ref_unit][unit] += 1
            tag = "caption" if ref_unit in caption_units else (
                "credit" if ref_unit in credit_units else kind)  # fmt: skip
            tags[unit][tag] += 1
    voted = sum(votes.values())
    labels = {w for w, c in votes.items() if w and c >= 3 and c >= 0.3 * voted}
    raw = {(n, d.region.id): list(d.captions) for n, (ds, _) in linked.items() for d in ds}
    for number, (drafts, unlinked) in linked.items():
        require_numbers(drafts, unlinked, openings[number], labels)
        link_numbered(drafts, unlinked, candidates[number], labels)
    covers = Counter()
    for owners in caption_owner.values():
        covers[owners.most_common(1)[0][0]] += 1
    rows = []
    for number, (drafts, _) in linked.items():
        for d in drafts:
            kept = {link.unit_id for link in d.captions}
            candidates_of = raw[(number, d.region.id)] + [
                link for link in d.captions if link not in raw[(number, d.region.id)]
            ]
            for role, links in (("caption", candidates_of), ("credit", d.credits)):
                for link in links:
                    tag_counts = tags.get(link.unit_id, Counter())
                    tag = tag_counts.most_common(1)[0][0] if tag_counts else "no tokens"
                    rows.append(
                        {
                            "rule": f"{role}: {link.rule}",
                            "role": role,
                            "page": number,
                            "unit": link.unit_id,
                            "review_required": link.review_required,
                            "figure_extent_share": extent[(number, d.region.id)],
                            "figures_on_page": len(drafts),
                            "figure_bbox": figure_box[(number, d.region.id)],
                            "unit_bbox": boxes[link.unit_id],
                            "reference_tag": tag,
                            "reference_tags": dict(tag_counts),
                            "correct_by_reference": tag == role,
                            "kept": role == "credit" or link.unit_id in kept,
                            "covers_reference_captions": covers.get(link.unit_id, 0),
                            "text_in_reference_caption": _in_captions(
                                texts[link.unit_id], ref_captions
                            ),
                            "text": texts[link.unit_id],
                        }
                    )
    figures = [
        {"page": n, "region": d.region.id, "bbox": figure_box[(n, d.region.id)]}
        for n, (ds, _) in linked.items()
        for d in ds
    ]
    (OUT / out).mkdir(parents=True, exist_ok=True)
    (OUT / out / f"{book}_rows.json").write_text(
        json.dumps(
            {"rows": rows, "figures": figures, "reference_captions": len(caption_owner)},
            ensure_ascii=False,
        ),
        "utf-8",
    )
    rows = [r for r in rows if r["kept"]]
    by_rule = defaultdict(list)
    for row in rows:
        by_rule[row["rule"]].append(row)
    summary, samples = {}, {}
    rng = random.Random(SEED)
    for rule, items in sorted(by_rule.items()):
        scorable = [r for r in items if r["reference_tag"] not in {"unaligned", "no tokens"}]
        summary[rule] = {
            "links": len(items),
            "scorable": len(scorable),
            "correct": sum(r["correct_by_reference"] for r in scorable),
            "precision_with_title_evidence": round(
                sum(r["correct_by_reference"] or r["text_in_reference_caption"] for r in items)
                / len(items),
                4,
            ),
            "precision_on_scorable": round(
                sum(r["correct_by_reference"] for r in scorable) / len(scorable), 4
            )
            if scorable
            else None,
            "reference_tags": dict(Counter(r["reference_tag"] for r in items).most_common()),
            "non_caption_tag_but_text_is_a_reference_caption": sum(
                r["role"] == "caption"
                and r["reference_tag"] != "caption"
                and r["text_in_reference_caption"]
                for r in items
            ),
        }
        samples[rule] = rng.sample(items, min(SAMPLE, len(items)))
    result = {"book": book, "caption_labels": sorted(labels), "rules": summary,
              "samples": samples}  # fmt: skip
    target = OUT / out / f"{book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    parser.add_argument("--out", default="links")
    args = parser.parse_args()
    run(args.book, args.out)
