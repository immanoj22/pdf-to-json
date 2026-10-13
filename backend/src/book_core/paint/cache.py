"""Independent paint evidence cache; no changes to native or object-analysis keys."""

import json
from pathlib import Path

from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.extraction.fingerprints import stable_id
from book_core.paint.extractor import VERSION, capable
from book_core.paint.models import PagePaintEvidence

CONFIG = {"render_scales": [2, 4], "opaque_cover": True}
LOADED_DIGEST = code_digest("paint")


def paint_fingerprint(analysis_key, device):
    return stable_id(
        analysis_key, code_digest("paint"), VERSION, json.dumps(CONFIG, sort_keys=True), device
    )


def page_paint(source, page, extractor, analysis_key, cache_dir=None):
    assert_producer_unchanged("paint", LOADED_DIGEST)
    key = paint_fingerprint(analysis_key, extractor.device.resolved)
    path = Path(cache_dir) / "paint" / key / f"{page.geometry.page}.json" if cache_dir else None
    if path is not None and path.exists():
        result = read_model(path, PagePaintEvidence, key)
    else:
        provider = capable(extractor)
        if provider is None:
            result = PagePaintEvidence(
                source_sha256=page.source_sha256,
                page=page.geometry.page,
                version=VERSION,
                diagnostics=["Extractor has no paint-proof capability; native visibility retained"],
            )
        else:
            result = provider.extract_paint_evidence(
                source, page, scales=tuple(CONFIG["render_scales"])
            )
        result = result.model_copy(
            update={
                "cache_key_inputs": {
                    "analysis_key": analysis_key,
                    "producer": LOADED_DIGEST,
                    "configuration": json.dumps(CONFIG, sort_keys=True),
                    "version": VERSION,
                }
            }
        )
        assert_producer_unchanged("paint", LOADED_DIGEST)
        if path is not None:
            write_model(path, result, key)
    if result.source_sha256 != page.source_sha256 or result.page != page.geometry.page:
        raise ValueError("Paint evidence belongs to another source/page")
    if any(
        s.span_id not in page.store.spans or page.store.spans[s.span_id].line_id != s.line_id
        for s in result.spans
    ):
        raise ValueError("Paint evidence references another span store")
    return result
