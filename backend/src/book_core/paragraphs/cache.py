"""Paragraph stage entry points with cached book and page results.

Pass 1 profiles the book (line pitch per font size, hyphenated compounds, a book-relative
letter threshold for language evidence). Pass 2 builds each page (cached per page) and decides
paragraph continuations across consecutive pages (book level). Inputs: native pages through
the Extractor, ``furniture.inputs.PageInputs`` and the Step 8 furniture decision, the Step 6
vocabulary and printed-navigation entries.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from book_core.caching import assert_producer_unchanged, code_digest
from book_core.document_analysis.language import relative_letter_threshold
from book_core.extraction.fingerprints import stable_id
from book_core.furniture.cache import page_furniture
from book_core.model.common import CoreModel, Provenance
from book_core.objects.analysis import atomic_write, verified_read
from book_core.paragraphs.crosspage import page_join
from book_core.paragraphs.keys import book_fingerprint, book_key_components, paragraph_code_digest
from book_core.paragraphs.lexicon import Profile
from book_core.paragraphs.models import BookParagraphs, PageJoin, PageParagraphs
from book_core.paragraphs.page import PARAGRAPHS_VERSION, build_page
from book_core.paragraphs.segment import PageSegmenter
from book_core.settings import Settings

LOADED_DIGEST = paragraph_code_digest()
LOADED_ORDER_DIGEST = code_digest("reading_order")
DEFAULT_CONFIG = {"anchor_rule": "keep"}


def assert_unchanged():
    assert_producer_unchanged("reading_order", LOADED_ORDER_DIGEST)
    if paragraph_code_digest() != LOADED_DIGEST:
        raise RuntimeError("paragraphs producer source changed; restart the worker")


class BookParagraphResult(CoreModel):
    book: BookParagraphs
    page_keys: dict[int, str] = Field(default_factory=dict)


def detector_for(settings, minimum_letters):
    """(detector or None, identity). Language evidence is an optional install extra."""
    from book_core.document_analysis.language import LinguaLanguageDetector

    try:
        detector = LinguaLanguageDetector(settings.ocr_languages, minimum_letters=minimum_letters)
    except RuntimeError as error:  # extra not installed: languages stay undetermined
        return None, {"name": "unavailable", "reason": str(error)}
    return detector, detector.identity


def _pages_key(book_key, number):
    return stable_id(book_key, "page", number)


def analyze_book_paragraphs(
    pages,
    inputs,
    furniture,
    furniture_key,
    furniture_cache,
    navigation,
    cache_dir,
    settings=None,
    config=None,
):
    """Book paragraphs for ``pages`` (a callable returning a fresh native page iterator).

    Returns (BookParagraphResult, cache hit). Page results are read with ``load_page``.
    """
    assert_unchanged()
    settings = settings or Settings()
    config = {**DEFAULT_CONFIG, **(config or {})}
    # The detector identity enters the key; its letter threshold is book-relative (pass 1).
    probe, probe_identity = detector_for(settings, 10)
    identity = {k: v for k, v in probe_identity.items() if k != "configuration"}
    components = book_key_components(
        paragraphs=LOADED_DIGEST,
        furniture_key=furniture_key,
        vocabulary=inputs.vocabulary,
        navigation=navigation,
        detector=identity,
        settings=settings,
        config=config,
        version=PARAGRAPHS_VERSION,
    )
    key = book_fingerprint(components)
    root = Path(cache_dir) / "paragraphs"
    path = root / "book" / f"{key}.json"
    if path.exists():
        result = verified_read(path, BookParagraphResult, key)
        if result.book.source_sha256 != inputs.digest:
            raise ValueError("Paragraph cache belongs to another source")
        return result, True

    def furniture_of(page):
        return page_furniture(page, inputs, furniture, furniture_key, furniture_cache)

    profile, letters = Profile(), []
    for page in pages():
        layout, _ = inputs(page)
        result = furniture_of(page)
        profile.add_page(page, layout, result.order)
        for line in layout.lines:
            text = "".join(page.store.spans[s].raw_text for s in line.span_ids)
            letters.append(sum(c.isalpha() for c in text))
    frozen = profile.freeze()
    threshold = relative_letter_threshold(letters)
    detector, detector_identity = detector_for(settings, threshold["resolved_minimum_letters"])
    del probe
    joins, candidates, page_keys, previous = [], [], {}, None
    for page in pages():
        number = page.geometry.page
        layout, _ = inputs(page)
        result = furniture_of(page)
        built = build_page(
            page,
            layout,
            result,
            frozen,
            inputs.vocabulary,
            navigation.get(number),
            detector,
            config["anchor_rule"],
            inputs.extractor.device.resolved,
        )
        page_key = _pages_key(key, number)
        atomic_write(root / "page" / key / f"{number}.json", built, page_key)
        page_keys[number] = page_key
        current = (page, layout, built.units, result)
        if previous is not None:
            furnitures = {id(previous[1]): previous[3], id(layout): result}

            def factory(pg, ly, furnitures=furnitures):
                return PageSegmenter(
                    pg, ly, furnitures[id(ly)], frozen, inputs.vocabulary, frozen["compounds"]
                )

            join, candidate = page_join(previous[:3], current[:3], inputs.vocabulary, factory)
            if join is not None:
                joins.append(join)
            if candidate is not None:
                candidates.append(candidate)
        previous = current
    book = BookParagraphs(
        source_sha256=inputs.digest,
        paragraphs_version=PARAGRAPHS_VERSION,
        pages=len(page_keys),
        page_joins=joins,
        page_join_candidates=candidates,
        profile={
            "pitch_by_size": frozen["pitch_by_size"],
            "hyphenated_compounds": len(frozen["compounds"]),
            "language_threshold": threshold,
            "language_detector": detector_identity,
            "anchor_rule": config["anchor_rule"],
        },
        cache_key_inputs=components,
        provenance=Provenance(
            source_sha256=inputs.digest,
            engine="book_core.paragraphs",
            engine_version=PARAGRAPHS_VERSION,
            method="derived",
            resolved_device=inputs.extractor.device.resolved,
        ),
    )
    output = BookParagraphResult(book=book, page_keys=page_keys)
    assert_unchanged()
    atomic_write(path, output, key)
    return output, False


def load_page(result, number, cache_dir):
    """The cached PageParagraphs of one page, with cross-page links applied."""
    key = result.page_keys[number]
    book_key = book_fingerprint(result.book.cache_key_inputs)
    path = Path(cache_dir) / "paragraphs" / "page" / book_key / f"{number}.json"
    page = verified_read(path, PageParagraphs, key)
    links_to = {
        j.from_unit_id: j.to_unit_id for j in result.book.page_joins if j.from_page == number
    }
    links_from = {
        j.to_unit_id: j.from_unit_id for j in result.book.page_joins if j.to_page == number
    }
    if not links_to and not links_from:
        return page
    units = [
        u.model_copy(
            update={"continues_to": links_to.get(u.id), "continues_from": links_from.get(u.id)}
        )
        for u in page.units
    ]
    return page.model_copy(update={"units": units})


def chains(result) -> dict[str, str]:
    """{unit id: id of the first unit of its logical paragraph} for cross-page chains."""
    root = {}
    for join in sorted(result.book.page_joins, key=lambda j: j.from_page):
        root[join.to_unit_id] = root.get(join.from_unit_id, join.from_unit_id)
    return root


__all__ = ["PageJoin", "analyze_book_paragraphs", "chains", "load_page"]
