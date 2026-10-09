"""Score one pipeline stage's output against provisional derived gold, book by book.

Rules: each stage is scored separately; results are reported per book and never combined into
an overall score; hold-out books are excluded unless the caller explicitly includes them, and
every result row carries its book's split. Only metrics that need no new pipeline stage are
implemented. The others are documented stubs that raise ``NotImplementedError`` until the
stage that produces their input exists.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from book_core.ingestion.provisional import provision_page
from book_core.ledger.records import NodeAssignment
from book_core.model.spans import ExtractedPage
from book_core.reference.pdf_tokens import page_tokens


@dataclass(frozen=True)
class DerivedGold:
    book: str
    split: str
    manifest: dict
    units: list[dict]
    markers: list[dict]
    pages: list[dict]

    @classmethod
    def load(cls, directory: Path) -> DerivedGold:
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
        for name, digest in manifest["files"].items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"{directory / name} does not match its manifest digest")
        if manifest["human_approved"] is not False:
            raise ValueError("Derived gold must stay human_approved = false")
        units_text = gzip.decompress((directory / "units.jsonl.gz").read_bytes()).decode("utf-8")
        return cls(
            book=manifest["book"],
            split=manifest["split"],
            manifest=manifest,
            units=[json.loads(line) for line in units_text.splitlines()],
            markers=json.loads((directory / "page_markers.json").read_text("utf-8")),
            pages=json.loads((directory / "pages.json").read_text("utf-8")),
        )


@dataclass(frozen=True)
class StageOutput:
    """Owner of each retained PDF token (by page and ordinal) in one stage's output.

    ``None`` means the stage did not place that token in any node.
    """

    stage: str
    book: str
    owners: Mapping[int, list[str | None]]
    token_digests: Mapping[int, str]


def ingestion_output(book: str, pages: Iterable[ExtractedPage]) -> StageOutput:
    """The current provisional-ingestion stage: native line runs owned through the ledger."""
    owners: dict[int, list[str | None]] = {}
    digests: dict[int, str] = {}
    for page in pages:
        _, ledger = provision_page(page)
        node_of = {
            item.token_id: item.node_id
            for item in ledger.assignments
            if isinstance(item, NodeAssignment)
        }
        tokens = page_tokens(page)
        owners[tokens.page] = [node_of.get(token.id) for token in tokens.tokens]
        digests[tokens.page] = tokens.digest
    return StageOutput("ingestion", book, owners, digests)


def _check_tokens(gold: DerivedGold, output: StageOutput) -> list[int]:
    """Pages whose token sequence differs from the gold's references (scored as unknown)."""
    return [
        row["page"]
        for row in gold.pages
        if output.token_digests.get(row["page"]) not in (None, row["token_digest"])
    ]


def _owned(output: StageOutput, page: int, ordinal: int) -> bool:
    owners = output.owners.get(page)
    return owners is not None and ordinal < len(owners) and owners[ordinal] is not None


def text_unit_coverage(gold: DerivedGold, output: StageOutput, min_confidence: float = 0.0):
    """Share of each reference unit's aligned PDF tokens that the stage places in a node."""
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for unit in gold.units:
        if not unit["pdf"] or unit["confidence"] < min_confidence:
            continue
        positions = [(p, o + d) for p, o, n in unit["pdf"] for d in range(n)]
        owned = sum(1 for p, o in positions if _owned(output, p, o))
        row = by_kind[unit["kind"]]
        row[0] += 1
        row[1] += owned == len(positions)
        row[2] += owned
        row[3] += len(positions)
    units = sum(row[0] for row in by_kind.values())
    return {
        "units": units,
        "units_fully_covered": sum(row[1] for row in by_kind.values()),
        "token_coverage": round(
            sum(r[2] for r in by_kind.values()) / max(sum(r[3] for r in by_kind.values()), 1), 6
        ),
        "by_kind": {
            kind: {"units": r[0], "fully_covered": r[1], "token_coverage": round(r[2] / r[3], 6)}
            for kind, r in sorted(by_kind.items())
            if r[3]
        },
        "min_confidence": min_confidence,
    }


def zone_coverage(gold: DerivedGold, output: StageOutput):
    """Per front/body/rear/metadata zone: share of aligned PDF tokens placed in a node."""
    zones: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for unit in gold.units:
        for page, ordinal, length in unit["pdf"]:
            for d in range(length):
                zones[unit["zone"]][0] += _owned(output, page, ordinal + d)
                zones[unit["zone"]][1] += 1
    return {
        zone: {"tokens": total, "covered": round(owned / total, 6)}
        for zone, (owned, total) in sorted(zones.items())
        if total
    }


def page_marker_coverage(gold: DerivedGold, output: StageOutput, include_excluded=False):
    """Share of reference page markers whose placed PDF page exists in the stage output."""
    markers = [m for m in gold.markers if include_excluded or not m["excluded_from_gates"]]
    placed = [m for m in markers if m["pdf_page"] is not None]
    present = [m for m in placed if m["pdf_page"] in output.owners]
    return {
        "markers": len(markers),
        "placed": len(placed),
        "page_present": len(present),
        "coverage": round(len(present) / len(placed), 6) if placed else None,
        "excluded_from_gates": sum(1 for m in gold.markers if m["excluded_from_gates"]),
    }


def paragraph_boundary_scores(gold: DerivedGold, output: StageOutput):
    """Stub: needs a paragraph stage (Step 7+) emitting paragraph nodes with token ranges."""
    raise NotImplementedError("Requires a paragraph-building stage")


def heading_level_scores(gold: DerivedGold, output: StageOutput):
    """Stub: needs a heading classification stage with levels (not font size alone)."""
    raise NotImplementedError("Requires a heading classification stage")


def list_table_membership_scores(gold: DerivedGold, output: StageOutput):
    """Stub: needs list and table structure stages."""
    raise NotImplementedError("Requires list and table structure stages")


def reading_order_scores(gold: DerivedGold, output: StageOutput):
    """Stub: needs a semantic reading-order stage; compares unit order with reference order."""
    raise NotImplementedError("Requires a semantic reading-order stage")


METRICS = {
    "text_unit_coverage": text_unit_coverage,
    "zone_coverage": zone_coverage,
    "page_marker_coverage": page_marker_coverage,
}
STUBS = {
    "paragraph_boundaries": paragraph_boundary_scores,
    "heading_levels": heading_level_scores,
    "list_table_membership": list_table_membership_scores,
    "reading_order": reading_order_scores,
}


def evaluate(
    golds: Iterable[DerivedGold],
    outputs: Mapping[str, StageOutput],
    *,
    include_holdout: bool = False,
) -> dict:
    """One stage, per book, no overall score. Hold-out books need an explicit opt-in."""
    stages = {output.stage for output in outputs.values()}
    if len(stages) > 1:
        raise ValueError("Score one stage at a time")
    books = {}
    for gold in golds:
        if gold.split == "holdout" and not include_holdout:
            books[gold.book] = {"split": gold.split, "skipped": "hold-out not requested"}
            continue
        output = outputs.get(gold.book)
        if output is None:
            books[gold.book] = {"split": gold.split, "skipped": "no stage output"}
            continue
        mismatched = _check_tokens(gold, output)
        if mismatched:
            raise ValueError(f"{gold.book}: token references changed on pages {mismatched[:10]}")
        books[gold.book] = {
            "split": gold.split,
            "notes": gold.manifest["notes"],
            **{name: metric(gold, output) for name, metric in METRICS.items()},
            "not_implemented": sorted(STUBS),
        }
    return {"stage": next(iter(stages), None), "books": books, "overall": None}
