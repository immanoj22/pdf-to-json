"""Furniture stage entry points with source/configuration/producer-keyed caches.

The book decision (roles for every line, page markers, folio runs, slot groups) is cached per
book; each page's PageFurniture (roles, marker, rebuilt order) per page under its book key.
The key components are explicit (``furniture.keys``): furniture and reading-order producer
digests, layout and order fingerprints, the Step 6 evidence digest, settings, configuration
and FURNITURE_VERSION. They are recorded on the decision for audit.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from book_core.caching import assert_producer_unchanged, code_digest
from book_core.furniture.apply import FURNITURE_VERSION, apply_page, line_roles, page_marker
from book_core.furniture.classify import Classifier, FurnitureConfig, config_dict
from book_core.furniture.features import page_features
from book_core.furniture.keys import book_fingerprint, book_key_components, furniture_code_digest
from book_core.furniture.models import (
    BookFurniture,
    FolioRun,
    LineRole,
    PageFurniture,
)
from book_core.furniture.sequence import SequenceConfig
from book_core.model.common import CoreModel, Provenance
from book_core.objects.analysis import atomic_write, verified_read
from book_core.settings import Settings

LOADED_DIGEST = furniture_code_digest()
LOADED_ORDER_DIGEST = code_digest("reading_order")


def assert_unchanged():
    assert_producer_unchanged("reading_order", LOADED_ORDER_DIGEST)
    if furniture_code_digest() != LOADED_DIGEST:
        raise RuntimeError("furniture producer source changed; restart the worker")


class BookDecisions(CoreModel):
    book: BookFurniture
    roles: dict[int, list[LineRole]] = Field(default_factory=dict)


def metadata_labels(metadata):
    """{physical page: label} from extractor PDF page-label metadata (empty labels dropped)."""
    return {row["page"]: row["label"] for row in metadata.get("page_labels", []) if row["label"]}


def book_key(inputs, metadata, settings, config, sequence):
    """(key, components) of one book decision; see ``furniture.keys``."""
    components = book_key_components(
        furniture=LOADED_DIGEST,
        layout_key=inputs.layout_key,
        order_key=inputs.order_key,
        vocabulary=inputs.vocabulary,
        metadata=metadata,
        settings=settings,
        config=config_dict(config, sequence),
        version=FURNITURE_VERSION,
    )
    return book_fingerprint(components), components


def decide_book(features, labels, source_sha256, config=None, sequence=None, resolved="cpu"):
    """Whole-book furniture decisions from per-page features (``furniture.features``)."""
    config, sequence = config or FurnitureConfig(), sequence or SequenceConfig()
    classifier = Classifier(features, labels, config, sequence).run()
    decisions = {d.page: d for d in classifier.labels}
    markers = [
        page_marker(decisions[page], classifier.folio_lines.get(page, []))
        for page in classifier.pages
    ]
    inferred = {}
    for d in classifier.labels:
        if d.run is not None and d.source == "inferred":
            inferred.setdefault(d.run, []).append(d.page)
    runs = []
    for run in classifier.runs:
        styles = classifier.folio_style.get(run.index)
        style = list(styles.most_common(1)[0][0][1]) if styles else []
        runs.append(
            FolioRun(
                index=run.index,
                kind=run.series[0],
                prefix=run.series[1],
                uppercase=run.series[2],
                offset=run.offset,
                first_page=run.first,
                last_page=run.last,
                first_label=run.label(run.first),
                last_label=run.label(run.last),
                printed_pages=len(run.printed),
                inferred_pages=inferred.get(run.index, []),
                style=style,
            )
        )
    roles = {page: {} for page in classifier.pages}
    for (page, line_id), decision in classifier.roles.items():
        roles[page][line_id] = decision
    for page, rows in features.items():
        if set(roles[page]) != {r.line_id for r in rows}:
            raise ValueError(f"Page {page}: not every line received a role")
    book = BookFurniture(
        source_sha256=source_sha256,
        furniture_version=FURNITURE_VERSION,
        pages=len(classifier.pages),
        body_style=list(classifier.body or []),
        runs=runs,
        groups=classifier.groups,
        markers=markers,
        metadata_comparison=classifier.metadata_comparison,
        config=config_dict(config, sequence),
        provenance=Provenance(
            source_sha256=source_sha256,
            engine="book_core.furniture",
            engine_version=FURNITURE_VERSION,
            method="derived",
            resolved_device=resolved,
        ),
    )
    return BookDecisions(book=book, roles={page: line_roles(rows) for page, rows in roles.items()})


def load_book_furniture(inputs, metadata, cache_dir, config=None, sequence=None, settings=None):
    """The cached book decision and its key, or (None, key): never computes (no new run)."""
    config, sequence = config or FurnitureConfig(), sequence or SequenceConfig()
    key, _ = book_key(inputs, metadata, settings or Settings(), config, sequence)
    path = Path(cache_dir) / "furniture" / "book" / f"{key}.json"
    if not path.exists():
        return None, key
    decisions = verified_read(path, BookDecisions, key)
    if decisions.book.source_sha256 != inputs.digest:
        raise ValueError("Furniture cache belongs to another source")
    return decisions, key


def analyze_book_furniture(
    pages, inputs, metadata, cache_dir, config=None, sequence=None, settings=None
):
    """Book decisions for all native ``pages`` of one source, through ``PageInputs``.

    Returns (BookDecisions, key, cache hit). ``pages`` is the complete page sequence (any iterable).
    """
    assert_unchanged()
    config, sequence = config or FurnitureConfig(), sequence or SequenceConfig()
    labels = metadata_labels(metadata)
    if metadata.get("source_sha256") != inputs.digest:
        raise ValueError("Page-label metadata belongs to another source")
    key, components = book_key(inputs, metadata, settings or Settings(), config, sequence)
    path = Path(cache_dir) / "furniture" / "book" / f"{key}.json"
    if path.exists():
        decisions = verified_read(path, BookDecisions, key)
        if decisions.book.source_sha256 != inputs.digest:
            raise ValueError("Furniture cache belongs to another source")
        return decisions, key, True
    features = {}
    for expected, page in enumerate(pages, 1):
        if page.geometry.page != expected:
            raise ValueError("Furniture needs the complete page sequence, in page order")
        layout, order = inputs(page)
        features[expected] = page_features(page, layout, order)
    decisions = decide_book(
        features, labels, inputs.digest, config, sequence, inputs.extractor.device.resolved
    )
    decisions = decisions.model_copy(
        update={"book": decisions.book.model_copy(update={"cache_key_inputs": components})}
    )
    assert_unchanged()
    atomic_write(path, decisions, key)
    return decisions, key, False


def page_furniture(page, inputs, decisions, decision_key, cache_dir):
    """Cached PageFurniture for one page under one book decision (``decision_key``)."""
    assert_unchanged()
    number = page.geometry.page
    path = Path(cache_dir) / "furniture" / "page" / decision_key / f"{number}.json"
    if path.exists():
        result = verified_read(path, PageFurniture, decision_key)
        if result.source_sha256 != inputs.digest or result.page != number:
            raise ValueError("Page furniture cache belongs to another source or page")
        return result
    layout, order = inputs(page)
    result = apply_page(
        page,
        layout,
        order,
        decisions.roles[number],
        decisions.book.markers[number - 1],
        inputs.vocabulary,
        inputs.extractor.device.resolved,
    )
    assert_unchanged()
    atomic_write(path, result, decision_key)
    return result
