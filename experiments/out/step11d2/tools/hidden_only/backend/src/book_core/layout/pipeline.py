"""Page layout proposals: visual lines, scopes, per-band columns and typed regions.

Inputs are the cached Step 3 object analysis and an extractor-rendered raster. Outputs are
proposals with confidence and reasons; nothing here claims reading order or paragraphs.

Figures embed only label-like text: paragraph-like lines (several words in the body style,
or a wrapped/justified sequence) and lines in the page's furniture zones stay in the flow.
Lines sharing a right-angle rotation (at least three) are analysed in their own reading
frame with the same table, band, lane and region rules, then mapped back to the page; a
single rotated line keeps the credit rule for isolated rotated text.
"""

import json
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import cv2

from book_core.caching import assert_producer_unchanged, code_digest
from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.layout.bands import segment_scope
from book_core.layout.blocks import (
    aligned_blocks,
    area,
    build_blocks,
    contains,
    expand,
    short_label,
    union,
)
from book_core.layout.evidence import (
    ROTATED_STRUCTURE_LINES,
    credit_like,
    page_body_style,
    paragraph_like,
    rotation_key,
    text_lines,
)
from book_core.layout.frames import frame_block, frame_line, from_frame, right_angle, to_frame
from book_core.layout.lines import build_lines
from book_core.layout.models import PageLayout, ReviewFlag, Scope
from book_core.layout.regions import (
    EDGE_ZONE,
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
from book_core.layout.tables import aligned_tables
from book_core.model.common import Provenance
from book_core.objects.analysis import analyze_page, atomic_write, fingerprints, verified_read
from book_core.objects.roles import raster_array
from book_core.paint.cache import page_paint, paint_fingerprint

LAYOUT_VERSION = "layout-proposals-2"
SCALE = 2.0
LOADED_CODE_DIGEST = code_digest("layout")


def furniture_zone(line, content):
    height = content.y1 - content.y0
    centre = (line.bbox.y0 + line.bbox.y1) / 2
    return centre <= content.y0 + EDGE_ZONE * height or centre >= content.y1 - EDGE_ZONE * height


def ownership(lines, blocks, store, content, body=None, neighbours=()):
    """Each visual line gets exactly one owner before segmentation."""
    figures = [b for b in blocks if b.kind == "figure"]
    tables = [b for b in blocks if b.kind == "table"]
    callouts = [b for b in blocks if b.kind == "callout"]
    owner = {}
    # Running text and page furniture never become embedded figure text.
    held = {
        line.id
        for line in lines
        if not line.blank
        and (furniture_zone(line, content) or paragraph_like(line, store, body, neighbours))
    }
    # Labels chain outward from artwork: a label next to an embedded label is embedded too.
    reach = {figure.id: figure for figure in figures}
    changed = True
    while changed:
        changed = False
        for line in lines:
            if (
                line.id in owner
                or line.id in held
                or not line.inside_content
                or line.blank
                or not line.visible
            ):
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
    # Rotated lines sharing a right angle form structure in their own reading frame.
    shared = {}
    for line in lines:
        if line.id in owner or line.blank or not line.visible or not line.inside_content:
            continue
        if not line.horizontal and (angle := right_angle(line.rotation)) is not None:
            shared.setdefault(angle, []).append(line.id)
    structural = {
        lid: angle
        for angle, ids in shared.items()
        if len(ids) >= ROTATED_STRUCTURE_LINES
        for lid in ids
    }
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
        elif line.id in structural:
            owner[line.id] = ("frame", structural[line.id])
        elif not line.horizontal:
            owner[line.id] = ("rotated", None)
        else:
            inside = [c for c in callouts if c.bbox.contains_center(line.bbox)]
            target = min(inside, key=lambda c: area(c.bbox)) if inside else None
            owner[line.id] = ("scope", target.id if target else None)
    return owner


def build_layout(analysis, raster, resolved_device="cpu", paint_evidence=None):
    native = analysis.native
    page = native.page
    store = page.store
    content = page.geometry.content_bbox
    array = raster_array(raster)
    scale = raster.width / raster.page_width
    proofs = paint_evidence.spans if paint_evidence is not None else []
    invisible = {p.span_id for p in proofs if p.decision == "invisible"}
    lines = build_lines(native, invisible)
    blocks, diagnostics = build_blocks(analysis, lines, array, scale)
    body = page_body_style(lines, store)
    neighbours = [line for line in text_lines(lines) if line.horizontal]
    owner = ownership(lines, blocks, store, content, body, neighbours)
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
    # The same tolerance the PageLayout validator applies to band overlaps (I2).
    ordered = sorted(line.font_size for line in lines if not line.blank)
    tolerance = max(1.0, 0.5 * ordered[len(ordered) // 2]) if ordered else 1.0
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
            scope,
            scope_lines,
            scope_blocks,
            edges[y0:y1, x0:x1],
            scale,
            sizes,
            frames,
            body_ids,
            store=store,
            overlap_tolerance=tolerance,
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
    for angle in sorted({target for kind, target in owner.values() if kind == "frame"}):
        members = [
            by_id[lid]
            for lid, (kind, target) in owner.items()
            if (kind, target) == ("frame", angle)
        ]
        scope, frame_bands, frame_regions, frame_tables, notes = analyse_frame(
            angle,
            members,
            lines,
            blocks,
            store,
            page_scope,
            edges,
            scale,
            sizes,
            frames,
            tolerance,
            body,
        )
        scopes.append(scope)
        bands.extend(frame_bands)
        regions.extend(frame_regions)
        blocks.extend(frame_tables)
        diagnostics.extend(notes)
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
        review_flags=flags
        + [
            ReviewFlag(subject_id=p.span_id, subject_kind="span", reason=p.reason)
            for p in proofs
            if p.needs_review
        ],
        visibility_evidence=proofs,
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


def frame_edges(edges, page_box, angle, scale):
    """Rendered edges under a page box, re-oriented into a reading frame."""
    height, width = edges.shape
    x0, y0 = max(0, int(page_box.x0 * scale)), max(0, int(page_box.y0 * scale))
    x1, y1 = min(width, int(page_box.x1 * scale) + 1), min(height, int(page_box.y1 * scale) + 1)
    crop = edges[y0:y1, x0:x1]
    if angle == 90:
        return crop.T[:, ::-1]
    if angle == 270:
        return crop.T[::-1, :]
    if angle == 180:
        return crop[::-1, ::-1]
    return crop


def intersects(a, b):
    return a.x0 <= b.x1 and a.x1 >= b.x0 and a.y0 <= b.y1 and a.y1 >= b.y0


def analyse_frame(
    angle, members, lines, blocks, store, page_scope, edges, scale, sizes, frames, tolerance, body
):
    """Bands, lanes, tables and regions for lines sharing one right-angle rotation."""
    notes = [f"{len(members)} lines rotated {angle} degrees analysed in their own frame"]
    frame = [frame_line(line, angle) for line in members]
    extent = union(line.bbox for line in members)
    font_unit = sorted(line.font_size for line in members)[len(members) // 2]
    zone = expand(extent, 2 * font_unit)
    context = [
        frame_block(block, angle)
        for block in blocks
        if block.kind in {"figure", "table", "rule"} and intersects(block.bbox, zone)
    ]
    tables = aligned_blocks(aligned_tables(frame, store, body))
    owner = {}
    for line in frame:
        table = next((t for t in tables if contains(t.bbox, line.bbox, tolerance=2)), None)
        owner[line.id] = ("table", table.id) if table else ("scope", None)
    frame_box = expand(
        union([*(line.bbox for line in frame), *(t.bbox for t in tables)]), font_unit
    )
    scope_id = stable_id(page_scope.id, "rotated", angle)
    working = Scope(
        id=scope_id, kind="rotated", bbox=frame_box, parent_id=page_scope.id, rotation=angle
    )
    free = [line for line in frame if owner[line.id][0] == "scope"]
    chars = sum(len(store.spans[s].raw_text.strip()) for m in free for s in m.span_ids)
    scope_body = dominant_style(free, store) if chars >= 200 else body
    body_ids = frozenset(line.id for line in free if dominant_style([line], store) == scope_body)
    segment_blocks = [*tables, *context]
    found, placed, more = segment_scope(
        working,
        free,
        segment_blocks,
        frame_edges(edges, from_frame(frame_box, angle), angle, scale),
        scale,
        sizes,
        [to_frame(f, angle) for f in frames],
        body_ids,
        store=store,
        overlap_tolerance=tolerance,
    )
    notes.extend(more)
    regions = build_regions(
        frame,
        segment_blocks,
        owner,
        [working],
        {None: scope_id},
        {block.id: scope_id for block in segment_blocks},
        found,
        placed,
        store,
        frame_box,
        working,
        own_blocks={table.id for table in tables},
        furniture=False,
    )
    page_lines = {line.id: line for line in members}
    figure_boxes = [block.bbox for block in blocks if block.kind == "figure"]
    body_size = body[1] if body else None
    mapped = []
    for region in regions:
        update = {"bbox": from_frame(region.bbox, angle)}
        if (
            len(region.line_ids) == 1
            and region.type != "table_candidate"
            and credit_like(page_lines[region.line_ids[0]], lines, figure_boxes, body_size)
        ):
            update.update(
                type="credit_candidate",
                proposed_type=None,
                confidence=0.75,
                review_required=False,
                reasons=["Small isolated rotated text beside a figure edge"],
            )
        mapped.append(region.model_copy(update=update))
    frame_bands = [band.model_copy(update={"bbox": from_frame(band.bbox, angle)}) for band in found]
    page_tables = [
        table.model_copy(
            update={
                "bbox": from_frame(table.bbox, angle),
                "line_ids": [lid for lid, (kind, target) in owner.items() if target == table.id],
                "features": {**table.features, "rotation": angle},
            }
        )
        for table in tables
    ]
    scope = working.model_copy(update={"bbox": from_frame(frame_box, angle)})
    return scope, frame_bands, mapped, page_tables, notes


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
    own_blocks=None,
    furniture=True,
):
    by_id = {line.id: line for line in lines}
    regions = []
    pitch = median_pitch(lines)
    figures = [b for b in blocks if b.kind == "figure"]
    rules = [b for b in blocks if b.kind == "rule"]
    free = [by_id[lid] for lid, (kind, _) in owner.items() if kind == "scope"]
    body_style = dominant_style(free, store)
    # I5 counts all eligible rotated lines, including figure-owned labels. A
    # leftover line can therefore belong to a structural group even when fewer
    # than three unowned lines remain for analyse_frame.
    rotated_counts = Counter(
        rotation_key(line) for line in text_lines(lines) if not line.horizontal
    )
    page_body = page_body_style(lines, store)
    credit_body_size = page_body[1] if page_body else None
    figure_boxes = [block.bbox for block in figures]
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
            "furniture": furniture,
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
        if kind in {"scope", "figure", "table", "frame"}:
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
            key = rotation_key(line)
            structural = (
                rotated_counts[key] >= ROTATED_STRUCTURE_LINES and right_angle(key) is not None
            )
            supported = not structural or credit_like(line, lines, figure_boxes, credit_body_size)
            spec = (
                ("credit_candidate", 0.75, ["Rotated small text outside figures"])
                if small and supported
                else ("unknown", 0.45, ["Rotated group text without full credit evidence; review"])
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
        if own_blocks is not None and block.id not in own_blocks:
            continue
        members = [
            by_id[lid]
            for lid, (kind, target) in owner.items()
            if kind in {"figure", "table"} and target == block.id
        ]
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
        paint_fingerprint(analysis_fingerprint, resolved_device),
        LAYOUT_VERSION,
        code_digest("layout"),
        f"scale-{SCALE}",
        json.dumps(dependencies, sort_keys=True),
        resolved_device,
    )


def analyze_layout(
    source, page_number, extractor, repetition=None, cache_dir=None, *, analysis=None
):
    """Cached layout proposals for one page plus the object analysis they derive from."""
    assert_producer_unchanged("layout", LOADED_CODE_DIGEST)
    source = Path(source)
    analysis = analysis or analyze_page(source, page_number, extractor, repetition, cache_dir)
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
    paint = page_paint(source, analysis.native.page, extractor, analysis_fingerprint, cache_dir)
    layout = build_layout(analysis, raster, extractor.device.resolved, paint)
    if paint.diagnostics:
        layout = layout.model_copy(
            update={
                "diagnostics": [*layout.diagnostics, *paint.diagnostics],
            }
        )
    assert_producer_unchanged("layout", LOADED_CODE_DIGEST)
    if path is not None:
        atomic_write(path, layout, fingerprint)
    return layout, analysis
