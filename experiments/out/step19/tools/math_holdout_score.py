"""Step 19: math hold-out MathML scores, measured as Step 18 registered them (M09).

Same frozen algorithms and the same preselected reference as Step 18's deferred tools
(experiments/out/step18/orchestration_tools/math_reference_alignment.py and
math_reference_metrics.py), with Step 19 routing:

1. Reference math is derived by the frozen Step 13 reader (``step13_gold.main``) from a
   byte-identical view of the sealed Algebra and Trigonometry 1e collection, located on this
   run's own native extraction. ``verified`` is the automatic glyph-count eligibility
   predicate, never a human check.
2. The run's archived equation regions and MathML records are scored by the frozen
   ``step13c_dev.evaluate`` (strict and expression level; per path, presentation and review
   status), with the frozen boundary classes (``step13_boundaries.classify``).

Writes new evidence only (refuses to overwrite). The reference repository is read only.

usage: python math_holdout_score.py TAG     (run from the repository root)
"""

import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
BOOK = "math_holdout"
COMMIT = "8322d84e2df67cad5ba6616fd306eb22427a50c4"


def write_new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=1, default=str)
        stream.write("\n")


def reference_view(reference_root, view, frozen):
    """Copy the one preselected collection and its modules, byte for byte."""
    from step19_run import sha

    collection = reference_root / "collections/algebra-and-trigonometry.collection.xml"
    assert collection.is_file(), "The preselected sealed collection is missing"
    spec = frozen.math_gold.profile_data()["dialects"][0]["collection"]
    tree = ET.parse(collection).getroot()
    modules = sorted({
        node.get(spec["module_attribute"]) for node in tree.iter()
        if node.tag == "{" + spec["namespace"] + "}" + spec["module_element"]
    })  # fmt: skip
    (view / "collections").mkdir(parents=True, exist_ok=False)
    shutil.copy2(collection, view / "collections" / collection.name)
    copied = {"collections/" + collection.name: sha(collection)}
    for module in modules:
        relative = spec["module_path"].format(module=module)
        destination = view / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reference_root / relative, destination)
        assert sha(reference_root / relative) == sha(destination)
        copied[relative] = sha(destination)
    return {"selected_collection": collection.name, "module_count": len(modules),
            "files_sha256": copied, "source_reference_modified": False}  # fmt: skip


def main():
    tag = sys.argv[1]
    import step13_gold as frozen
    import step13c_dev
    from reference_paths import reference_path
    from step13_boundaries import classify
    from step13c_evaluate import archive_records, summary
    from step19_run import OUT

    performance = json.loads((OUT / tag / "performance" / f"{BOOK}.json").read_text("utf-8"))
    assert performance["outcome"] == "completed", "Score only a completed run"
    run, cache = performance["run"], Path(performance["cache"])
    evidence = OUT / tag / "math"
    gold_dir = evidence / "reference_math"
    assert not gold_dir.exists(), "Preserve existing derivation evidence"
    work = ROOT / ".cache/s19/math_reference_work" / tag
    view = work / "selected_reference"
    receipt = reference_view(reference_path("math_holdout_cnxml"), view, frozen)
    write_new(evidence / "input_view_receipt.json", {**receipt, "reference_commit": COMMIT})

    frozen.reference_path = lambda key: view if key == "math_holdout_cnxml" else reference_path(key)
    frozen.MATH_BOOK = BOOK
    frozen.BOOKS = {BOOK: ("math_holdout_pdf", "holdout")}
    frozen.CNXML = {BOOK: "math_holdout_cnxml"}
    frozen.CACHE, frozen.GOLD, frozen.WORK = cache, gold_dir, work
    frozen.OUT = evidence / "reference_coverage"
    frozen.main("registered", native_key=run["cache_keys"]["native"])
    manifest = json.loads((gold_dir / "manifest.json").read_text("utf-8"))

    step13c_dev.GOLD = gold_dir
    rows, _ = step13c_dev.gold()
    regions_by_page, records = archive_records(run)
    pages = range(1, run["pages"] + 1)
    values = step13c_dev.evaluate(regions_by_page, records, pages)
    values.pop("rows", None)
    located = defaultdict(list)
    for row in rows:
        if row["status"] == "located":
            located[row["page"]].append(row)
    boundary = Counter()
    for number, page_rows in located.items():
        objects = {o for row in page_rows for o in row["object_ids"]}
        for row in page_rows:
            if row["verified"]:
                label, _ = classify(row, regions_by_page.get(number, []),
                                    objects - set(row["object_ids"]))  # fmt: skip
                boundary[label] += 1
    write_new(evidence / "math_scores.json", {
        "book_id": BOOK, "tag": tag, "label": performance.get("label"),
        "reference_counts": manifest["counts"],
        "reference_by_status": dict(Counter(r["status"] for r in rows)),
        "automatically_geometry_eligible_located": sum(boundary.values()),
        "boundary_counts": dict(boundary),
        "output": summary(list(records.values())),
        "output_regions": sum(map(len, regions_by_page.values())),
        "frozen_mathml_scores": values,
        "coverage_note": "Scores are conditional on frozen reference location and the "
        "automatic glyph-count eligibility predicate; 'verified' is not a human check.",
        "human_approved": False,
    })  # fmt: skip
    print(json.dumps({k: v for k, v in values.items() if k != "examples"}, default=str)[:4000])


if __name__ == "__main__":
    main()
