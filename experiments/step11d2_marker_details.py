"""Explain every changed page of the rejected marker experiment."""

# ruff: noqa: E402
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "experiments")]
from step7_layouts import BOOKS
from step11d2_hidden import write
from step11d2_markers import BASE, CACHE_VARIANT, OUT, frozen_book, read

from book_core.lists.cache import BookListsResult, load_page
from book_core.lists.keys import book_fingerprint
from book_core.objects.analysis import verified_read


def main():
    result = {}
    for book in BOOKS:
        path = OUT / f"{book}.json"
        experiment = read(path)
        baseline = read(BASE / f"{book}.json")
        _, extractor, inputs, *_ = frozen_book(book)
        keys = [
            book_fingerprint(baseline["keys"]["lists"]),
            book_fingerprint(experiment["list_key_inputs"]),
        ]
        roots = [ROOT / ".cache/step11", CACHE_VARIANT]
        versions = [
            verified_read(root / "lists/book" / f"{key}.json", BookListsResult, key)
            for root, key in zip(roots, keys, strict=True)
        ]
        wanted = set(experiment["changed_pages"])
        rows = []
        for page in extractor.extract_pages(inputs.source):
            number = page.geometry.page
            if number not in wanted:
                continue
            layout, _ = inputs(page)
            lines = {
                line.id: "".join(page.store.spans[sid].raw_text for sid in line.span_ids)
                for line in layout.lines
            }
            pair = [
                load_page(version, number, root)
                for version, root in zip(versions, roots, strict=True)
            ]
            changed = {
                lid
                for lid in lines
                if next(u for u in pair[0].units if lid in u.line_ids)
                != next(u for u in pair[1].units if lid in u.line_ids)
            }
            rows.append(
                {
                    "page": number,
                    "changed_line_ids": sorted(changed),
                    "versions": [
                        {
                            "units": [
                                {
                                    "unit": u.model_dump(mode="json"),
                                    "text": [lines[lid] for lid in u.line_ids],
                                }
                                for u in value.units
                                if changed.intersection(u.line_ids)
                            ]
                        }
                        for value in pair
                    ],
                }
            )
        result[book] = {"pages": rows, "metric_changes": experiment["metric_changes"]}
    write(OUT / "page_details.json", result)
    print(json.dumps({book: [r["page"] for r in value["pages"]] for book, value in result.items()}))


if __name__ == "__main__":
    main()
