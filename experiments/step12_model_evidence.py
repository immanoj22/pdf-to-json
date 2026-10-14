"""Step 12: layout-model region classes as evidence for captions and figures (measurement).

Reads the cached Heron and PP-DocLayoutV3 detections (``step12_detect.py``; 72 dpi, 0.5
threshold, CPU) and the link harness rows (``step12_links.py --out links_v4``). Models are
evidence, never the sole decider. Variants per model (heron, pp), and fused (both agree /
either), against the final rule-only result:

Captions (each candidate unit; the model type is the detector region covering at least half
of the unit's box):
- reject: a kept link is dropped when the model calls the unit page header/footer, text,
  table or heading;
- confirm: a kept link is dropped unless the model calls it a caption;
- rescue: a candidate the rules left unlinked is linked when the model calls it a caption.
Precision counts a link correct when its tokens belong to a reference caption/title or its
text is a reference figure title/caption; recall counts reference captions owned by links.

Figures (a model figure supports one of ours when they overlap by at least half of the
smaller box):
- drop: our figures without model support are dropped;
- add: model figures that overlap none of ours are added;
Precision/recall by page counts against the reference view, and by printed label where the
reference names its image files by label (book 4).

Usage: python step12_model_evidence.py --book medical_anatomy
"""

# ruff: noqa: E402
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from reference_paths import reference_path
from step7_layouts import BOOKS
from step12_detect import CACHE, detectors
from step12_evaluate import file_label, reference_view
from step12_reference import inventory

from book_core.cache_store import read_json
from book_core.detection.cache import detect_page
from book_core.extraction.pymupdf_backend import PyMuPDFExtractor

OUT = ROOT / "experiments/out/step12/model_evidence"
NOT_CAPTION = {"header_footer_candidate", "main_text", "table_candidate", "heading_candidate"}


def overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def box(region):
    b = region.bbox
    return [b.x0, b.y0, b.x1, b.y1]


def covering_type(unit_box, regions):
    best = None
    for region in regions:
        share = overlap(unit_box, box(region)) / max(1e-6, area(unit_box))
        if share >= 0.5 and (best is None or share > best[0]):
            best = (share, region.type)
    return best[1] if best else None


def caption_variants(rows, total, types):
    """types: {(page, unit): {model: type}}."""

    def score(selected):
        correct = [
            r for r in selected if r["correct_by_reference"] or r["text_in_reference_caption"]
        ]
        return {
            "links": len(selected),
            "precision": round(len(correct) / len(selected), 4) if selected else None,
            "recall": round(sum(r["covers_reference_captions"] for r in correct) / total, 4)
            if total
            else None,
        }

    captions = [r for r in rows if r["role"] == "caption"]
    result = {"rules_only": score([r for r in captions if r["kept"]])}

    def says(row, model, kinds):
        found = types[(row["page"], row["unit"])]
        if model == "both":
            return all(found[m] in kinds for m in ("heron", "pp"))
        if model == "either":
            return any(found[m] in kinds for m in ("heron", "pp"))
        return found[model] in kinds

    for model in ("heron", "pp", "both", "either"):
        caption = {"caption_candidate"}
        result[f"{model}: reject"] = score(
            [r for r in captions if r["kept"] and not says(r, model, NOT_CAPTION)]
        )
        result[f"{model}: confirm"] = score(
            [r for r in captions if r["kept"] and says(r, model, caption)]
        )
        result[f"{model}: rescue"] = score(
            [r for r in captions if r["kept"] or says(r, model, caption)]
        )
    return result


def figure_variants(book, figures, model_figures, labels):
    _, ref_pages, _ = reference_view(book)
    ref_labels = Counter()
    for figure in inventory(book)["figures"]:
        for name in figure["images"]:
            parsed = file_label(name)
            if parsed:
                ref_labels[parsed[0].casefold()] += 1
    ours = defaultdict(list)
    for f in figures:
        ours[f["page"]].append(f["bbox"])

    def supported(page, b, model):
        found = model_figures[page]

        def hit(m):
            return any(overlap(b, x) >= 0.5 * min(area(b), area(x)) for x in found[m])

        if model == "both":
            return hit("heron") and hit("pp")
        if model == "either":
            return hit("heron") or hit("pp")
        return hit(model)

    def model_only(page, model):
        found = model_figures[page]
        boxes = found["pp"] if model in {"pp", "both"} else found["heron"]
        if model == "either":
            boxes = found["heron"] + [
                x for x in found["pp"]
                if not any(overlap(x, y) >= 0.5 * min(area(x), area(y)) for y in found["heron"])
            ]  # fmt: skip
        extra = []
        for x in boxes:
            if any(overlap(x, b) >= 0.5 * min(area(x), area(b)) for b in ours[page]):
                continue
            if model == "both" and not any(
                overlap(x, y) >= 0.5 * min(area(x), area(y)) for y in found["heron"]
            ):
                continue
            extra.append(x)
        return extra

    def score(counts):
        matched = sum(
            min(counts.get(p, 0), ref_pages.get(p, 0)) for p in set(counts) | set(ref_pages)
        )
        ours_total, ref_total = sum(counts.values()), sum(ref_pages.values())
        row = {
            "ours": ours_total,
            "precision": round(matched / ours_total, 4) if ours_total else None,
            "recall": round(matched / ref_total, 4) if ref_total else None,
        }
        if ref_labels:
            by_label = Counter()
            for page, count in counts.items():
                if labels.get(page):
                    by_label[labels[page].casefold()] += count
            hits = sum(min(by_label[k], ref_labels[k]) for k in set(by_label) | set(ref_labels))
            row["label_precision"] = round(hits / sum(by_label.values()), 4)
            row["label_recall"] = round(hits / sum(ref_labels.values()), 4)
        return row

    pages = set(model_figures)
    base = {p: len(ours[p]) for p in pages}
    result = {"rules_only": score(base)}

    def matched(counts, by_label):
        if by_label:
            got = Counter()
            for page, count in counts.items():
                if labels.get(page):
                    got[labels[page].casefold()] += count
            return sum(min(got[k], ref_labels[k]) for k in set(got) | set(ref_labels))
        return sum(min(counts.get(p, 0), ref_pages.get(p, 0)) for p in set(counts) | set(ref_pages))

    flags = {}
    for rule in ("neither", "not_both", "heron", "pp"):
        unflagged = {}
        flagged = 0
        for p in pages:
            keep = 0
            for b in ours[p]:
                support = {m: supported(p, b, m) for m in ("heron", "pp")}
                if rule == "neither":
                    bad = not any(support.values())
                elif rule == "not_both":
                    bad = not all(support.values())
                else:
                    bad = not support[rule]
                flagged += bad
                keep += not bad
            unflagged[p] = keep
        row = {"flagged": flagged, "unflagged": sum(unflagged.values())}
        for name, by_label in (("page", False), ("label", True)):
            if by_label and not ref_labels:
                continue
            total, kept = matched(base, by_label), matched(unflagged, by_label)
            row[f"precision_unflagged_{name}"] = round(kept / max(1, row["unflagged"]), 4)
            row[f"precision_flagged_{name}"] = (
                round((total - kept) / flagged, 4) if flagged else None
            )
        flags[rule] = row
    result["model_disagrees_flag"] = flags
    # Model-only figures found by both models: their own (marginal) precision.
    extra = {p: len(model_only(p, "both")) for p in pages}
    added = {p: base[p] + extra[p] for p in pages}
    count = sum(extra.values())
    row = {"count": count, "pages": sorted(p for p, n in extra.items() if n)[:40]}
    for name, by_label in (("page", False), ("label", True)):
        if by_label and not ref_labels:
            continue
        gain = matched(added, by_label) - matched(base, by_label)
        row[f"precision_{name}"] = round(gain / count, 4) if count else None
        row[f"reference_figures_gained_{name}"] = gain
    result["model_only_both"] = row
    for model in ("heron", "pp", "both", "either"):
        drop = {p: sum(supported(p, b, model) for b in ours[p]) for p in pages}
        add = {p: base[p] + len(model_only(p, model)) for p in pages}
        result[f"{model}: drop unsupported"] = score(drop)
        result[f"{model}: add model-only"] = score(add)
    return result


def main(book):
    data = json.loads(
        (ROOT / f"experiments/out/step12/links_v4/{book}_rows.json").read_text("utf-8")
    )
    run = json.loads(
        (
            ROOT
            / "experiments/out/step12"
            / os.environ.get("STEP12_OUT", "run")
            / f"performance/{book}.json"
        ).read_text("utf-8")
    )["run"]
    output = Path(run["output"])
    markers = read_json(output / "book.json.gz")["furniture"]["markers"]
    labels = {m["page"]: m["label"] for m in markers}
    source = reference_path(BOOKS[book][0])
    extractor = PyMuPDFExtractor("cpu")
    models = dict(zip(("heron", "pp"), detectors(), strict=True))
    detected = {}
    for page in range(1, run["pages"] + 1):
        detected[page] = {
            name: detect_page(source, page, extractor, detector, CACHE).regions
            for name, detector in models.items()
        }
    types = {
        (r["page"], r["unit"]): {
            name: covering_type(r["unit_bbox"], detected[r["page"]][name]) for name in models
        }
        for r in data["rows"]
    }
    model_figures = {
        page: {name: [box(x) for x in regions if x.type == "figure"] for name, regions in d.items()}
        for page, d in detected.items()
    }
    captions = caption_variants(data["rows"], data["reference_captions"], types)
    type_mix = Counter(
        (r["kept"], r["correct_by_reference"] or r["text_in_reference_caption"],
         types[(r["page"], r["unit"])]["pp"], types[(r["page"], r["unit"])]["heron"])
        for r in data["rows"] if r["role"] == "caption"
    )  # fmt: skip
    figures = figure_variants(book, data["figures"], model_figures, labels)
    result = {
        "book": book,
        "captions": captions,
        "caption_type_mix": [
            {"kept": k, "correct": c, "pp": p, "heron": h, "n": n}
            for (k, c, p, h), n in type_mix.most_common()
        ],
        "figures": figures,
        "model_figure_regions": {
            name: sum(len(v[name]) for v in model_figures.values()) for name in models
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{book}.json").write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "caption_type_mix"}, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--book", required=True)
    main(parser.parse_args().book)
