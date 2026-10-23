"""Assembly stage: the published book JSON of a final archive, validated, written atomically.

Inputs: the final archive (all stage decisions), the run's native object cache (span
baselines, drawings), the source PDF through the Extractor capabilities (link annotations,
render proofs of hidden text) and the client profile. Page evidence (links and render proofs)
is cached per page under its own key (``assembly_evidence`` scope: source, native key,
evidence producer), so assembly changes never redo the renders.

The output folder ``<output>/<book key>/`` holds ``book.json`` (canonical: sorted keys,
compact UTF-8; validated against ``book.schema.json``), ``images/`` (figure images named by
the profile and equation fallbacks), ``review/`` (crops of review items, per the profile)
and ``manifest.json`` (the files and their SHA-256). The book key binds the final archive
key, the evidence key, the assembly producer, the profile hash and the job settings; the run
date is outside the content hash. Writing is atomic (a temporary folder, then a rename).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from book_core.cache_store import read_json, write_json
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.extraction.fingerprints import stable_id

VERSION = "assembly-1"
EVIDENCE_VERSION = "assembly-evidence-3"
LOADED_DIGEST = code_digest("assembly")
LOADED_EVIDENCE_DIGEST = code_digest("assembly_evidence")


class _Geometry:
    __slots__ = ("origin", "direction")

    def __init__(self, origin, direction):
        self.origin, self.direction = tuple(origin), tuple(direction)


class _Drawing:
    __slots__ = ("kind", "bbox")

    def __init__(self, bbox):
        from book_core.model.common import BBox

        self.kind, self.bbox = "drawing", BBox(**bbox)


class NativeEvidence:
    """What the assembly reads of a cached native object page: span baselines and the
    boxes of drawn objects (integrity-checked like every cache read, not fully validated)."""

    def __init__(self, span_geometry, objects):
        self.span_geometry, self.objects = span_geometry, objects


def read_native_evidence(root, key, number):
    """The native evidence of one page, or None where none is cached (OCR views)."""
    path = Path(root) / "native" / key / f"{number}.json"
    if not path.exists():
        return None
    entry = read_json(path)
    payload = entry["payload"]
    if entry["fingerprint"] != key or (
        hashlib.sha256(payload.encode("utf8")).hexdigest() != entry["sha256"]
    ):
        raise ValueError("Corrupt native cache checksum or fingerprint")
    data = json.loads(payload)
    geometry = {sid: _Geometry(g["origin"], g["direction"])
                for sid, g in data.get("span_geometry", {}).items()}  # fmt: skip
    drawings = [_Drawing(o["bbox"]) for o in data.get("objects", [])
                if o.get("kind") == "drawing" and o.get("bbox")]  # fmt: skip
    return NativeEvidence(geometry, drawings)


def evidence_fingerprint(source_sha256, native_key):
    return stable_id(EVIDENCE_VERSION, source_sha256, native_key, code_digest("assembly_evidence"))


def page_evidence(root, key, source, extractor, page, number):
    """{"links": [PageLink], "marks": PageMarks, "not_rendered": {span id: proof}} of one
    page (cached)."""
    from book_core.assembly.hidden import candidates, render_proofs
    from book_core.assembly.links import PageLink, PageMarks, capable

    path = Path(root) / "assembly_evidence" / key / f"{number}.json"
    if path.exists():
        payload = read_json(path)
        if payload.get("key") != key or payload.get("page") != number:
            raise ValueError("Assembly evidence cache holds another key or page")
    else:
        assert_producer_unchanged("assembly_evidence", LOADED_EVIDENCE_DIGEST)
        reader = capable(extractor)
        links = reader.extract_links(source, number) if reader is not None else []
        marks = (reader.extract_marks(source, number, page.store, links) if reader is not None
                 else PageMarks(paired=False))  # fmt: skip
        proofs = render_proofs(source, page, candidates(page.store))
        unproven = proofs.pop("_unproven", {})
        payload = {
            "key": key,
            "page": number,
            "version": EVIDENCE_VERSION,
            "links": [link.model_dump(mode="json") for link in links],
            "link_reader": reader is not None,
            "marks": marks.model_dump(mode="json"),
            "not_rendered": proofs,
            "unproven": unproven,
        }
        assert_producer_unchanged("assembly_evidence", LOADED_EVIDENCE_DIGEST)
        write_json(path, payload)
    return {
        "links": [PageLink.model_validate(link) for link in payload["links"]],
        "marks": PageMarks.model_validate(payload["marks"]),
        "not_rendered": payload["not_rendered"],
    }


def book_fingerprint(final_key, evidence_key, profile, settings_sha256):
    return stable_id(VERSION, final_key, evidence_key, code_digest("assembly"), profile.sha256,
                     settings_sha256)  # fmt: skip


def settings_digest(*models):
    """SHA-256 of the job and stage settings that shaped the run (canonical JSON)."""
    parts = [m.model_dump(mode="json") if hasattr(m, "model_dump") else m for m in models]
    text = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def converter_identity():
    from importlib.metadata import PackageNotFoundError, version

    try:
        found = version("universal-book-core")
    except PackageNotFoundError:
        found = "0+unknown"
    return {"name": "book_core", "version": found, "producer": LOADED_DIGEST}


def publish_book(archive, output_dir, *, source, extractor, native_page, cache_root, native_key,
                 source_sha256, final_key, profile, settings_sha256, run_date=None,
                 progress=None):  # fmt: skip
    """Assemble, validate and publish; returns (output folder, stats)."""
    from book_core.assembly import validate
    from book_core.assembly.assemble import assemble

    assert_producer_unchanged("assembly", LOADED_DIGEST)
    evidence_key = evidence_fingerprint(source_sha256, native_key)
    key = book_fingerprint(final_key, evidence_key, profile, settings_sha256)
    destination = Path(output_dir) / f"book-{key}"
    if destination.exists() and (destination / "manifest.json").exists():
        manifest = json.loads((destination / "manifest.json").read_text("utf-8"))
        if manifest.get("run_date") == run_date:
            _verify(destination, manifest)
            return destination, {"reused": True, "key": key, "evidence_key": evidence_key}

    def evidence(number, page):
        return page_evidence(cache_root, evidence_key, source, extractor, page, number)

    book, ctx = assemble(archive, native_page=native_page, evidence_page=evidence,
                         profile=profile, converter=converter_identity(),
                         settings_sha256=settings_sha256, run_date=run_date,
                         progress=progress)  # fmt: skip
    data = book.model_dump(mode="json", by_alias=True)
    validate.check(data)
    text = validate.dumps(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".book-", dir=destination.parent) as temporary:
        pending = Path(temporary) / "book"
        pending.mkdir()
        (pending / "book.json").write_text(text, "utf-8", newline="\n")
        if ctx.images:
            (pending / "images").mkdir()
        for name, row in sorted(ctx.images.items()):
            target = pending / "images" / name
            if row["converted"] is not None:
                target.write_bytes(row["converted"])
            else:
                shutil.copyfile(Path(archive) / "images" / row["original"], target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Published image {name} differs from its recorded digest")
        crops = [item for item in data["review"]["items"] if item.get("crop")] if data.get(
            "review") else []  # fmt: skip
        if crops:
            _write_crops(source, crops, pending, profile.review.crop_dpi)
        files = {p.relative_to(pending).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(pending.rglob("*")) if p.is_file()}  # fmt: skip
        manifest = {
            "format_version": 1,
            "schema": data["schema"],
            "key": key,
            "evidence_key": evidence_key,
            "final_key": final_key,
            "content_sha256": data["metadata"]["content_sha256"],
            "run_date": run_date,
            "files": files,
        }
        (pending / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True)
                                               + "\n", "utf-8", newline="\n")  # fmt: skip
        assert_producer_unchanged("assembly", LOADED_DIGEST)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(pending, destination)
    stats = {
        "reused": False,
        "key": key,
        "evidence_key": evidence_key,
        "bytes": len(text.encode("utf-8")),
        "units": sum(1 for _ in _units(book)),
        "review_items": len(data["review"]["items"]) if data.get("review") else 0,
        "counts": {k: v for k, v in sorted(ctx.counts.items()) if not k.startswith("segment:")},
    }
    return destination, stats


def _units(book):
    from book_core.assembly.schema import iter_units

    return iter_units(book.content)


def _verify(destination, manifest):
    for name, checksum in manifest["files"].items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != checksum:
            raise ValueError("Existing book output differs or is corrupt")


def _write_crops(source, items, pending, dpi):
    """Crop images of review items: the item's box with a margin, else the whole page."""
    import pymupdf

    from book_core.run_context import open_source

    folder = pending / "review"
    folder.mkdir()
    with open_source(Path(source)) as document:
        for item in items:
            page = document[item["page"] - 1]
            clip = None
            if item.get("box"):
                b = item["box"]
                clip = pymupdf.Rect(b["x0"] - 24, b["y0"] - 24, b["x1"] + 24, b["y1"] + 24)
                clip &= page.rect
                if clip.is_empty:
                    clip = None
            pixmap = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
            (folder / Path(item["crop"]).name).write_bytes(pixmap.tobytes("png"))
