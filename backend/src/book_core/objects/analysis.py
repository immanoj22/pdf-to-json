"""Cached native/derived page evidence with checksums and exact asset accounting."""

import hashlib
import json
import os
import tempfile
from importlib.metadata import version
from pathlib import Path

from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.objects.consolidation import consolidate
from book_core.objects.models import AssetLedger, ImageRepetition, NativeObjectPage, ObjectAnalysis
from book_core.objects.roles import classify
from book_core.objects.spatial import build_graph

ANALYSIS_VERSION = "native-object-roles-9"
NATIVE_VERSION = "native-object-api-5"


def verified_read(path, model, fingerprint):
    entry = json.loads(path.read_text(encoding="utf-8"))
    payload = entry["payload"]
    checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if entry["fingerprint"] != fingerprint or checksum != entry["sha256"]:
        raise ValueError("Corrupt object cache checksum or fingerprint")
    return model.model_validate_json(payload)


def atomic_write(path, value, fingerprint):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump_json()
    entry = {
        "fingerprint": fingerprint,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "payload": payload,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(entry, file)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


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


def analyze_page(source, page_number, extractor, repetition=None, cache_dir=None):
    source = Path(source)
    if page_number < 1:
        raise ValueError("Page argument must be positive")
    before = source.stat()
    digest = source_digest(source)
    if repetition is not None and repetition.source_sha256 != digest:
        raise ValueError("Repetition evidence belongs to a different PDF")
    identity = json.dumps(extractor.identity.model_dump(), sort_keys=True)
    native_fingerprint = stable_id(digest, identity, NATIVE_VERSION)
    dependencies = {
        name: version(name)
        for name in ["shapely", "networkx", "numpy", "opencv-python-headless", "pydantic"]
    }
    fingerprint = stable_id(
        native_fingerprint,
        json.dumps(dependencies, sort_keys=True),
        ANALYSIS_VERSION,
        "bbox-geometry",
        "crop-dpi-96",
        json.dumps(repetition.model_dump() if repetition else None, sort_keys=True),
    )
    root = Path(cache_dir) if cache_dir is not None else None
    path = root / "analysis" / fingerprint / f"{page_number}.json" if root is not None else None
    native_path = (
        root / "native" / native_fingerprint / f"{page_number}.json" if root is not None else None
    )
    if path is not None and path.exists():
        analysis = verified_read(path, ObjectAnalysis, fingerprint)
        if (
            analysis.native.page.source_sha256 != digest
            or analysis.native.page.geometry.page != page_number
        ):
            raise ValueError("Object cache belongs to another source or page")
        verify_asset_ledger(analysis)
        return analysis
    if native_path is not None and native_path.exists():
        native = verified_read(native_path, NativeObjectPage, native_fingerprint)
        if native.page.source_sha256 != digest or native.page.geometry.page != page_number:
            raise ValueError("Native cache belongs to another source or page")
    else:
        native = extractor.extract_object_page(source, page_number)
        if native_path is not None:
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
        atomic_write(path, analysis, fingerprint)
    return analysis


def cached_repetition(source, extractor, cache_dir):
    source = Path(source)
    key = stable_id(
        source_digest(source),
        json.dumps(extractor.identity.model_dump(), sort_keys=True),
        "image-repetition-3",
    )
    path = Path(cache_dir) / "repetition" / f"{key}.json"
    if path.exists():
        result = verified_read(path, ImageRepetition, key)
        if result.source_sha256 != source_digest(source):
            raise ValueError("Repetition cache belongs to another PDF")
        return result
    result = extractor.image_repetition(source)
    atomic_write(path, result, key)
    return result
