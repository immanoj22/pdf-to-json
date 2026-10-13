"""Step 11d continuation: page-level audit of layout and furniture differences per variant.

Layout pages are compared after removing only the fields this step adds (span visibility
evidence and span review flags). Any other layout difference is listed. Furniture pages
are compared field by field and summarised by changed path pattern.
"""

# ruff: noqa: E402
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
import step11c_identity as identity
from step11d2_hidden import write
from step11d2_run import BASE, CACHE, CACHE8, differences, read

from book_core.furniture.models import PageFurniture
from book_core.layout.models import PageLayout
from book_core.objects.analysis import verified_read

VARIANTS = ("hidden", "flags", "combined")


def strip_added(layout):
    data = identity.semantic(layout.model_dump(mode="json"))
    data.pop("visibility_evidence", None)
    data["review_flags"] = [f for f in data["review_flags"] if f["subject_kind"] != "span"]
    return data


def pattern(path):
    return re.sub(r"/\d+", "/#", path)


def main(book, variant):
    out = ROOT / "experiments/out/step11d2" / variant
    versions = [read(BASE / f"{book}.json"), read(out / f"after/{book}.json")]
    keys = [v["keys"] for v in versions]
    layout_pages, added_counts, furniture_pages = {}, Counter(), {}
    furniture_patterns = Counter()
    for number in versions[0]["pages"]:
        layouts = [
            verified_read(
                CACHE / "layout" / k["layout"] / f"{number}.json", PageLayout, k["layout"]
            )
            for k in keys
        ]
        after = layouts[1]
        added_counts["pages_with_evidence"] += bool(after.visibility_evidence)
        for proof in after.visibility_evidence:
            added_counts[f"decision_{proof.decision}"] += 1
        added_counts["span_review_flags"] += sum(
            f.subject_kind == "span" for f in after.review_flags
        )
        diff = differences(*[strip_added(x) for x in layouts])
        if diff:
            layout_pages[number] = sorted({pattern(d["path"]) for d in diff})
        furniture = [
            verified_read(
                CACHE8 / "furniture/page" / k["furniture"] / f"{number}.json",
                PageFurniture,
                k["furniture"],
            )
            for k in keys
        ]
        diff = differences(*[identity.semantic(f.model_dump(mode="json")) for f in furniture])
        if diff:
            furniture_pages[number] = diff
            furniture_patterns.update({pattern(d["path"]) for d in diff})
    result = {
        "book": book,
        "variant": variant,
        "pages": len(versions[0]["pages"]),
        "added_layout_fields": dict(added_counts),
        "layout_pages_with_other_differences": layout_pages,
        "furniture_changed_pages": sorted(int(n) for n in furniture_pages),
        "furniture_changed_path_patterns": dict(furniture_patterns.most_common()),
        "furniture_differences": furniture_pages,
    }
    write(out / f"variant_audit_{book}.json", result)
    print(
        book,
        variant,
        "layout pages with non-evidence differences:",
        sorted(int(n) for n in layout_pages),
        "| furniture pages:",
        len(furniture_pages),
        dict(furniture_patterns.most_common(8)),
        dict(added_counts),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", choices=identity.BOOKS, required=True)
    parser.add_argument("--variant", choices=VARIANTS, default="hidden")
    args = parser.parse_args()
    main(args.book, args.variant)
