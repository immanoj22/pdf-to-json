"""Native paint evidence. Source parsing is confined to this extractor module."""

from collections import defaultdict
from pathlib import Path

import pymupdf

from book_core.extraction.fingerprints import source_digest, stable_id
from book_core.extraction.rasters import RasterPage
from book_core.model.common import BBox, Provenance
from book_core.objects.models import (
    ImageRepetition,
    NativeObjectPage,
    PageObject,
    PaintCommand,
    PathItem,
    RenderGlyph,
    RepetitionRecord,
    TextRenderInfo,
)


def bbox(values):
    if isinstance(values, BBox):
        return values
    values = list(values)
    if len(values) != 4 or values[2] < values[0] or values[3] < values[1]:
        return None
    return BBox(x0=values[0], y0=values[1], x1=values[2], y1=values[3])


def clipped(values, width, height):
    result = bbox(values)
    if result is None:
        return None
    x0, y0 = max(0, result.x0), max(0, result.y0)
    x1, y1 = min(width, result.x1), min(height, result.y1)
    return bbox((x0, y0, x1, y1))


def path_item(item):
    coordinates = []
    orientation = None
    for value in item[1:]:
        if isinstance(value, (pymupdf.Point, pymupdf.Rect, pymupdf.Quad)):
            coordinates.extend(float(v) for v in tuple(value) if isinstance(v, (int, float)))
            if isinstance(value, pymupdf.Quad):
                coordinates = [v for point in value for v in (point.x, point.y)]
        elif isinstance(value, int):
            orientation = value
    return PathItem(operator=item[0], coordinates=coordinates, orientation=orientation)


def extract_object_page(extractor, source: Path, page_number: int) -> NativeObjectPage:
    digest = source_digest(source)
    identity = extractor.identity
    namespace = extractor._namespace(digest)
    provenance = Provenance(
        source_sha256=digest,
        engine=identity.name,
        engine_version=identity.version,
        method="native",
        resolved_device=extractor.device.resolved,
    )
    diagnostics = []
    objects = []
    with pymupdf.open(source) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError("Page argument is outside the document")
        page = document[page_number - 1]
        evidence = extractor._page_evidence(
            page, digest, namespace, provenance, pymupdf.TEXTFLAGS_RAWDICT
        )
        width, height = evidence.geometry.width, evidence.geometry.height
        log = page.get_bboxlog(layers=True)
        commands = [
            PaintCommand(
                seqno=i,
                operation=entry[0],
                raw_bbox=list(entry[1]),
                bbox=bbox(entry[1]),
                layer=entry[2] if len(entry) > 2 else None,
            )
            for i, entry in enumerate(log)
        ]
        valid_command_indices = [command.seqno for command in commands if command.bbox is not None]
        if len(valid_command_indices) != len(commands):
            diagnostics.append(
                "Empty-paint bounds retained; drawing counters require reconciliation"
            )

        def compatible(command, drawing, rectangle):
            if rectangle is None or command.bbox is None:
                return False
            operation = "fill-path" if drawing["type"] in {"f", "fs"} else "stroke-path"
            if command.operation != operation:
                return False
            a, b = rectangle, command.bbox
            if operation == "fill-path":
                return (
                    max(abs(a.x0 - b.x0), abs(a.y0 - b.y0), abs(a.x1 - b.x1), abs(a.y1 - b.y1))
                    <= 0.5
                )
            return (
                abs((a.x0 + a.x1 - b.x0 - b.x1) / 2) <= 0.5
                and abs((a.y0 + a.y1 - b.y0 - b.y1) / 2) <= 0.5
            )

        breaks = {
            i
            for i, entry in enumerate(log)
            if entry[0] in {"fill-text", "stroke-text", "ignore-text", "fill-image"}
        }
        run = []
        current = 0
        for i in range(len(log)):
            if i in breaks:
                current += 1
            run.append(current)
        traces = page.get_texttrace()
        render_info = []
        for trace in traces:
            info = TextRenderInfo(
                seqno=trace["seqno"],
                render_type=trace["type"],
                opacity=trace.get("opacity"),
                font=trace.get("font"),
                size=trace.get("size"),
                color=list(trace.get("color", ())),
                direction=tuple(trace.get("dir", (1, 0))),
                writing_mode=trace.get("wmode", 0),
                bidi_level=trace.get("bidi_lvl"),
                layer=trace.get("layer"),
                glyphs=[
                    RenderGlyph(
                        unicode=char[0], glyph_id=char[1], origin=tuple(char[2]), bbox=bbox(char[3])
                    )
                    for char in trace["chars"]
                ],
            )
            render_info.append((bbox(trace["bbox"]), info))
        # Glyph-box intersection assigns paint metadata, never ownership or reading order.
        from book_core.objects.spatial import SpatialIndex

        span_objects = [
            PageObject(
                id=span.id,
                kind="text",
                bbox=span.bbox,
                native_bbox=span.bbox,
                source_page=page_number,
                source_spans=[span.id],
                provenance=span.provenance,
            )
            for span in evidence.store.spans.values()
        ]
        index = SpatialIndex(span_objects)
        assignments = defaultdict(list)
        unmatched = []
        for trace_box, info in render_info:
            matches = index.query(trace_box)
            if matches:
                for position in matches:
                    assignments[position].append(info)
            else:
                unmatched.append((trace_box, info))
        for i, obj in enumerate(span_objects):
            infos = assignments[i]
            objects.append(
                obj.model_copy(
                    update={
                        "render_info": infos,
                        "paint_sequences": sorted({t.seqno for t in infos}),
                        "opacity": min(
                            (t.opacity for t in infos if t.opacity is not None), default=None
                        ),
                    }
                )
            )
        for i, (trace_box, info) in enumerate(unmatched):
            objects.append(
                PageObject(
                    id=stable_id(namespace, page_number, "trace", i),
                    kind="text_render",
                    source_page=page_number,
                    bbox=clipped(trace_box, width, height) if trace_box else None,
                    native_bbox=trace_box,
                    paint_sequences=[info.seqno],
                    render_info=[info],
                    provenance=provenance,
                    evidence_notes=["Trace has no rawdict span match; evidence retained"],
                )
            )
        placements = page.get_image_info(hashes=True, xrefs=True)
        visual_commands = [
            command for command in commands if command.operation in {"fill-image", "fill-shade"}
        ]
        if len(placements) != len(visual_commands):
            diagnostics.append(
                "Image/shading placement and paint counts differ: unmatched evidence retained"
            )
        matched_visual = set()
        for i, placement in enumerate(placements):
            command = visual_commands[i] if i < len(visual_commands) else None
            native_box = bbox(placement["bbox"])
            matched = command is not None
            if matched and command.operation == "fill-image":
                # Do not accept inconsistent paint/placement association.
                a, b = native_box, command.bbox
                matched = (
                    a is not None
                    and b is not None
                    and max(abs(a.x0 - b.x0), abs(a.y0 - b.y0), abs(a.x1 - b.x1), abs(a.y1 - b.y1))
                    < 1
                )
            kind = "shading" if command and command.operation == "fill-shade" else "image"
            notes = []
            if not matched:
                diagnostics.append(f"Unmatched image placement {i}")
                notes.append("Paint sequence unavailable or association inconsistent")
            if kind == "shading":
                notes.append(
                    "Shading placement bounds supplied by get_image_info; bboxlog may be unbounded"
                )
            seq = [command.seqno] if matched else []
            matched_visual.update(seq)
            objects.append(
                PageObject(
                    id=stable_id(namespace, page_number, kind, i),
                    kind=kind,
                    source_page=page_number,
                    bbox=clipped(native_box, width, height),
                    native_bbox=native_box,
                    paint_sequences=seq,
                    paint_run=run[seq[0]] if seq else None,
                    image_digest=placement["digest"].hex(),
                    image_xref=placement.get("xref"),
                    image_transform=list(placement.get("transform", ())),
                    image_width=placement.get("width"),
                    image_height=placement.get("height"),
                    image_has_mask=placement.get("has-mask"),
                    provenance=provenance,
                    evidence_notes=notes,
                )
            )
        for command in visual_commands:
            if command.seqno in matched_visual:
                continue
            objects.append(
                PageObject(
                    id=stable_id(namespace, page_number, "unmatched", command.seqno),
                    kind="unmatched_paint",
                    source_page=page_number,
                    bbox=clipped(command.bbox, width, height) if command.bbox else None,
                    native_bbox=command.bbox,
                    paint_sequences=[command.seqno],
                    provenance=provenance,
                    evidence_notes=["Native visual paint has no image placement record"],
                )
            )
        object_lookup = {obj.id: obj for obj in objects}
        active_clips = {}
        active_groups = {}
        for i, drawing in enumerate(page.get_drawings(extended=True)):
            level = drawing.get("level", 0)
            active_clips = {k: v for k, v in active_clips.items() if k < level}
            active_groups = {k: v for k, v in active_groups.items() if k < level}
            kind = drawing["type"] if drawing["type"] in {"clip", "group"} else "drawing"
            oid = stable_id(namespace, page_number, kind, i)
            rect = drawing.get("rect", drawing.get("scissor"))
            native_box = bbox(rect) if rect is not None else None
            visible = clipped(native_box, width, height) if native_box else None
            clip_ids = list(active_clips.values())
            if visible is not None:
                for clip_id in clip_ids:
                    clip_object = object_lookup[clip_id]
                    if clip_object.bbox:
                        visible = clipped(
                            (
                                max(visible.x0, clip_object.bbox.x0),
                                max(visible.y0, clip_object.bbox.y0),
                                min(visible.x1, clip_object.bbox.x1),
                                min(visible.y1, clip_object.bbox.y1),
                            ),
                            width,
                            height,
                        )
                        if visible is None:
                            break
            native_seqno = drawing.get("seqno")
            seq = None
            association_notes = []
            if native_seqno is not None:
                candidates = []
                if 0 <= native_seqno < len(valid_command_indices):
                    candidates.append(valid_command_indices[native_seqno])
                if 0 <= native_seqno < len(commands):
                    candidates.append(native_seqno)
                seq = next(
                    (
                        candidate
                        for candidate in dict.fromkeys(candidates)
                        if compatible(commands[candidate], drawing, native_box)
                    ),
                    None,
                )
                if seq is None:
                    association_notes.append(
                        "Drawing paint association unverified; native counter retained"
                    )
                elif seq != native_seqno:
                    association_notes.append(
                        "Drawing counter reconciled around invalid empty paints"
                    )
            sequences = [seq] if seq is not None else []
            if drawing["type"] == "fs" and seq is not None and seq + 1 < len(commands):
                stroke_drawing = {**drawing, "type": "s"}
                if compatible(commands[seq + 1], stroke_drawing, native_box):
                    sequences.append(seq + 1)
                else:
                    association_notes.append("Combined stroke association unverified")
            groups = [object_lookup[oid] for oid in active_groups.values()]
            group_opacity = 1.0
            for group in groups:
                group_opacity *= group.opacity if group.opacity is not None else 1
            obj = PageObject(
                id=oid,
                kind=kind,
                source_page=page_number,
                bbox=visible,
                native_bbox=native_box,
                paint_sequences=sequences,
                native_seqno=native_seqno,
                paint_run=run[seq] if seq is not None else None,
                opacity=drawing.get("opacity", group_opacity),
                fill_opacity=drawing.get("fill_opacity"),
                stroke_opacity=drawing.get("stroke_opacity"),
                fill=list(drawing["fill"]) if drawing.get("fill") is not None else None,
                stroke=list(drawing["color"]) if drawing.get("color") is not None else None,
                stroke_width=drawing.get("width"),
                path_items=[path_item(item) for item in drawing.get("items", [])],
                clip_ids=clip_ids,
                clip_status="native_scissor" if clip_ids or kind == "clip" else "unavailable",
                blend_mode=drawing.get("blendmode"),
                native_level=level,
                provenance=provenance,
                evidence_notes=(
                    ["Native graphics state; not visible artwork"]
                    if kind in {"clip", "group"}
                    else []
                )
                + association_notes,
            )
            objects.append(obj)
            object_lookup[oid] = obj
            if kind == "clip":
                active_clips[level] = oid
            if kind == "group":
                active_groups[level] = oid
        represented = {seq for obj in objects for seq in obj.paint_sequences}
        for command in commands:
            if (
                command.operation in {"fill-path", "stroke-path", "fill-image", "fill-shade"}
                and command.seqno not in represented
            ):
                objects.append(
                    PageObject(
                        id=stable_id(namespace, page_number, "unrepresented-paint", command.seqno),
                        kind="unmatched_paint",
                        source_page=page_number,
                        bbox=clipped(command.bbox, width, height) if command.bbox else None,
                        native_bbox=command.bbox,
                        paint_sequences=[command.seqno],
                        provenance=provenance,
                        evidence_notes=[
                            "No native drawing/placement association; paint retained for review"
                        ],
                    )
                )
                diagnostics.append(
                    f"Unassociated visual paint sequence {command.seqno} retained as unknown"
                )
        return NativeObjectPage(
            page=evidence, objects=objects, paint_commands=commands, diagnostics=diagnostics
        )


def render_page(source: Path, page_number: int, dpi: int = 144) -> RasterPage:
    if dpi <= 0:
        raise ValueError("DPI must be positive")
    with pymupdf.open(source) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError("Page argument is outside the document")
        page = document[page_number - 1]
        # All extracted boxes use the unrotated crop frame.
        page.set_rotation(0)
        pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=pymupdf.csRGB)
        return RasterPage(
            png=pixmap.tobytes("png"),
            width=pixmap.width,
            height=pixmap.height,
            page_width=page.rect.width,
            page_height=page.rect.height,
        )


def image_repetition(source: Path) -> ImageRepetition:
    digest = source_digest(source)
    occurrences = defaultdict(list)
    diagnostics = []
    with pymupdf.open(source) as document:
        page_count = len(document)
        for page in document:
            placements = page.get_image_info(hashes=True, xrefs=True)
            visual_log = [
                entry for entry in page.get_bboxlog() if entry[0] in {"fill-image", "fill-shade"}
            ]
            if len(placements) != len(visual_log):
                diagnostics.append(
                    f"Page {page.number + 1}: raster repetition association unavailable"
                )
                continue
            for info, paint in zip(placements, visual_log, strict=True):
                if paint[0] != "fill-image":
                    continue
                rect = pymupdf.Rect(info["bbox"])
                normalized = (
                    rect.x0 / page.cropbox.width,
                    rect.y0 / page.cropbox.height,
                    rect.x1 / page.cropbox.width,
                    rect.y1 / page.cropbox.height,
                )
                occurrences[info["digest"].hex()].append((page.number + 1, normalized))
    records = {}
    for key, placements in occurrences.items():
        values = [placement for _, placement in placements]
        stable = all(
            max(abs(a - b) for a, b in zip(value, values[0], strict=True)) <= 0.02
            for value in values
        )
        records[key] = RepetitionRecord(
            page_numbers=sorted({page for page, _ in placements}), stable_placement=stable
        )
    return ImageRepetition(
        source_sha256=digest, page_count=page_count, images=records, diagnostics=diagnostics
    )
