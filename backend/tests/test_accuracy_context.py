"""Read-only multi-script source contexts with raw-range and cache identity checks."""

import hashlib

import pytest
from pydantic import ValidationError

from book_core.accuracy.cache import request_digest
from book_core.accuracy.context import (
    ResolvedSourceText,
    SourceEvidenceResolver,
    SpanStoreEvidenceResolver,
    bind_source_context,
    resolve_continuation,
    validate_source_context,
)
from book_core.accuracy.models import (
    ContinuationInput,
    EvidenceReference,
    GlyphEvidence,
    MathBuildInput,
    SourceRegion,
)
from book_core.model.common import SpanRef

SOURCE = "a" * 64


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pair(page):
    return ContinuationInput(
        source_sha256=page.source_sha256,
        regions=[
            SourceRegion(
                id="arabic",
                page=1,
                source_refs=[SpanRef(span_id="span-0", start=0, end=5)],
                languages=["ara"],
                script="Arab",
                text_direction="rtl",
            ),
            SourceRegion(
                id="english",
                page=1,
                source_refs=[SpanRef(span_id="span-1")],
                languages=["eng"],
            ),
        ],
        first_region_id="arabic",
        second_region_id="english",
    )


def test_arabic_english_binding_preserves_transient_text_and_supplied_order(make_page):
    page = make_page(("\u0645\u0631\u062d\u0628\u0627 ", "Hello"))
    before = page.model_dump_json()
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    assert isinstance(context, SourceEvidenceResolver)
    request = _pair(page)
    old_request = request.model_dump_json()
    bound = bind_source_context(request, context)
    first, second = resolve_continuation(bound, context)
    assert first.raw_text == "\u0645\u0631\u062d\u0628\u0627"
    assert second.text == "Hello"
    assert first.pages == second.pages == (1,)
    assert bound.first_text_sha256 == _digest(first.text)
    assert bound.second_text_sha256 == _digest(second.text)
    assert context.evidence_ref in bound.evidence_refs
    assert context.evidence_ref.kind == "span_store"
    assert first.raw_text not in bound.model_dump_json()
    assert second.text not in bound.model_dump_json()
    assert request.model_dump_json() == old_request
    assert page.model_dump_json() == before
    reversed_text = context.resolve(
        [SpanRef(span_id="span-1"), SpanRef(span_id="span-0")], source_sha256=SOURCE
    )
    assert reversed_text.raw_text == "Hello\u0645\u0631\u062d\u0628\u0627 "
    assert request_digest(bound) != request_digest(request)


def test_unspaced_japanese_ranges_do_not_gain_word_separators(make_page):
    text = "\u65e5\u672c\u8a9e\u3092\u5b66\u3076"
    page = make_page((text,))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    resolved = context.resolve(
        [SpanRef(span_id="span-0", start=0, end=3), SpanRef(span_id="span-0", start=3, end=6)],
        source_sha256=SOURCE,
    )
    assert resolved.raw_text == resolved.text == text
    assert " " not in resolved.text and "\n" not in resolved.text


def test_ligature_offsets_slice_original_codepoints_before_nfkc(make_page):
    page = make_page(("A\ufb03B",))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    ligature = context.resolve([SpanRef(span_id="span-0", start=1, end=2)], source_sha256=SOURCE)
    following = context.resolve([SpanRef(span_id="span-0", start=2, end=3)], source_sha256=SOURCE)
    assert ligature.raw_text == "\ufb03"
    assert ligature.text == "ffi"
    assert ligature.raw_sha256 == _digest("\ufb03")
    assert ligature.text_sha256 == _digest("ffi")
    assert ligature.raw_sha256 != ligature.text_sha256
    assert following.raw_text == following.text == "B"


def test_wrong_source_and_unknown_or_out_of_range_refs_fail(make_page):
    page = make_page(("Hello",))
    with pytest.raises(ValueError, match="provenance"):
        SpanStoreEvidenceResolver("b" * 64, page.store)
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    with pytest.raises(ValueError, match="another source"):
        context.resolve([SpanRef(span_id="span-0")], source_sha256="b" * 64)
    with pytest.raises(ValueError, match="unknown span"):
        context.resolve([SpanRef(span_id="missing")], source_sha256=SOURCE)
    with pytest.raises(ValueError, match="original span"):
        context.resolve([SpanRef(span_id="span-0", start=1, end=99)], source_sha256=SOURCE)
    with pytest.raises(ValueError, match="artifact digest"):
        context.resolve([], source_sha256=SOURCE, evidence_sha256="b" * 64)


def test_context_detects_shallow_store_mutation_and_stale_bound_requests(make_page):
    page = make_page(("\u0645\u0631\u062d\u0628\u0627 ", "Hello"))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    bound = bind_source_context(_pair(page), context)
    span = page.store.spans["span-1"]
    page.store.spans["span-1"] = span.model_copy(update={"raw_text": "Changed", "text": "Changed"})
    with pytest.raises(ValueError, match="Stale source context"):
        context.assert_current()
    with pytest.raises(ValueError, match="Stale source context"):
        resolve_continuation(bound, context)
    fresh = SpanStoreEvidenceResolver(SOURCE, page.store)
    assert fresh.native_artifact_sha256 != context.native_artifact_sha256
    with pytest.raises(ValueError, match="current source context"):
        validate_source_context(bound, fresh)


def test_region_page_and_request_source_are_context_checked(make_page):
    page = make_page(("\u0645\u0631\u062d\u0628\u0627 ", "Hello"))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    request = _pair(page)
    wrong_source = request.model_copy(update={"source_sha256": "b" * 64})
    with pytest.raises(ValueError, match="different sources"):
        bind_source_context(wrong_source, context)
    region = request.regions[0].model_copy(update={"page": 2})
    wrong_page = request.model_copy(update={"regions": [region, request.regions[1]]})
    with pytest.raises(ValueError, match="source page"):
        bind_source_context(wrong_page, context)


def test_bound_text_hashes_and_artifact_reference_are_required_and_checked(make_page):
    page = make_page(("\u0645\u0631\u062d\u0628\u0627 ", "Hello"))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    request = _pair(page)
    with pytest.raises(ValueError, match="current source context"):
        validate_source_context(request, context)
    bound = bind_source_context(request, context)
    validate_source_context(bound, context)
    assert bind_source_context(bound, context) == bound
    bad_text = bound.model_copy(update={"first_text_sha256": "b" * 64})
    with pytest.raises(ValueError, match="Continuation text digests"):
        validate_source_context(bad_text, context)
    bad_ref = context.evidence_ref.model_copy(update={"sha256": "b" * 64})
    conflicting = request.model_copy(update={"evidence_refs": [bad_ref]})
    with pytest.raises(ValueError, match="Conflicting"):
        bind_source_context(conflicting, context)
    with pytest.raises(ValidationError):
        ContinuationInput(
            **request.model_dump(exclude={"first_text_sha256"}), first_text_sha256=SOURCE
        )


def test_math_context_binds_span_store_without_claiming_glyph_geometry(make_page):
    page = make_page(("x + y",))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    request = MathBuildInput(
        source_sha256=SOURCE,
        source_kind="digital",
        regions=[SourceRegion(id="formula", page=1, source_refs=[SpanRef(span_id="span-0")])],
    )
    bound = bind_source_context(request, context)
    validate_source_context(bound, context)
    assert bound.evidence_refs == [context.evidence_ref]
    assert bound.evidence_refs[0].kind == "span_store"
    assert "x + y" not in bound.model_dump_json()


def test_resolved_text_rejects_wrong_digest_or_normalization():
    fields = {
        "raw_text": "A",
        "text": "A",
        "raw_sha256": _digest("A"),
        "text_sha256": _digest("A"),
        "source_sha256": SOURCE,
        "native_artifact_sha256": "b" * 64,
        "pages": (1,),
    }
    with pytest.raises(ValueError, match="digests"):
        ResolvedSourceText(**{**fields, "text_sha256": "c" * 64})
    with pytest.raises(ValueError, match="normalization"):
        ResolvedSourceText(**{**fields, "text": "B", "text_sha256": _digest("B")})


def test_math_glyph_ranges_are_checked_without_claiming_native_geometry(make_page):
    page = make_page(("x + y",))
    context = SpanStoreEvidenceResolver(SOURCE, page.store)
    native_ref = EvidenceReference(id="native", sha256="b" * 64, kind="native_objects")
    glyph = GlyphEvidence(
        id="glyph",
        region_id="formula",
        native_evidence_id="native",
        source_ref=SpanRef(span_id="span-0", start=0, end=99),
        bbox=page.store.spans["span-0"].bbox,
        origin=(10, 25),
        writing_vector=(1, 0),
    )
    request = MathBuildInput(
        source_sha256=SOURCE,
        source_kind="digital",
        glyphs=[glyph],
        evidence_refs=[native_ref],
        regions=[SourceRegion(id="formula", page=1, source_refs=[SpanRef(span_id="span-0")])],
    )
    with pytest.raises(ValueError, match="original span"):
        bind_source_context(request, context)


def test_custom_context_reference_must_identify_its_actual_artifact(make_page):
    page = make_page(("Hello",))
    actual = SpanStoreEvidenceResolver(SOURCE, page.store)

    class IncorrectReference:
        def __getattr__(self, name):
            return getattr(actual, name)

        @property
        def evidence_ref(self):
            return actual.evidence_ref.model_copy(update={"sha256": "b" * 64})

    request = MathBuildInput(
        source_sha256=SOURCE,
        source_kind="digital",
        regions=[SourceRegion(id="formula", page=1, source_refs=[SpanRef(span_id="span-0")])],
    )
    with pytest.raises(ValueError, match="actual artifact digest"):
        bind_source_context(request, IncorrectReference())
