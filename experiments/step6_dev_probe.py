"""Read-only book development probe over source-verified Step 6 cached native evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_core.document_analysis.navigation import analyze_navigation, resolve_title
from book_core.extraction.cache import payload_digest
from book_core.model.spans import ExtractedPage


def _payload(path: Path) -> dict:
    entry = json.loads(path.read_text("utf8"))
    payload = entry["payload"]
    if payload_digest(payload) != entry["payload_sha256"]:
        raise ValueError(f"Corrupt cache payload: {path}")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--native-directory", type=Path, required=True)
    parser.add_argument("--metadata-directory", type=Path, required=True)
    parser.add_argument("--first-pages", type=int, required=True)
    parser.add_argument("--sample-pages", type=int, nargs="*", default=[])
    args = parser.parse_args()
    if args.first_pages < 1:
        parser.error("--first-pages must be positive")
    metadata = None
    for path in sorted(args.metadata_directory.glob("*.json")):
        payload = _payload(path)
        if payload["source_sha256"] == args.source_sha256:
            if metadata is not None:
                raise ValueError("Multiple source metadata caches; select one directory explicitly")
            metadata = payload
    if metadata is None:
        raise ValueError("No metadata cache for the supplied source")
    pages = []
    for path in sorted(args.native_directory.glob("page_*.json"))[: args.first_pages]:
        page = ExtractedPage.model_validate(_payload(path))
        if page.source_sha256 != args.source_sha256:
            raise ValueError("Native page belongs to a different source")
        pages.append(page)
    if len(pages) != args.first_pages:
        raise ValueError("Requested development page range is incomplete")
    print(
        "METADATA",
        json.dumps(
            {
                "source_sha256": metadata["source_sha256"],
                "page_count": metadata["page_count"],
                "page_labels": len(metadata.get("page_labels", [])),
                "nonempty_labels": sum(
                    bool(row["label"]) for row in metadata.get("page_labels", [])
                ),
                "bookmarks": len(metadata.get("bookmarks", [])),
                "label_definitions": metadata.get("page_label_definitions", []),
            },
            ensure_ascii=False,
        ),
    )
    navigation = analyze_navigation(pages, metadata)
    print("TOC_PAGES", json.dumps(navigation["toc_pages"], ensure_ascii=False))
    print(
        "ENTRY_COUNTS",
        json.dumps(
            {
                str(page.geometry.page): sum(
                    entry["source_page"] == page.geometry.page
                    for entry in navigation["printed_entries"]
                )
                for page in pages
                if any(
                    entry["source_page"] == page.geometry.page
                    for entry in navigation["printed_entries"]
                )
            }
        ),
    )
    print(
        "TOTAL_ENTRIES",
        len(navigation["printed_entries"]),
        "RESOLVED",
        sum(bool(entry["target_pages"]) for entry in navigation["printed_entries"]),
    )
    for number in args.sample_pages:
        entries = [
            entry for entry in navigation["printed_entries"] if entry["source_page"] == number
        ]
        print(
            "SAMPLE_PAGE",
            number,
            json.dumps(
                [
                    {
                        "title": resolve_title(entry, pages)[:100],
                        "target_label": entry["target_label"],
                        "target_pages": entry["target_pages"],
                        "reference_side": entry["reference_side"],
                        "pairing_ambiguous": entry.get("pairing_ambiguous"),
                        "pairing_selected_by": entry.get("pairing_selected_by"),
                    }
                    for entry in entries[:5]
                ],
                ensure_ascii=False,
            ),
        )


if __name__ == "__main__":
    main()
