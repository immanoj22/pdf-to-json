"""Cached native/derived page evidence with checksums and exact asset accounting."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from book_core.cache_store import FORMAT_VERSION, read_json, read_model, write_model, write_payload
from book_core.caching import assert_producer_unchanged, code_digest, runtime_versions
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.objects.consolidation import consolidate
from book_core.objects.models import AssetLedger, ImageRepetition, NativeObjectPage, ObjectAnalysis
from book_core.objects.roles import classify
from book_core.objects.spatial import build_graph

ANALYSIS_VERSION = "native-object-roles-9"
NATIVE_VERSION = "native-object-api-6"
LOADED_CODE_DIGEST = code_digest("analysis")


def verified_read(path, model, fingerprint, *, native=None):
    if model is ObjectAnalysis:
        entry = read_json(path)
        if entry.get("format_version", 1) not in {1, FORMAT_VERSION}:
            raise ValueError("Unsupported cache format version")
        payload = entry["payload"]
        if entry["fingerprint"] != fingerprint or (
            hashlib.sha256(payload.encode("utf8")).hexdigest() != entry["sha256"]
        ):
            raise ValueError("Corrupt object cache checksum or fingerprint")
        data = json.loads(payload)
        if "native_key" in data:
            native_key = data.pop("native_key")
            if len(native_key) != 64 or any(c not in "0123456789abcdef" for c in native_key):
                raise ValueError("Corrupt native cache reference")
            native_path = Path(path).parents[2] / "native" / native_key / Path(path).name
            native = native or read_model(native_path, NativeObjectPage, native_key)
            return ObjectAnalysis(native=native, **data)
    return read_model(path, model, fingerprint)


def atomic_write(path, value, fingerprint):
    write_model(path, value, fingerprint)


def write_analysis(path, value, fingerprint, native_key):
    """Native evidence lives once; every field is restored by verified_read."""
    payload = value.model_dump(mode="json", exclude={"native"}, exclude_defaults=True)
    payload["native_key"] = native_key
    write_payload(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), fingerprint)


def verify_asset_ledger(analysis):
    all_objects = analysis.all_objects()
    ids = [obj.id for obj in all_objects]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate asset/object identifier")
    expected = {obj.id for obj in all_objects if not obj.is_text}
    records = analysis.asset_ledger.records
    actual = [record.object_id for record in records]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Asset ledger must account for every asset exactly once")
    objects = {obj.id: obj for obj in all_objects}
    claimed = set()
    for compound in analysis.compounds:
        if len(set(compound.member_ids)) != len(compound.member_ids):
            raise ValueError("Duplicate compound member")
        for member in compound.member_ids:
            if member not in objects or objects[member].kind in {
                "text",
                "text_render",
                "compound",
                "clip",
                "group",
            }:
                raise ValueError("Compound has missing, text, context or recursive members")
            if member in claimed:
                raise ValueError("Primitive belongs to more than one compound")
            claimed.add(member)
    for record in records:
        if record.role == "unknown" and not record.review_required:
            raise ValueError("Unknown assets must remain under review")
    if any(edge.source not in objects or edge.target not in objects for edge in analysis.relations):
        raise ValueError("Dangling object relation")
    return {"assets": len(expected), "missing": 0, "extra": 0}


def fingerprints(digest, extractor, repetition=None):
    """Native and derived cache identities; shared by downstream derived caches."""
    if repetition is not None and repetition.source_sha256 != digest:
        raise ValueError("Repetition evidence belongs to a different PDF")
    identity = json.dumps(extractor.identity.model_dump(), sort_keys=True)
    native_fingerprint = stable_id(
        digest,
        identity,
        NATIVE_VERSION,
        code_digest("extraction"),
        json.dumps(runtime_versions(), sort_keys=True),
    )
    dependencies = {
        name: version(name)
        for name in ["shapely", "networkx", "numpy", "opencv-python-headless", "pydantic"]
    }
    fingerprint = stable_id(
        native_fingerprint,
        json.dumps(dependencies, sort_keys=True),
        ANALYSIS_VERSION,
        code_digest("analysis"),
        "bbox-geometry",
        "crop-dpi-96",
        json.dumps(repetition.model_dump() if repetition else None, sort_keys=True),
    )
    return native_fingerprint, fingerprint


def analyze_page(source, page_number, extractor, repetition=None, cache_dir=None, *, native=None):
    assert_producer_unchanged("analysis", LOADED_CODE_DIGEST)
    source = Path(source)
    if page_number < 1:
        raise ValueError("Page argument must be positive")
    before = source.stat()
    digest = source_digest(source)
    native_fingerprint, fingerprint = fingerprints(digest, extractor, repetition)
    root = Path(cache_dir) if cache_dir is not None else None
    path = root / "analysis" / fingerprint / f"{page_number}.json" if root is not None else None
    native_path = (
        root / "native" / native_fingerprint / f"{page_number}.json" if root is not None else None
    )
    if path is not None and path.exists():
        analysis = verified_read(path, ObjectAnalysis, fingerprint, native=native)
        if (
            analysis.native.page.source_sha256 != digest
            or analysis.native.page.geometry.page != page_number
        ):
            raise ValueError("Object cache belongs to another source or page")
        verify_asset_ledger(analysis)
        return analysis
    if native is not None:
        if native.page.source_sha256 != digest or native.page.geometry.page != page_number:
            raise ValueError("Native cache belongs to another source or page")
    elif native_path is not None and native_path.exists():
        native = verified_read(native_path, NativeObjectPage, native_fingerprint)
        if native.page.source_sha256 != digest or native.page.geometry.page != page_number:
            raise ValueError("Native cache belongs to another source or page")
    else:
        native = extractor.extract_object_page(source, page_number)
        if native_path is not None:
            assert_producer_unchanged("analysis", LOADED_CODE_DIGEST)
            atomic_write(native_path, native, native_fingerprint)
    compounds = consolidate(native)
    objects = [*native.objects, *compounds]
    _, relations, complete, diagnostics, checked = build_graph(objects, compounds)
    raster = extractor.render_page(source, page_number, dpi=96)
    records = classify(native, compounds, raster, repetition)
    analysis = ObjectAnalysis(
        native=native,
        compounds=compounds,
        relations=relations,
        asset_ledger=AssetLedger(records=records),
        graph_complete=complete,
        diagnostics=[*native.diagnostics, *diagnostics],
        candidate_pairs_checked=checked,
        analysis_version=ANALYSIS_VERSION,
    )
    verify_asset_ledger(analysis)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during object analysis")
    if path is not None:
        assert_producer_unchanged("analysis", LOADED_CODE_DIGEST)
        if native_path is not None:
            write_analysis(path, analysis, fingerprint, native_fingerprint)
        else:
            atomic_write(path, analysis, fingerprint)
    return analysis


def cached_repetition(source, extractor, cache_dir):
    assert_producer_unchanged("analysis", LOADED_CODE_DIGEST)
    source = Path(source)
    key = stable_id(
        source_digest(source),
        json.dumps(extractor.identity.model_dump(), sort_keys=True),
        "image-repetition-3",
        json.dumps(runtime_versions(), sort_keys=True),
        code_digest("extraction"),
    )
    path = Path(cache_dir) / "repetition" / f"{key}.json"
    if path.exists():
        result = verified_read(path, ImageRepetition, key)
        if result.source_sha256 != source_digest(source):
            raise ValueError("Repetition cache belongs to another PDF")
        return result
    result = extractor.image_repetition(source)
    assert_producer_unchanged("analysis", LOADED_CODE_DIGEST)
    atomic_write(path, result, key)
    return result
