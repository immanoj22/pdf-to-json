"""Read-only PDF navigation metadata and native block membership behind the extractor."""

from pathlib import Path

import pymupdf

from book_core.extraction.fingerprints import source_digest, stable_id


def _unchanged(source, before):
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during document metadata extraction")


def extract_navigation(extractor, source: Path) -> dict:
    before = source.stat()
    digest = source_digest(source)
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError("Encrypted sources require explicit decryption before extraction")
        definitions = document.get_page_labels()
        labels = [
            {"page": page.number + 1, "label": page.get_label(), "source": "pdf_page_labels"}
            for page in document
        ]
        line_geometry = {}
        native_blocks = []
        namespace = extractor._namespace(digest)
        for page in document:
            raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
            for block_index, block in enumerate(raw["blocks"]):
                if block["type"] != 0:
                    continue
                native_blocks.append(
                    {
                        "page": page.number + 1,
                        "block": block_index,
                        "line_ids": [
                            stable_id(namespace, "line", page.number + 1, block_index, index)
                            for index, _ in enumerate(block["lines"])
                        ],
                    }
                )
                for index, line in enumerate(block["lines"]):
                    line_id = stable_id(namespace, "line", page.number + 1, block_index, index)
                    line_geometry[line_id] = {
                        "direction": list(line["dir"]),
                        "writing_mode": "vertical" if line["wmode"] else "horizontal",
                    }
        bookmarks = []
        for index, (depth, title, page, destination) in enumerate(document.get_toc(simple=False)):
            internal = destination.get("kind") == pymupdf.LINK_GOTO
            target = page if internal and 0 < page <= document.page_count else None
            bookmarks.append(
                {
                    "id": stable_id(digest, "bookmark", index),
                    "title": title,
                    "depth": depth,
                    "target_page": target,
                    "action_kind": destination.get("kind"),
                    "uri": destination.get("uri"),
                    "file": destination.get("file"),
                    "named_destination": destination.get("nameddest"),
                }
            )
        result = {
            "source_sha256": digest,
            "extractor": extractor.identity.model_dump(mode="json"),
            "page_count": document.page_count,
            "page_label_definitions": definitions,
            "page_labels": labels,
            "bookmarks": bookmarks,
            "line_geometry": line_geometry,
            "native_blocks": native_blocks,
        }
    _unchanged(source, before)
    return result


def extract_native_blocks(extractor, source: Path) -> list[dict]:
    before = source.stat()
    digest = source_digest(source)
    namespace = extractor._namespace(digest)
    result = []
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError("Encrypted sources require explicit decryption before extraction")
        for page in document:
            raw = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT, sort=False)
            for block_index, block in enumerate(raw["blocks"]):
                if block["type"] != 0:
                    continue
                result.append(
                    {
                        "page": page.number + 1,
                        "block": block_index,
                        "line_ids": [
                            stable_id(namespace, "line", page.number + 1, block_index, index)
                            for index, _ in enumerate(block["lines"])
                        ],
                    }
                )
    _unchanged(source, before)
    return result
