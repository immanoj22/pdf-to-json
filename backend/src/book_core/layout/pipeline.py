"""Page layout proposals: visual lines, scopes, per-band columns and typed regions.

Inputs are the cached Step 3 object analysis and an extractor-rendered raster. Outputs are
proposals with confidence and reasons; nothing here claims reading order or paragraphs.
"""

import json
from importlib.metadata import version
from pathlib import Path

import cv2

from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.layout.bands import segment_scope
from book_core.layout.blocks import area, build_blocks, contains, expand, short_label, union
from book_core.layout.lines import build_lines
from book_core.layout.models import PageLayout, ReviewFlag, Scope
from book_core.layout.regions import (
    Group,
    dominant_style,
    embedded,
    group_lane,
    locate,
    make_region,
    median_pitch,
    merge_main_text,
    type_groups,
)
from book_core.model.common import Provenance
from book_core.objects.analysis import analyze_page, atomic_write, fingerprints, verified_read
from book_core.objects.roles import raster_array

LAYOUT_VERSION = "layout-proposals-1"
SCALE = 2.0


def ownership(lines, blocks, store, content):
    """Each visual line gets exactly one owner before segmentation."""
    figures = [b for b in blocks if b.kind == "figure"]
    tables = [b for b in blocks if b.kind == "table"]
    callouts = [b for b in blocks if b.kind == "callout"]
    owner = {}
    # Labels chain outward from artwork: a label next to an embedded label is embedded too.
    reach = {figure.id: figure for figure in figures}
    changed = True
    while changed:
        changed = False
        for line in lines:
            if line.id in owner or not line.inside_content or line.blank or not line.visible:
                continue
            figure = next(
                (
                    f
                    for f in figures
                    if embedded(line, f, store)
                    or (
                        short_label(line, store)
                        and expand(
                            reach[f.id].bbox, max(12.0, 1.2 * line.font_size)
                        ).contains_center(line.bbox)
                    )
                ),
                None,
            )
            if figure is not None:
                owner[line.id] = ("figure", figure.id)
                grown = union([reach[figure.id].bbox, line.bbox])
                reach[figure.id] = reach[figure.id].model_copy(update={"bbox": grown})
                changed = True
    for line in lines:
        if line.id in owner:
            continue
        if not line.inside_content:
            owner[line.id] = ("artifact", None)
        elif line.blank:
            owner[line.id] = ("blank", None)
        elif not line.visible:
            owner[line.id] = ("invisible", None)
        elif table := next((t for t in tables if contains(t.bbox, line.bbox, tolerance=2)), None):
            owner[line.id] = ("table", table.id)
        elif not line.horizontal:
            owner[line.id] = ("rotated", None)
        else:
            inside = [c for c in callouts if c.bbox.contains_center(line.bbox)]
            target = min(inside, key=lambda c: area(c.bbox)) if inside else None
            owner[line.id] = ("scope", target.id if target else None)
    return owner


def build_layout(analysis, raster, resolved_device="cpu"):
    native = analysis.native
    page = native.page
    store = page.store
    content = page.geometry.content_bbox
    array = raster_array(raster)
    scale = raster.width / raster.page_width
    lines = build_lines(native)
    blocks, diagnostics = build_blocks(analysis, lines, array, scale)
    owner = ownership(lines, blocks, store, content)
    by_id = {line.id: line for line in lines}
    # Embedded lines are recorded on their figure or table blocks.
    blocks = [
        block.model_copy(
            update={
                "line_ids": [lid for lid, (kind, target) in owner.items() if target == block.id]
            }
        )
        if block.kind in {"figure", "table"}
        else block
        for block in blocks
    ]
    callouts = [b for b in blocks if b.kind == "callout"]
    page_scope = Scope(
        id=stable_id(page.source_sha256, page.geometry.page, "scope"), kind="page", bbox=content
    )
    scope_of_block = {}

    def enclosing(bbox, exclude=None):
        inside = [
            c
            for c in callouts
            if c.id != exclude and contains(c.bbox, bbox) and area(c.bbox) > area(bbox) * 1.0001
        ]
        return min(inside, key=lambda c: area(c.bbox)) if inside else None

    scopes = [page_scope]
    scope_ids = {None: page_scope.id}
    for callout in sorted(callouts, key=lambda c: -area(c.bbox)):
        parent = enclosing(callout.bbox, exclude=callout.id)
        scope = Scope(
            id=stable_id("scope", callout.id),
            kind="callout",
            bbox=callout.bbox,
            parent_id=scope_ids[parent.id if parent else None],
            block_id=callout.id,
        )
        scopes.append(scope)
        scope_ids[callout.id] = scope.id
    for block in blocks:
        parent = enclosing(block.bbox, exclude=block.id)
        scope_of_block[block.id] = scope_ids[parent.id if parent else None]
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    frames = [
        obj.bbox
        for obj in analysis.all_objects()
        if obj.bbox is not None
        and obj.kind == "drawing"
        and obj.stroke is not None
        and obj.fill is None
        and any(item.operator == "re" for item in obj.path_items)
    ]
    sizes = [line.font_size for line in lines if not line.blank and line.font_size > 0]
    free_lines = [by_id[lid] for lid, (kind, _) in owner.items() if kind == "scope"]
    bands = []
    membership = {}
    for scope in scopes:
        scope_lines = [
            by_id[lid]
            for lid, (kind, target) in owner.items()
            if kind == "scope" and scope_ids[target] == scope.id
        ]
        scope_blocks = [b for b in blocks if scope_of_block[b.id] == scope.id]
        chars = sum(len(store.spans[s].raw_text.strip()) for m in scope_lines for s in m.span_ids)
        body = dominant_style(scope_lines if chars >= 200 else free_lines, store)
        body_ids = frozenset(
            line.id for line in scope_lines if dominant_style([line], store) == body
        )
        x0, y0 = round(scope.bbox.x0 * scale), round(scope.bbox.y0 * scale)
        x1, y1 = round(scope.bbox.x1 * scale) + 1, round(scope.bbox.y1 * scale) + 1
        found, placed, notes = segment_scope(
            scope, scope_lines, scope_blocks, edges[y0:y1, x0:x1], scale, sizes, frames, body_ids
        )
        bands.extend(found)
        membership.update(placed)
        diagnostics.extend(notes)
    regions = build_regions(
        lines,
        blocks,
        owner,
        scopes,
        scope_ids,
        scope_of_block,
        bands,
        membership,
        store,
        content,
        page_scope,
    )
    flags = review_flags(analysis, bands, regions)
    return PageLayout(
        source_sha256=page.source_sha256,
        page=page.geometry.page,
        layout_version=LAYOUT_VERSION,
        content_bbox=content,
        lines=lines,
        blocks=blocks,
        scopes=scopes,
        bands=bands,
        regions=regions,
        review_flags=flags,
        diagnostics=diagnostics,
        provenance=Provenance(
            source_sha256=page.source_sha256,
            engine="book_core.layout",
            engine_version=LAYOUT_VERSION,
            method="derived",
            resolved_device=resolved_device,
            execution_device="cpu",
        ),
    )


def build_regions(
    lines,
    blocks,
    owner,
    scopes,
    scope_ids,
    scope_of_block,
    bands,
    membership,
    store,
    content,
    page_scope,
):
    by_id = {line.id: line for line in lines}
    regions = []
    pitch = median_pitch(lines)
    figures = [b for b in blocks if b.kind == "figure"]
    rules = [b for b in blocks if b.kind == "rule"]
    free = [by_id[lid] for lid, (kind, _) in owner.items() if kind == "scope"]
    body_style = dominant_style(free, store)
    scope_body = {}
    scope_width = {}
    for scope in scopes:
        members = [
            by_id[lid]
            for lid, (kind, target) in owner.items()
            if kind == "scope" and scope_ids[target] == scope.id
        ]
        chars = sum(len(store.spans[sid].raw_text.strip()) for m in members for sid in m.span_ids)
        scope_body[scope.id] = dominant_style(members, store) if chars >= 200 else body_style
        scope_width[scope.id] = (
            max(m.bbox.x1 for m in members) - min(m.bbox.x0 for m in members)
            if members
            else scope.bbox.x1 - scope.bbox.x0
        )
    page_bands = [b for b in bands if b.scope_id == page_scope.id]
    banners = {b.id for b in blocks if b.kind == "banner"}
    # Text printed on a banner is not the page title band.
    text_bands = [
        b
        for b in page_bands
        if any(lane.line_count for lane in b.lanes)
        and not any(set(lane.block_ids) & banners for lane in b.lanes)
    ]
    top_band = min(text_bands, key=lambda b: b.bbox.y0).id if text_bands else None
    groups = []
    placed = {}
    for lid, (kind, _) in owner.items():
        if kind == "scope" and lid in membership:
            band, lane = membership[lid]
            placed.setdefault((id(band), id(lane)), (band, lane, []))[2].append(by_id[lid])
    for band, lane, lane_lines in placed.values():
        if lane is not None:
            for members in group_lane(lane_lines, store, pitch):
                groups.append(
                    Group(
                        lines=members,
                        scope_id=band.scope_id,
                        band=band,
                        lane=lane,
                        style=dominant_style(members, store),
                    )
                )
    claimed = {line.id for group in groups for line in group.lines}
    leftovers = [
        by_id[lid] for lid, (kind, _) in owner.items() if kind == "scope" and lid not in claimed
    ]
    for line in leftovers:
        scope_id = scope_ids[owner[line.id][1]]
        band, lane = locate(bands, scope_id, line.bbox)
        groups.append(
            Group(
                lines=[line],
                scope_id=scope_id,
                band=band,
                lane=lane,
                style=dominant_style([line], store),
            )
        )

    def lane_lines_of(group):
        return [
            line
            for other in groups
            if other.lane is group.lane and other.band is group.band
            for line in other.lines
        ]

    def isolated_above(group):
        box = group.bbox
        above = [
            line.bbox.y1
            for line in lane_lines_of(group)
            if line not in group.lines and line.bbox.y1 <= box.y0 + 0.5
        ]
        return not above or box.y0 - max(above) >= 0.5 * pitch

    def between(rule, group):
        """Another text block sits between the rule and this group."""
        box = group.bbox
        return any(
            other is not group
            and other.bbox.y0 >= rule.bbox.y1 - 1
            and other.bbox.y1 <= box.y0 + 1
            and min(other.bbox.x1, rule.bbox.x1) > max(other.bbox.x0, rule.bbox.x0)
            for other in groups
        )

    def body_below(group):
        box = group.bbox
        scope_style = scope_body.get(group.scope_id) or body_style
        return any(
            other is not group
            and other.lane is group.lane
            and other.band is group.band
            and other.style == scope_style
            and 0 <= other.bbox.y0 - box.y1 <= 2 * pitch
            for other in groups
        )

    type_groups(
        groups,
        {
            "store": store,
            "content": content,
            "body_style": body_style,
            "scope_body": scope_body,
            "scope_width": scope_width,
            "figures": figures,
            "rules": rules,
            "top_band": top_band,
            "page_scope": page_scope.id,
            "pitch": pitch,
            "isolated_above": isolated_above,
            "between": between,
            "body_below": body_below,
        },
    )
    for group in merge_main_text(groups, pitch):
        regions.append(
            make_region(
                group.type,
                group.lines,
                group.scope_id,
                group.band,
                group.lane,
                group.confidence,
                group.reasons,
                group.evidence,
            )
        )
    for line in lines:
        kind, target = owner[line.id]
        if kind == "scope" or kind in {"figure", "table"}:
            continue
        band, lane = locate(bands, page_scope.id, line.bbox)
        if kind == "artifact":
            spec = ("artifact_candidate", 0.9, ["Line centre outside the explicit printed TrimBox"])
        elif kind == "blank":
            spec = ("artifact_candidate", 0.9, ["Whitespace-only native line; carries no tokens"])
        elif kind == "invisible":
            spec = ("unknown", 0.4, ["Invisible text layer; review before use"])
        else:
            small = body_style is None or line.font_size <= 1.05 * body_style[1]
            spec = (
                ("credit_candidate", 0.75, ["Rotated small text outside figures"])
                if small
                else ("unknown", 0.45, ["Rotated text that is not small; review"])
            )
        regions.append(
            make_region(
                spec[0],
                [line],
                page_scope.id,
                band,
                lane,
                spec[1],
                spec[2],
                {"rotation": line.rotation},
            )
        )
    for block in blocks:
        if block.kind not in {"figure", "table"}:
            continue
        members = [by_id[lid] for lid in block.line_ids]
        scope_id = scope_of_block[block.id]
        bbox = union([block.bbox, *(line.bbox for line in members)])
        band, lane = membership.get(block.id) or locate(bands, scope_id, bbox)
        regions.append(
            make_region(
                "figure" if block.kind == "figure" else "table_candidate",
                members,
                scope_id,
                band,
                lane,
                block.confidence,
                list(block.reasons),
                {"embedded_lines": len(members), **block.features},
                bbox=bbox,
                object_ids=block.object_ids,
            )
        )
    by_scope = {}
    for region in regions:
        by_scope.setdefault(region.scope_id, []).append(region.id)
    for scope in scopes:
        if scope.kind != "callout":
            continue
        block = next(b for b in blocks if b.id == scope.block_id)
        band, lane = membership.get(block.id) or locate(bands, scope.parent_id, block.bbox)
        regions.append(
            make_region(
                "callout",
                [],
                scope.parent_id,
                band,
                lane,
                block.confidence,
                list(block.reasons),
                {"lane_kind": lane.kind if lane is not None else None},
                bbox=block.bbox,
                object_ids=block.object_ids,
                child_region_ids=sorted(by_scope.get(scope.id, [])),
            )
        )
    return regions


def review_flags(analysis, bands, regions):
    """Unknown visual objects never block processing; each is listed for review."""
    flags = [
        ReviewFlag(
            subject_id=record.object_id, subject_kind="visual_object", reason=record.reasons[0]
        )
        for record in analysis.asset_ledger.records
        if record.role == "unknown"
    ]
    flags += [
        ReviewFlag(subject_id=band.id, subject_kind="band", reason="; ".join(band.reasons))
        for band in bands
        if band.review_required
    ]
    flags += [
        ReviewFlag(subject_id=region.id, subject_kind="region", reason=region.reasons[-1])
        for region in regions
        if region.review_required
    ]
    return flags


def layout_fingerprint(analysis_fingerprint, resolved_device):
    dependencies = {
        name: version(name) for name in ["opencv-python-headless", "numpy", "shapely", "regex"]
    }
    return stable_id(
        analysis_fingerprint,
        LAYOUT_VERSION,
        f"scale-{SCALE}",
        json.dumps(dependencies, sort_keys=True),
        resolved_device,
    )


def analyze_layout(source, page_number, extractor, repetition=None, cache_dir=None):
    """Cached layout proposals for one page plus the object analysis they derive from."""
    source = Path(source)
    analysis = analyze_page(source, page_number, extractor, repetition, cache_dir)
    digest = source_digest(source)
    _, analysis_fingerprint = fingerprints(digest, extractor, repetition)
    fingerprint = layout_fingerprint(analysis_fingerprint, extractor.device.resolved)
    path = (
        Path(cache_dir) / "layout" / fingerprint / f"{page_number}.json"
        if cache_dir is not None
        else None
    )
    if path is not None and path.exists():
        layout = verified_read(path, PageLayout, fingerprint)
        if layout.source_sha256 != digest or layout.page != page_number:
            raise ValueError("Layout cache belongs to another source or page")
        return layout, analysis
    raster = extractor.render_page(source, page_number, dpi=round(72 * SCALE))
    layout = build_layout(analysis, raster, extractor.device.resolved)
    if path is not None:
        atomic_write(path, layout, fingerprint)
    return layout, analysis
