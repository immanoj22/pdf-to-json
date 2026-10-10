"""Apply book-level furniture roles to one page: a region view, a rebuilt order, page records.

Step 4 proposed header/footer/page-number regions from one page's evidence. Step 8 decides
with the whole book, so the page's regions are re-typed in a *view* (the cached Step 4 layout
is never modified): furniture lines become header/footer or page-number regions, and content
lines that Step 4 took for furniture become text (repeated boxes become sidebar floats, as
designed boxes). A region whose lines get different types is split. The unchanged Step 7
builder then orders the view, and its single furniture stream is split into one stream per
furniture role. Pages whose types do not change keep their cached Step 7 order.
"""

from __future__ import annotations

from collections import defaultdict

from book_core.extraction.fingerprints import stable_id
from book_core.furniture.models import (
    FURNITURE_ROLES,
    LineRole,
    PageFurniture,
    PageMarker,
)
from book_core.layout.models import PageLayout
from book_core.model.common import Provenance
from book_core.reading_order.builder import build_reading_order
from book_core.reading_order.graph import check
from book_core.reading_order.models import OrderEdge, PageReadingOrder, Stream

FURNITURE_VERSION = "furniture-2"  # Step 9: metadata front matter, drawn boxes
STEP4_FURNITURE = frozenset({"header_footer_candidate", "page_number_candidate"})


def target_type(region_type, role, inside_content):
    """The region type a line needs so the Step 7 builder streams it by its Step 8 role."""
    if role == "folio":
        return "page_number_candidate"
    if role in {"running_head", "running_foot"}:
        return "header_footer_candidate"
    if role == "production_mark":
        return region_type if not inside_content else "header_footer_candidate"
    if region_type in STEP4_FURNITURE:
        return "sidebar" if role == "repeated_box" else "main_text"
    return region_type


def region_view(layout, roles):
    """Layout copy whose regions carry the Step 8 types; None when nothing changes."""
    lines = {line.id: line for line in layout.lines}
    role_of = {role.line_id: role.role for role in roles}
    regions, renamed, changed = [], {}, False
    for region in layout.regions:
        groups = defaultdict(list)
        for lid in region.line_ids:
            kind = target_type(region.type, role_of[lid], lines[lid].inside_content)
            groups[kind].append(lid)
        if not groups or list(groups) == [region.type]:
            regions.append(region)
            continue
        changed = True
        evidence = {**region.evidence, "step4_type": region.type}
        reasons = [*region.reasons, "re-typed by the whole-book furniture stage"]
        if len(groups) == 1:
            (kind,) = groups
            regions.append(
                region.model_copy(update={"type": kind, "evidence": evidence, "reasons": reasons})
            )
            continue
        ids = []
        for kind, members in groups.items():
            boxes = [lines[lid].bbox for lid in members]
            part = region.model_copy(
                update={
                    "id": stable_id(region.id, "furniture-split", kind),
                    "type": kind,
                    "line_ids": members,
                    "bbox": boxes[0].model_copy(
                        update={
                            "x0": min(b.x0 for b in boxes),
                            "y0": min(b.y0 for b in boxes),
                            "x1": max(b.x1 for b in boxes),
                            "y1": max(b.y1 for b in boxes),
                        }
                    ),
                    "child_region_ids": region.child_region_ids if not ids else [],
                    "evidence": {**evidence, "split_from": region.id},
                    "reasons": [*reasons, "split: its lines have different furniture roles"],
                }
            )
            ids.append(part.id)
            regions.append(part)
        renamed[region.id] = ids
    if not changed:
        return None
    if renamed:
        regions = [
            r.model_copy(
                update={
                    "child_region_ids": [
                        new for child in r.child_region_ids for new in renamed.get(child, [child])
                    ]
                }
            )
            if any(child in renamed for child in r.child_region_ids)
            else r
            for r in regions
        ]
    regions = _attach_returned_lines(layout, regions, lines)
    data = layout.model_dump()
    data["regions"] = [r.model_dump() for r in regions]
    return PageLayout.model_validate(data)  # re-run every layout validator


HOST_TYPES = frozenset({"main_text", "heading_candidate", "title_candidate"})
HOST_REACH = 3.0  # font sizes between a returned line and its host region


def _union(boxes):
    first = boxes[0]
    return first.model_copy(
        update={
            "x0": min(b.x0 for b in boxes),
            "y0": min(b.y0 for b in boxes),
            "x1": max(b.x1 for b in boxes),
            "y1": max(b.y1 for b in boxes),
        }
    )


NOT_HOSTS = STEP4_FURNITURE | {"artifact_candidate", "figure", "table_candidate", "callout"}
ADJACENT_REACH = 1.5  # font sizes: a returned line directly continuing a neighbouring block


def _host(line, scope_id, regions, bands, returned):
    """The block a returned line belongs to: the adjacent block it continues, else its lane.

    First choice: a content region of the same scope overlapping the line horizontally by at
    least half the line's width and within ADJACENT_REACH font sizes (a definition, note or
    paragraph whose next line Step 4 split off). Fallback: the nearest text region whose lane
    holds the line's centre, within HOST_REACH font sizes.
    """
    if not line.horizontal:
        return None
    box = line.bbox
    width = max(box.x1 - box.x0, 1e-6)
    centre = (box.x0 + box.x1) / 2
    adjacent = lane_host = None
    for region in regions:
        if region.id in returned or region.scope_id != scope_id or region.type in NOT_HOSTS:
            continue
        other = region.bbox
        distance = max(0.0, box.y0 - other.y1, other.y0 - box.y1)
        overlap = min(box.x1, other.x1) - max(box.x0, other.x0)
        if overlap >= 0.5 * width and distance <= ADJACENT_REACH * line.font_size:
            if adjacent is None or distance < adjacent[0]:
                adjacent = (distance, region)
        if region.type not in HOST_TYPES or region.band_id not in bands:
            continue
        lanes = {lane.index: lane for lane in bands[region.band_id].lanes}
        lane = lanes.get(region.lane_index)
        if lane is None or not lane.x0 <= centre <= lane.x1:
            continue
        if distance <= HOST_REACH * line.font_size and (
            lane_host is None or distance < lane_host[0]
        ):
            lane_host = (distance, region)
    chosen = adjacent or lane_host
    return chosen[1] if chosen else None


def _attach_returned_lines(layout, regions, lines):
    """Content lines that Step 4 took for furniture rejoin the text region of their lane.

    Step 4 furniture regions sit outside the band structure, so the Step 7 builder would read
    a returned line as a loose block at its position, after every column of its band. A line
    whose lane holds a text region within HOST_REACH font sizes joins that region and is read
    in its lane by baseline; otherwise it stays a loose block (Step 7 behaviour).
    """
    scopes = {scope.id: scope for scope in layout.scopes}
    bands = {band.id: band for band in layout.bands}
    returned = {
        r.id
        for r in regions
        if r.type == "main_text" and r.evidence.get("step4_type") in STEP4_FURNITURE
    }
    moves = defaultdict(list)
    for region in regions:
        if region.id not in returned or scopes[region.scope_id].rotation:
            continue
        for lid in region.line_ids:
            host = _host(lines[lid], region.scope_id, regions, bands, returned)
            if host is not None:
                moves[host.id].append((region.id, lid))
    if not moves:
        return regions
    taken = defaultdict(set)
    for items in moves.values():
        for source, lid in items:
            taken[source].add(lid)
    result, dropped = [], set()
    for region in regions:
        if region.id in moves:
            added = [lid for _, lid in moves[region.id]]
            members = [*region.line_ids, *added]
            region = region.model_copy(
                update={
                    "line_ids": members,
                    "bbox": _union([lines[lid].bbox for lid in members]),
                    "evidence": {**region.evidence, "returned_lines": len(added)},
                    "reasons": [*region.reasons, "content lines returned from Step 4 furniture"],
                }
            )
        elif region.id in taken:
            remaining = [lid for lid in region.line_ids if lid not in taken[region.id]]
            if not remaining:
                dropped.add(region.id)
                continue
            region = region.model_copy(
                update={
                    "line_ids": remaining,
                    "bbox": _union([lines[lid].bbox for lid in remaining]),
                }
            )
        result.append(region)
    return [
        r.model_copy(
            update={"child_region_ids": [c for c in r.child_region_ids if c not in dropped]}
        )
        if dropped & set(r.child_region_ids)
        else r
        for r in result
    ]


def split_furniture_streams(order, roles):
    """One furniture stream per furniture role, each chained by next_in_stream edges."""
    role_of = {role.line_id: role.role for role in roles}
    sid = lambda *parts: stable_id(order.source_sha256, order.page, "stream", *parts)  # noqa: E731
    streams, edges, mapping = [], list(order.edges), {}
    for stream in order.streams:
        if stream.kind != "furniture":
            streams.append(stream)
            continue
        members = set(stream.line_ids)
        edges = [e for e in edges if not (e.kind == "next_in_stream" and e.source in members)]
        by_role = defaultdict(list)
        for lid in stream.line_ids:
            role = role_of[lid]
            if role not in FURNITURE_ROLES:
                raise ValueError(f"Content line {lid[:12]} in a furniture stream")
            by_role[role].append(lid)
        for role in sorted(by_role):
            lines = by_role[role]
            new = Stream(
                id=sid("furniture", role),
                kind="furniture",
                line_ids=lines,
                confidence=stream.confidence,
                reasons=[f"{role} lines, retained; whole-book furniture decision"],
            )
            streams.append(new)
            mapping[role] = new.id
            edges += [
                OrderEdge(
                    source=a,
                    target=b,
                    kind="next_in_stream",
                    confidence=0.8,
                    reasons=[f"{role} stream order"],
                )
                for a, b in zip(lines, lines[1:], strict=False)
            ]
    rebuilt = order.model_copy(update={"streams": streams, "edges": edges})
    return PageReadingOrder.model_validate(rebuilt.model_dump()), mapping


def apply_page(page, layout, order, roles, marker, vocabulary=None, resolved_device="cpu"):
    """PageFurniture for one page: roles, marker and the order rebuilt with those roles."""
    if {r.line_id for r in roles} != {line.id for line in layout.lines}:
        raise ValueError(f"Page {layout.page}: roles must cover exactly the layout lines")
    view = region_view(layout, roles)
    rebuilt = (
        order
        if view is None
        else build_reading_order(view, page.store, vocabulary, resolved_device)
    )
    problems = check(rebuilt, view or layout)
    if problems:
        raise ValueError(f"Page {layout.page}: reading order invariants fail: {problems}")
    final, mapping = split_furniture_streams(rebuilt, roles)
    problems = check(final, view or layout)
    if problems:
        raise ValueError(f"Page {layout.page}: furniture streams break invariants: {problems}")
    return PageFurniture(
        source_sha256=layout.source_sha256,
        page=layout.page,
        furniture_version=FURNITURE_VERSION,
        roles=roles,
        marker=marker,
        order=final,
        furniture_streams=mapping,
        provenance=Provenance(
            source_sha256=layout.source_sha256,
            engine="book_core.furniture",
            engine_version=FURNITURE_VERSION,
            method="derived",
            resolved_device=resolved_device,
            notes=["order rebuilt with Step 8 roles" if view is not None else "Step 7 order kept"],
        ),
    )


def line_roles(decisions):
    """LineRole records from the classifier's per-line decision dictionaries."""
    return [LineRole(line_id=line_id, **decision) for line_id, decision in decisions.items()]


def page_marker(decision, folio_line_ids):
    """PageMarker from a sequence decision (``furniture.sequence.PageLabel``)."""
    return PageMarker(
        page=decision.page,
        label=decision.label,
        kind=decision.kind if decision.label is not None else "none",
        source=decision.source,
        confidence=decision.confidence,
        folio_line_ids=folio_line_ids if decision.source in {"printed", "metadata"} else [],
        run_index=decision.run,
        metadata_label=decision.metadata_label,
        reasons=list(decision.reasons),
        review_required=decision.review_required,
    )
