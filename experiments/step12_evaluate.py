"""Step 12 Task 7: figure metrics of the figures stage against the reference, per book.

Reference figures are the figure containers plus page-specific images outside them; images
in metadata containers (DocBook ``info`` file references), inline media and files placed on
several pages (shared icons) are reported separately and not counted as figures.

- detection by page counts: per PDF page, min(ours, reference) matched; precision/recall;
  images per page agree / over / under;
- caption links: a reference caption (figure caption, or a figure title) is linked when the
  unit owning most of its aligned tokens is a caption of one of our figures on that page;
  where the reference image file name carries a page label and an index, the linked
  figure's name parts are compared with it (name agreement);
- credit links: reference credit units on pages that hold a reference image, linked when
  the owning unit is a credit of one of our figures on that page;
- figure-internal text: reference image-description tokens owned by units linked as
  internal text.

Usage: python step12_evaluate.py --book spanish_us_history [--out after]
"""

# ruff: noqa: E402
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step12_reference as reference
from step12_measure import gold_tokens, load

OUT = ROOT / "experiments/out/step12/evaluation"
# Evaluation only: how the registered references name their image files (label, index).
FILE_NAMES = (
    re.compile(r"/pg([^/_]+)_(\d+)\.\w+$"),
    re.compile(r"/p([^/_]+)_(\d+)\.\w+$"),
    re.compile(r"/page([^/-]+)-(\d+)\.\w+$"),
)


def file_label(name):
    for pattern in FILE_NAMES:
        match = pattern.search("/" + (name or "").replace("\\", "/").split("/")[-1])
        if match:
            return match.group(1), int(match.group(2))
    return None


def reference_view(book):
    inv = reference.inventory(book)
    uses = defaultdict(set)
    for figure in inv["figures"]:
        for name in figure["images"]:
            uses[name].add(figure["page"])
    for image in inv["loose_images"]:
        uses[image["file"]].add(image["page"])
    repeated = {name for name, pages in uses.items() if len(pages) > 1}
    per_page = Counter()
    for figure in inv["figures"]:
        if not figure["metadata"] and not (set(figure["images"]) <= repeated and figure["images"]):
            per_page[figure["page"]] += 1
    skipped = Counter()
    for image in inv["loose_images"]:
        if image["metadata"]:
            skipped["metadata_file_references"] += 1
        elif image["inline"]:
            skipped["inline_media"] += 1
        elif image["file"] in repeated:
            skipped["shared_icons"] += 1
        else:
            per_page[image["page"]] += 1
    return inv, per_page, skipped


def caption_paths(inv):
    """{reference unit path prefix: figure} for captions and figure titles."""
    return {figure["path"]: figure for figure in inv["figures"]}


def evaluate(book, figures_key=None):
    from step7_layouts import CACHE

    from book_core.evaluation.furniture import token_lines
    from book_core.figures.cache import load_page

    inv, ref_pages, skipped = reference_view(book)
    gold, pages, _, _ = load(book)
    run = ROOT / "experiments/out/step12" / os.environ.get("STEP12_OUT", "run")
    key = (
        figures_key
        or json.loads((run / f"performance/{book}.json").read_text("utf-8"))["run"]["cache_keys"][
            "figures"
        ]
    )
    owner, credit_units = gold_tokens(gold, inv)
    figure_by_path = caption_paths(inv)
    caption_units = {}
    for unit in gold.units:
        for path, figure in figure_by_path.items():
            if unit["path"].startswith(path + "/") and (
                "/caption[" in unit["path"] or unit["element"] == "title"
            ):
                caption_units[unit["unit"]] = figure
                break
    counts = Counter()
    per_page_rows = Counter()
    caption_votes = defaultdict(Counter)
    credit_votes = defaultdict(Counter)
    credit_pages = {}
    internal = Counter()
    names = Counter()
    linked_caption_figure = {}
    our_tags = defaultdict(Counter)  # our unit -> reference tag of its tokens
    link_rules = {}  # (role, our unit) -> rule
    for page, layout, built in pages():
        number = page.geometry.page
        page_figures = load_page(CACHE, key, number)
        records = page_figures.figures
        page_credit = {c.unit_id: len(c.proposed_figure_ids) for c in page_figures.page_credits}
        ours = len(records)
        ref = ref_pages.get(number, 0)
        counts["ours"] += ours
        counts["reference"] += ref
        counts["matched"] += min(ours, ref)
        per_page_rows["agree" if ours == ref else "over" if ours > ref else "under"] += bool(
            ours or ref
        )
        role = {}
        for record in records:
            for link in record.captions:
                role[link.unit_id] = ("caption", record)
                link_rules[("caption", link.unit_id)] = link.rule
            for link in record.credits:
                link_rules[("credit", link.unit_id)] = link.rule
            for link in record.internal_text:
                role[link.unit_id] = ("internal", record)
        credit_of = defaultdict(list)
        for record in records:
            for link in record.credits:
                credit_of[link.unit_id].append(record)
        unit_of = {lid: u for u in built.units for lid in u.line_ids}
        for ordinal, lid in enumerate(token_lines(page, layout)):
            if lid is None:
                continue
            hit = owner.get((number, ordinal))
            ours_unit = unit_of[lid].id
            if hit is None:
                our_tags[ours_unit]["unaligned"] += 1
                continue
            unit_id, kind = hit
            our_tags[ours_unit][
                "caption" if unit_id in caption_units else "credit" if unit_id in credit_units
                else kind
            ] += 1  # fmt: skip
            if unit_id in caption_units:
                caption_votes[unit_id][(number, ours_unit)] += 1
                if role.get(ours_unit, ("",))[0] == "caption":
                    linked_caption_figure[(unit_id, number, ours_unit)] = role[ours_unit][1]
            if unit_id in credit_units:
                credit_votes[unit_id][
                    (number, ours_unit, bool(credit_of.get(ours_unit)), page_credit.get(ours_unit))
                ] += 1
                credit_pages[unit_id] = number
            if kind == "image_description":
                internal["tokens"] += 1
                internal["linked_as_internal"] += role.get(ours_unit, ("",))[0] == "internal"
                internal["linked_as_caption"] += role.get(ours_unit, ("",))[0] == "caption"
    caption = Counter()
    for unit_id, votes in caption_votes.items():
        (number, ours_unit), _ = votes.most_common(1)[0]
        caption["scored"] += 1
        record = linked_caption_figure.get((unit_id, number, ours_unit))
        if record is None:
            continue
        caption["linked"] += 1
        figure = caption_units[unit_id]
        parsed = file_label(figure["images"][0]) if figure["images"] else None
        if parsed is not None:
            caption["named_reference"] += 1
            label, index = parsed
            same_label = (record.page_label or "").casefold() == label.casefold()
            caption["label_agrees"] += same_label
            caption["label_and_index_agree"] += same_label and record.anchor.reading_index == index
            names[(same_label, record.anchor.reading_index == index)] += 1
    credit = Counter()
    for unit_id, votes in credit_votes.items():
        if not ref_pages.get(credit_pages[unit_id]):
            credit["on_pages_without_reference_image"] += 1
            continue
        (_, _, linked, proposals), _ = votes.most_common(1)[0]
        credit["scored"] += 1
        credit["linked"] += linked
        credit["recorded_as_page_credit"] += proposals is not None
        credit["page_credit_with_one_proposed_figure"] += proposals == 1
    ratio = lambda a, b: round(a / b, 6) if b else None  # noqa: E731
    precision = defaultdict(Counter)
    for (link_role, unit), rule in link_rules.items():
        tags = our_tags.get(unit)
        tag = tags.most_common(1)[0][0] if tags else "no tokens"
        row = precision[f"{link_role}: {rule}"]
        row["links"] += 1
        row[f"reference {tag}"] += 1
        row["correct"] += tag == link_role
    link_precision = {
        rule: {**dict(row), "precision": ratio(row["correct"], row["links"])}
        for rule, row in sorted(precision.items())
    }
    return {
        "book": book,
        "figures_key": key,
        "reference_skipped_images": dict(skipped),
        "detection_by_page_counts": {
            "ours": counts["ours"],
            "reference": counts["reference"],
            "matched": counts["matched"],
            "precision": ratio(counts["matched"], counts["ours"]),
            "recall": ratio(counts["matched"], counts["reference"]),
        },
        "images_per_page": dict(per_page_rows),
        "captions": {
            **dict(caption),
            "link_accuracy": ratio(caption["linked"], caption["scored"]),
            "label_and_index_agreement": ratio(
                caption["label_and_index_agree"], caption["named_reference"]
            ),
        },
        "credits": {
            **dict(credit),
            "link_accuracy": ratio(credit["linked"], credit["scored"]),
            "page_credit_coverage": ratio(credit["recorded_as_page_credit"], credit["scored"]),
        },
        "link_precision_by_rule": link_precision,
        "figure_internal_text": {
            **dict(internal),
            "share_linked_as_internal": ratio(internal["linked_as_internal"], internal["tokens"]),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True, choices=sorted(reference.XML_KEYS))
    parser.add_argument("--out", default="after")
    parser.add_argument("--key")
    args = parser.parse_args()
    result = evaluate(args.book, args.key)
    target = OUT / args.out / f"{args.book}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
