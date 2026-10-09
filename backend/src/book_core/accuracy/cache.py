"""Content-addressed cache keys for optional providers; no pipeline or disk writes."""

import hashlib
import json

from book_core.accuracy.interfaces import AccuracyProvider
from book_core.accuracy.models import (
    AccuracyInput,
    AccuracyResult,
    ContinuationInput,
    ContinuationResult,
    ExtensionMetadata,
    FormulaInput,
    FormulaResult,
    HeadingInput,
    HeadingResult,
    MathBuildInput,
    MathBuildResult,
    MathConversionInput,
    MathConversionResult,
    PageReviewInput,
    PageReviewResult,
    TableStructureInput,
    TableStructureResult,
    source_ref_within,
)
from book_core.caching import code_digest, runtime_versions

ACCURACY_CACHE_VERSION = "optional-accuracy-evidence-1"


def canonical_digest(value) -> str:
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def request_digest(request: AccuracyInput) -> str:
    """Includes source references, coordinates, image bytes, features and evidence digests."""
    return canonical_digest(
        {
            "input_type": f"{type(request).__module__}.{type(request).__qualname__}",
            "value": request.model_dump(mode="json"),
        }
    )


def metadata_key(metadata: ExtensionMetadata, *, resolved_device=None) -> dict:
    actual_device = metadata.device.resolved if resolved_device is None else resolved_device
    if actual_device not in {"cpu", "cuda"}:
        raise ValueError("Unsupported execution device")
    if metadata.device.requested == "cpu" and actual_device != "cpu":
        raise ValueError("A CPU device policy cannot execute on CUDA")
    device = {"requested": metadata.device.requested, "resolved": actual_device}
    dependencies = {"core": runtime_versions(), "provider": metadata.dependency_versions}
    return {
        **metadata.model_dump(mode="json", exclude={"device"}),
        "configuration_sha256": canonical_digest(metadata.configuration),
        "runtime_sha256": canonical_digest(dependencies),
        "runtime": dependencies,
        "device": device,
    }


def accuracy_fingerprint(
    request: AccuracyInput, provider: AccuracyProvider, *, resolved_device=None
) -> str:
    return canonical_digest(
        {
            "source_sha256": request.source_sha256,
            "request_sha256": request_digest(request),
            "cache_version": ACCURACY_CACHE_VERSION,
            "producer_sha256": code_digest("accuracy"),
            "provider": metadata_key(provider.metadata, resolved_device=resolved_device),
        }
    )


def _result_type(request):
    # Local import keeps the opt-in legacy bridges out of ordinary contract imports.
    from book_core.accuracy.adapters import LanguageInput, LanguageResult, OcrInput, OcrResult

    contracts = (
        (TableStructureInput, TableStructureResult),
        (FormulaInput, FormulaResult),
        (MathBuildInput, MathBuildResult),
        (MathConversionInput, MathConversionResult),
        (ContinuationInput, ContinuationResult),
        (HeadingInput, HeadingResult),
        (PageReviewInput, PageReviewResult),
        (LanguageInput, LanguageResult),
        (OcrInput, OcrResult),
    )
    for input_type, result_type in contracts:
        if isinstance(request, input_type):
            return result_type
    raise ValueError("Unknown accuracy request schema")


def validate_result(request: AccuracyInput, provider: AccuracyProvider, result: AccuracyResult):
    """Reject stale, mismatched or dangling source/configuration/code/model/device evidence."""
    if not isinstance(result, _result_type(request)):
        raise ValueError("Accuracy result schema differs from its request operation")
    # model_copy and external caches can bypass initial construction validators.
    type(request).model_validate(request.model_dump())
    type(result).model_validate(result.model_dump())
    if result.source_sha256 != request.source_sha256 or result.request_sha256 != request_digest(
        request
    ):
        raise ValueError("Accuracy evidence belongs to another source request")
    expected = provider.metadata.model_copy(update={"device": result.metadata.device})
    if result.metadata != expected:
        raise ValueError("Accuracy evidence provider metadata differs")
    if result.metadata.device.requested != provider.metadata.device.requested:
        raise ValueError("Accuracy evidence device policy differs")
    if result.cache_key != accuracy_fingerprint(
        request, provider, resolved_device=result.metadata.device.resolved
    ):
        raise ValueError("Accuracy evidence cache key differs")
    regions = {region.id: region for region in request.regions}
    requested_refs = [ref for region in request.regions for ref in region.source_refs]
    emitted_refs = []
    if isinstance(result, TableStructureResult):
        emitted_refs.extend(ref for cell in result.cells for ref in cell.source_refs)
    if isinstance(result, FormulaResult):
        for item in result.observations:
            if item.region_id not in regions:
                raise ValueError("Formula evidence references an unknown source region")
            if item.source_kind != request.source_kind:
                raise ValueError("Formula observation source kind differs from its request")
            if any(
                not source_ref_within(ref, regions[item.region_id].source_refs)
                for ref in item.source_refs
            ):
                raise ValueError("Formula observation references another source region")
    if isinstance(result, MathBuildResult) and result.tree is not None:
        emitted_refs.extend(result.tree.iter_source_refs())
        if request.source_kind == "digital":
            pending = [result.tree]
            while pending:
                tree = pending.pop()
                if tree.derived_value is not None:
                    raise ValueError("Digital math evidence must preserve source references")
                pending.extend(tree.children)
    if isinstance(result, MathConversionResult) and result.target_format != request.target_format:
        raise ValueError("Math conversion output format differs from its request")
    if isinstance(result, PageReviewResult):
        evidence_ids = {ref.id: ref for ref in request.evidence_refs}
        for finding in result.findings:
            if not set(finding.region_ids).issubset(regions):
                raise ValueError("Review finding references an unknown source region")
            if any(evidence_ids.get(ref.id) != ref for ref in finding.evidence_refs):
                raise ValueError("Review finding references unknown evidence")
            emitted_refs.extend(finding.source_refs)
    if any(not source_ref_within(ref, requested_refs) for ref in emitted_refs):
        raise ValueError("Accuracy evidence references an unknown source range")
