"""Book-level figures after lists: links, spreads, names, measured kind and image export.

Page links come from each page's layout and final units/order (``figures.page``). Spreads
and names are whole-book decisions, so page records are written once every page is linked;
a partial cache is recomputed. Images are rendered through the Extractor, cropped to the
figure box, encoded per the measured kind and stored with the cache; the final archive
copies them. No stage reads figure records back: units, order and the ledger are unchanged.
"""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import cv2

from book_core.atomic import replace_with_retry
from book_core.cache_store import read_model, write_model
from book_core.caching import assert_producer_unchanged, code_digest
from book_core.extraction.fingerprints import stable_id
from book_core.figures import imaging
from book_core.figures.evidence import MODEL_DISAGREES, disagrees, supported
from book_core.figures.models import (
    AltText,
    BookFigures,
    FigureRecord,
    PageFigures,
    Spread,
)
from book_core.figures.names import assign_names
from book_core.figures.page import (
    caption_openings,
    label_votes,
    link_numbered,
    link_page,
    numbered_candidates,
    page_credits,
    require_numbers,
)
from book_core.figures.settings import FigureSettings
from book_core.figures.spreads import candidates, continuous
from book_core.model.common import BBox, Provenance

VERSION = "figures-2"
CONFIG = {
    "caption_gap_font_sizes": 2.0,
    "caption_box_lines": 8,
    "label_min_captions": 3,
    "label_share": 0.3,
    "page_scale_share": 0.5,
    "spread_edge_share": 0.02,
    "spread_vertical_overlap": 0.8,
    "kind": {
        "raster": imaging.RASTER,
        "vector": imaging.VECTOR,
        "photo_dominant": imaging.PHOTO_DOMINANT,
        "drawing_dominant": imaging.DRAWING_DOMINANT,
        "drawing_flat": imaging.DRAWING_FLAT,
        "quantize_bits": imaging.QUANTIZE_BITS,
        "flat_gradient": imaging.FLAT_GRADIENT,
    },
}
LOADED_DIGEST = code_digest("figures")
PAGE_SCALE = "figure region covers at least half the content area; grouping needs review"


def figures_fingerprint(lists_key, settings, model_identity=None):
    return stable_id(
        lists_key,
        json.dumps(model_identity or {}, sort_keys=True),
        code_digest("figures"),
        VERSION,
        json.dumps(CONFIG, sort_keys=True),
        settings.model_dump_json(),
        "opencv-" + cv2.__version__,
    )


def _union(a, b):
    return BBox(x0=min(a.x0, b.x0), y0=min(a.y0, b.y0), x1=max(a.x1, b.x1), y1=max(a.y1, b.y1))


def analyze_book_figures(
    source,
    pages,
    layout_of,
    built_of,
    objects_of,
    markers,
    lists_key,
    cache_dir,
    total,
    extractor,
    settings=None,
    generator=None,
    model_figures=None,
):
    """Figure records for every page; returns (key, BookFigures).

    ``model_figures(number)``: {model: [figure boxes]} layout-model evidence, required when
    the settings turn it on; figures the models do not support are flagged, never dropped.

    ``objects_of(number, ids)``: [(id, kind, bbox)] of the named native objects;
    ``markers``: {page: (label, source)} from the Step 8 page labels;
    ``generator``: an optional alt-text draft generator (used only when the settings ask).
    """
    settings = settings or FigureSettings()
    assert_producer_unchanged("figures", LOADED_DIGEST)
    if settings.model_evidence == "auto":
        raise ValueError("Resolve model_evidence (figures.evidence.resolve) before the stage")
    if (settings.model_evidence == "on") != (model_figures is not None):
        raise ValueError("Layout-model evidence must be supplied exactly when it is on")
    key = figures_fingerprint(
        lists_key, settings, model_figures.identity if model_figures is not None else None
    )
    directory = Path(cache_dir) / "figures" / key
    paths = {n: directory / f"{n}.json" for n in range(1, total + 1)}
    book_path = directory / "book.json"
    if book_path.exists() and all(path.exists() for path in paths.values()):
        return key, read_model(book_path, BookFigures, key)
    if settings.alt_text_drafts and generator is None:
        raise ValueError("Alt-text drafts are on but no generator was supplied")
    linked, contents, digest = {}, {}, None
    votes, numbered, openings = Counter(), {}, {}
    for page in pages():
        number = page.geometry.page
        digest = page.source_sha256
        layout = layout_of(page)
        built = built_of(number)
        drafts, unlinked = link_page(layout, built)
        linked[number] = (drafts, unlinked)
        contents[number] = layout.content_bbox
        votes.update(label_votes(drafts, page.store, layout, built))
        numbered[number] = numbered_candidates(drafts, page.store, layout, built)
        openings[number] = caption_openings(drafts, page.store, layout, built)
    if sorted(linked) != list(paths):
        raise ValueError("Figure links have incomplete page coverage")
    # Caption labels are learned from the book's own linked captions, never from a list.
    voted = sum(votes.values())
    labels = sorted(
        word
        for word, count in votes.items()
        if word and count >= CONFIG["label_min_captions"] and count >= CONFIG["label_share"] * voted
    )
    for number, (drafts, unlinked) in linked.items():
        require_numbers(drafts, unlinked, openings[number], set(labels))
        link_numbered(drafts, unlinked, numbered[number], set(labels))
    ids = {
        (n, d.region.id): stable_id("figure-record", digest, n, d.region.id)
        for n, (drafts, _) in linked.items()
        for d in drafts
    }
    credits_of = {
        n: page_credits(drafts, lambda d, n=n: ids[n, d.region.id])
        for n, (drafts, _) in linked.items()
    }
    by_id = {}
    for n, (drafts, _) in sorted(linked.items()):
        if not drafts:
            continue
        raster = extractor.render_page(source, n, settings.export_dpi)
        rgb = imaging.decode_png(raster.png)
        scale = raster.width / raster.page_width
        found = model_figures(n) if model_figures is not None else None
        for d in drafts:
            fid = ids[n, d.region.id]
            object_ids = sorted(d.block.object_ids if d.block else d.region.object_ids)
            objects = objects_of(n, object_ids)
            image_boxes = [bbox for _, kind, bbox in objects if kind == "image" and bbox]
            vectors = sum(kind != "image" for _, kind, _ in objects)
            crop = imaging.crop(rgb, scale, d.region.bbox)
            kind, fmt, confidence, evidence, kind_flags = imaging.decide(
                d.region.bbox, crop, image_boxes, vectors
            )
            by_id[fid] = {
                "page": n, "draft": d, "kind": kind, "format": fmt,
                "edges": (crop[:, :2].copy(), crop[:, -2:].copy()),
                "confidence": confidence, "evidence": evidence, "flags": list(kind_flags),
                "object_ids": object_ids,
            }  # fmt: skip
            if found is not None:
                support = {name: supported(d.region.bbox, boxes) for name, boxes in found.items()}
                by_id[fid]["support"] = support
                if disagrees(support, settings.model_disagreement):
                    by_id[fid]["flags"].append(MODEL_DISAGREES)
        del rgb, raster
    spreads, taken = [], set()
    for a, left, b, right, geometry in candidates(
        {n: drafts for n, (drafts, _) in linked.items()},
        contents,
        CONFIG["spread_edge_share"],
        CONFIG["spread_vertical_overlap"],
    ):
        first, second = ids[a, left.region.id], ids[b, right.region.id]
        if first in taken or second in taken:
            continue
        ok, pixels = continuous(
            by_id[first]["edges"][1],
            left.region.bbox,
            by_id[second]["edges"][0],
            right.region.bbox,
        )
        if not ok:
            continue
        taken.update({first, second})
        spreads.append(
            Spread(
                figure_ids=[first, second],
                pages=[a, b],
                confidence=0.7,
                reasons=[
                    "figures meet the facing content edges, align vertically and their "
                    "pixels continue across the gutter"
                ],
                evidence={**geometry, **pixels},
            )
        )
    partner = {}
    for spread in spreads:
        first, second = spread.figure_ids
        partner[first], partner[second] = second, first
    second_halves = {spread.figure_ids[1] for spread in spreads}
    entries = []
    for n, (drafts, _) in sorted(linked.items()):
        label, label_source = markers.get(n, (None, "none"))
        for d in drafts:
            if ids[n, d.region.id] not in second_halves:
                entries.append(
                    (ids[n, d.region.id], n, label, label_source, d.anchor.reading_index)
                )
    names = assign_names(entries, settings)
    images = directory / "images"
    records = {n: [] for n in linked}
    for spread in spreads:
        first, second = (by_id[i] for i in spread.figure_ids)
        if first["kind"] != second["kind"]:
            first["flags"].append("spread halves disagree on photo/drawing; review")
    rendered = {}

    def pixels_of(fid):
        """Second pass: re-render (at most two pages held) and crop one figure."""
        item = by_id[fid]
        n = item["page"]
        if n not in rendered:
            if len(rendered) >= 2:
                rendered.pop(min(rendered))
            raster = extractor.render_page(source, n, settings.export_dpi)
            rendered[n] = (imaging.decode_png(raster.png), raster.width / raster.page_width)
        rgb, scale = rendered[n]
        return imaging.crop(rgb, scale, item["draft"].region.bbox)

    def export_pixels(fid):
        crop = pixels_of(fid)
        if fid not in partner:
            return crop
        twin = pixels_of(partner[fid])
        height = max(crop.shape[0], twin.shape[0])
        return cv2.hconcat([_pad(crop, height), _pad(twin, height)])

    for fid, item in by_id.items():
        n, d = item["page"], item["draft"]
        start = partner.get(fid) if fid in second_halves else fid
        stem, label, inferred, name_flags = names[start]
        label_source = markers.get(by_id[start]["page"], (None, "none"))[1]
        exported, alt = None, AltText()
        if fid not in second_halves:
            pixels = export_pixels(fid)
            fmt = item["format"]
            data = imaging.encode(pixels, fmt, settings.jpeg_quality)
            exported = imaging.exported(stem, fmt, settings.export_dpi, pixels, data)
            if settings.export_images:
                write_bytes(images / exported.file_name, data)
            if settings.alt_text_drafts:
                alt = generator.describe(pixels)
        flags = [*item["flags"], *name_flags, *d.flags]
        content = contents[n]
        box = d.region.bbox
        share = ((box.x1 - box.x0) * (box.y1 - box.y0)) / max(
            1e-6, (content.x1 - content.x0) * (content.y1 - content.y0)
        )
        if share >= CONFIG["page_scale_share"]:
            flags.append(PAGE_SCALE)
        records[n].append(
            FigureRecord(
                id=fid,
                page=n,
                pages=sorted({n, by_id[partner[fid]]["page"]}) if fid in partner else [n],
                region_ids=[d.region.id],
                block_ids=[d.block.id] if d.block else [],
                object_ids=item["object_ids"],
                bbox=d.region.bbox,
                content_area_share=round(min(1.0, share), 6),
                small_artwork=share < settings.small_figure_share,
                page_label=label,
                label_source="none" if label is None else label_source,
                label_inferred=inferred,
                name=stem,
                kind=item["kind"],
                kind_confidence=item["confidence"],
                image=exported,
                evidence=item["evidence"],
                captions=d.captions,
                credits=d.credits,
                internal_text=d.internal,
                anchor=d.anchor,
                alt_text=alt,
                model_support=item.get("support", {}),
                spread_partner_id=partner.get(fid),
                confidence=round(min(d.region.confidence, item["confidence"]), 4),
                reasons=[*d.region.reasons, *d.reasons],
                review_flags=flags,
            )
        )
    for second in second_halves:
        first = partner[second]
        first_page = by_id[first]["page"]
        record = next(r for r in records[first_page] if r.id == first)
        twin = next(r for r in records[by_id[second]["page"]] if r.id == second)
        records[by_id[second]["page"]] = [
            r.model_copy(update={"image": record.image, "name": record.name}) if r is twin else r
            for r in records[by_id[second]["page"]]
        ]
    inputs = {
        "lists_key": lists_key,
        "producer": LOADED_DIGEST,
        "configuration": json.dumps(CONFIG, sort_keys=True),
        "settings": settings.model_dump_json(),
        "version": VERSION,
    }
    assert_producer_unchanged("figures", LOADED_DIGEST)
    for n, (_, unlinked) in linked.items():
        write_model(
            paths[n],
            PageFigures(
                source_sha256=digest,
                page=n,
                figures_version=VERSION,
                figures=records[n],
                unlinked_captions=unlinked,
                page_credits=credits_of[n],
                cache_key_inputs=inputs,
                provenance=Provenance(
                    source_sha256=digest, engine="figures", engine_version=VERSION, method="derived"
                ),
            ),
            key,
        )
    all_records = [r for rows in records.values() for r in rows]
    book = BookFigures(
        source_sha256=digest,
        figures_version=VERSION,
        pages=total,
        spreads=spreads,
        names={stem: fid for fid, (stem, *_rest) in names.items()},
        profile={
            "figures": len(all_records),
            "images": sum(r.image is not None for r in all_records if r.id not in second_halves),
            "photos": sum(r.kind == "photo" for r in all_records),
            "drawings": sum(r.kind == "drawing" for r in all_records),
            "png_uncertain": sum(imaging.UNCERTAIN in r.review_flags for r in all_records),
            "spreads": len(spreads),
            "captions_linked": sum(len(r.captions) for r in all_records),
            "credits_linked": len({c.unit_id for r in all_records for c in r.credits}),
            "page_credits": sum(len(c) for c in credits_of.values()),
            "internal_text_units": sum(len(r.internal_text) for r in all_records),
            "unlinked_captions": sum(len(u) for _, u in linked.values()),
            "caption_labels": labels,
            "caption_links_by_rule": dict(
                Counter(c.rule for r in all_records for c in r.captions).most_common()
            ),
            "page_credit_proposals_by_rule": dict(
                Counter(c.rule for rows in credits_of.values() for c in rows).most_common()
            ),
            "unlabelled_names": sum(r.label_source == "none" for r in all_records),
            "inferred_labels": sum(r.label_inferred for r in all_records),
            "page_scale_regions": sum(PAGE_SCALE in r.review_flags for r in all_records),
            "small_artwork": sum(r.small_artwork for r in all_records),
            "model_disagrees": sum(MODEL_DISAGREES in r.review_flags for r in all_records),
            "unlinked_caption_reasons": dict(
                Counter(c.reason for _, u in linked.values() for c in u).most_common()
            ),
            "image_bytes": sum(
                r.image.bytes for r in all_records if r.image and r.id not in second_halves
            ),
        },
        config=CONFIG,
        cache_key_inputs=inputs,
        provenance=Provenance(
            source_sha256=digest, engine="figures", engine_version=VERSION, method="derived"
        ),
    )
    write_model(book_path, book, key)
    return key, book


def write_bytes(path, data):
    """Atomic file write (temporary file in the same directory, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        replace_with_retry(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _pad(rgb, height):
    if rgb.shape[0] == height:
        return rgb
    return cv2.copyMakeBorder(
        rgb, 0, height - rgb.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)
    )


def load_page(cache_dir, key, number):
    return read_model(Path(cache_dir) / "figures" / key / f"{number}.json", PageFigures, key)


def load_book(cache_dir, key):
    return read_model(Path(cache_dir) / "figures" / key / "book.json", BookFigures, key)


def image_path(cache_dir, key, file_name):
    return Path(cache_dir) / "figures" / key / "images" / file_name
