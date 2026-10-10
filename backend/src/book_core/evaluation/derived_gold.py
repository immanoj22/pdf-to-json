"""Provisional derived gold from a reference alignment (always human_approved = false).

The reference XML is evidence, not infallible truth: every derived label carries the alignment
confidence of its tokens and full provenance (source hashes, repairs, aligner version and
configuration, producer digest, and page token digests that pin the PDF token references).

PDF tokens are referenced as (page, ordinal): the ordinal indexes the page's retained native
tokens in extraction order. ``pages.json`` stores each page's token-id digest so a consumer can
verify that the references still point at the same tokens.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from book_core.caching import code_digest
from book_core.reference.aligner import AlignmentResult
from book_core.reference.pdf_tokens import PdfPage
from book_core.reference.xml_reader import ReferenceDocument

DERIVED_GOLD_VERSION = "derived-gold-1"


def _runs(positions: list[tuple[int, int]]) -> list[list[int]]:
    """[page, first ordinal, length] for consecutive ordinals on one page."""
    runs: list[list[int]] = []
    for page, ordinal in sorted(set(positions)):
        if runs and runs[-1][0] == page and runs[-1][1] + runs[-1][2] == ordinal:
            runs[-1][2] += 1
        else:
            runs.append([page, ordinal, 1])
    return runs


def derive_units(
    doc: ReferenceDocument, pages: Sequence[PdfPage], result: AlignmentResult
) -> list[dict]:
    """Text units in reference (XML) order with labels, PDF token runs and confidence."""
    numbers = result.pages
    tokens_of: dict[int, list[int]] = defaultdict(list)
    order: list[int] = []
    for i, unit in enumerate(doc.units):
        if unit not in tokens_of:
            order.append(unit)
        tokens_of[unit].append(i)
    extra: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for x, page, ordinal in result.extra_links:
        extra[x].append((numbers[page], ordinal))

    def unit_positions(unit: int) -> tuple[list[int], list[tuple[int, int]]]:
        aligned = [i for i in tokens_of[unit] if result.xml_page[i] >= 0]
        positions = [(numbers[result.xml_page[i]], result.xml_ordinal[i]) for i in aligned]
        positions += [pos for i in aligned for pos in extra.get(i, ())]
        return aligned, positions

    # A split link can put text of two adjacent units into one PDF token (glued in the PDF).
    owners: dict[tuple[int, int], set[int]] = defaultdict(set)
    for unit in order:
        for position in unit_positions(unit)[1]:
            owners[position].add(unit)
    units = []
    for sequence, unit in enumerate(order):
        indices = tokens_of[unit]
        aligned, positions = unit_positions(unit)
        element = doc.elements[unit]
        dialect = doc.dialect
        level, level_method = dialect.heading_level(unit, doc.elements)
        confidence = sum(result.xml_confidence[i] for i in indices) / len(indices)
        units.append(
            {
                "unit": sequence,
                "path": element.path,
                "element": element.name,
                "kind": dialect.element_kind(unit, doc.elements),
                "zone": dialect.zone_of(unit, doc.elements),
                "heading_level": level,
                "heading_level_method": level_method if level is not None else None,
                "list": dialect.list_membership(unit, doc.elements),
                "table": dialect.table_membership(unit, doc.elements),
                "xml_tokens": len(indices),
                "aligned_tokens": len(aligned),
                "confidence": round(confidence, 4),
                "methods": dict(Counter(result.xml_method[i] for i in aligned).most_common()),
                "unaligned_causes": dict(
                    Counter(result.xml_cause[i] for i in indices if result.xml_cause[i])
                ),
                "start": list(positions[0]) if aligned else None,
                "end": list(positions[len(aligned) - 1]) if aligned else None,
                "pdf": _runs(positions),
                "shared_pdf": sorted(
                    [list(position) for position in set(positions) if len(owners[position]) > 1]
                ),
            }
        )
    return units


def marker_label_of(doc: ReferenceDocument, marker, rule: Mapping | None) -> str:
    """The marker's own label, else one read from an attribute by a dialect data rule
    (``page_marker_label``: attribute and a pattern whose first group is the label)."""
    if marker.label or not rule:
        return marker.label
    value = doc.elements[marker.element].attributes.get(rule["attribute"], "")
    match = re.match(rule["pattern"], value)
    return match.group(1) if match else marker.label


def derive_markers(
    doc: ReferenceDocument,
    result: AlignmentResult,
    *,
    low_confidence: bool,
    label_rule: Mapping | None = None,
) -> list[dict]:
    segments = {segment["segment"]: segment for segment in result.segments}
    markers = []
    for number, marker in enumerate(doc.markers):
        segment = segments[marker.segment]
        confidence = min(1.0, segment["containment"] / result.config["placement_full"])
        markers.append(
            {
                "marker": number,
                "label": marker_label_of(doc, marker, label_rule),
                "path": doc.elements[marker.element].path,
                "reference_order": number,
                "pdf_page": segment["page"] if segment["count"] else None,
                "segment_tokens": segment["count"],
                "containment": segment["containment"],
                "located": segment["located"],
                "confidence": round(confidence * (0.5 if low_confidence else 1.0), 4),
                "low_confidence": low_confidence or not segment["located"],
                "excluded_from_gates": low_confidence,
            }
        )
    return markers


def _deterministic_gzip(text: str) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, filename="") as handle:
        handle.write(text.encode("utf-8"))
    return buffer.getvalue()


def write_derived_gold(
    directory: Path,
    *,
    book: str,
    split: str,
    notes: list[str],
    pdf_sha256: str,
    extractor: dict,
    doc: ReferenceDocument,
    pages: Sequence[PdfPage],
    result: AlignmentResult,
    dialects_digest: str,
    low_confidence_markers: bool = False,
    dialect_profile_digest: str | None = None,
    marker_label: Mapping | None = None,
) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    units = derive_units(doc, pages, result)
    markers = derive_markers(
        doc, result, low_confidence=low_confidence_markers, label_rule=marker_label
    )
    page_rows = [
        {"page": page.page, "tokens": len(page.tokens), "token_digest": page.digest}
        for page in pages
    ]
    files = {
        "units.jsonl.gz": _deterministic_gzip(
            "".join(json.dumps(unit, ensure_ascii=False, sort_keys=True) + "\n" for unit in units)
        ),
        "page_markers.json": (json.dumps(markers, ensure_ascii=False, indent=1) + "\n").encode(),
        "pages.json": (json.dumps(page_rows, indent=1) + "\n").encode(),
    }
    for name, data in files.items():
        (directory / name).write_bytes(data)
    zones = Counter()
    for unit in units:
        zones[unit["zone"]] += unit["aligned_tokens"]
    manifest = {
        "book": book,
        "split": split,
        "notes": notes,
        "human_approved": False,
        "status": "provisional derived gold; the reference XML is evidence, not infallible truth",
        "version": DERIVED_GOLD_VERSION,
        "provenance": {
            "pdf_sha256": pdf_sha256,
            "xml_sha256": doc.sha256,
            "dialect": doc.dialect.name,
            "dialect_profiles_sha256": dialects_digest,
            **(
                {"dialect_profile_sha256": dialect_profile_digest} if dialect_profile_digest else {}
            ),
            "in_memory_repairs": result.repairs,
            "extractor": extractor,
            "aligner_version": result.version,
            "aligner_config": result.config,
            "alignment_producer_sha256": code_digest("alignment"),
            "token_reference": (
                "[page, ordinal] over retained native tokens in extraction order; "
                "verify with pages.json token_digest"
            ),
        },
        "counts": {
            "units": len(units),
            "units_by_kind": dict(Counter(unit["kind"] for unit in units).most_common()),
            "aligned_tokens_by_zone": dict(zones.most_common()),
            "page_markers": len(markers),
            "pdf_pages": len(pages),
        },
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    (directory / "manifest.json").write_bytes(  # exact LF bytes on every platform
        (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    )
    return manifest
