"""Transparent, conservative asset roles. No text structure or reading-order inference."""

import cv2
import numpy as np

from book_core.objects.models import RoleDecision
from book_core.objects.spatial import SpatialIndex


def raster_array(raster):
    result = cv2.imdecode(np.frombuffer(raster.png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if result is None:
        raise ValueError("Extractor returned an unreadable PNG")
    return result


def classify(native, compounds, raster, repetition):
    objects = [*native.objects, *compounds]
    text = [obj for obj in native.objects if obj.kind == "text"]
    index = SpatialIndex(text)
    images = [obj for obj in native.objects if obj.kind == "image" and obj.bbox]
    image_index = SpatialIndex(images)
    array = raster_array(raster)
    page = native.page.geometry
    area = page.width * page.height
    native_objects = {obj.id: obj for obj in native.objects}
    supported_compounds = {
        compound.id
        for compound in compounds
        if len(compound.member_ids) >= 3
        and all(native_objects[member].kind == "shading" for member in compound.member_ids)
    }
    member_ids = {
        member
        for compound in compounds
        if compound.id in supported_compounds
        for member in compound.member_ids
    }
    decisions = []
    for obj in objects:
        if obj.is_text:
            continue
        features = {
            "coverage": 0.0,
            "text_above_share": 0.0,
            "text_overlap_count": 0,
            "invisible_text_share": 0.0,
            "caption_like_nearby": False,
            "edge_density": None,
            "texture": None,
            "fill_text_contrast": None,
            "opacity": obj.opacity,
            "blend_mode": obj.blend_mode,
            "paint_order_fraction": min(obj.paint_sequences, default=0)
            / max(1, len(native.paint_commands)),
            "paper_like": None,
            "overpainted_image_share": 0.0,
        }
        if obj.bbox is not None:
            rect = obj.bbox
            coverage = max(0, rect.x1 - rect.x0) * max(0, rect.y1 - rect.y0) / area
            if obj.kind == "image":
                overlap_shares = []
                for i in image_index.query(rect):
                    other = images[i]
                    if (
                        other.id != obj.id
                        and other.paint_sequences
                        and obj.paint_sequences
                        and min(other.paint_sequences) > max(obj.paint_sequences)
                    ):
                        width = max(0, min(rect.x1, other.bbox.x1) - max(rect.x0, other.bbox.x0))
                        height = max(0, min(rect.y1, other.bbox.y1) - max(rect.y0, other.bbox.y0))
                        overlap_shares.append(width * height / max(1, coverage * area))
                features["overpainted_image_share"] = max(overlap_shares, default=0)
            overlaps = []
            for i in index.query(rect):
                candidate = text[i]
                bounds = candidate.bbox
                overlap = max(0, min(rect.x1, bounds.x1) - max(rect.x0, bounds.x0)) * max(
                    0, min(rect.y1, bounds.y1) - max(rect.y0, bounds.y0)
                )
                text_area = (bounds.x1 - bounds.x0) * (bounds.y1 - bounds.y0)
                if text_area > 0 and overlap / text_area >= 0.5:
                    overlaps.append(candidate)
            visible = [
                t
                for t in overlaps
                if not t.render_info
                or any(
                    info.render_type != 3 and (info.opacity is None or info.opacity > 0)
                    for info in t.render_info
                )
            ]
            invisible = [
                t
                for t in overlaps
                if t.render_info
                and all(info.render_type == 3 or info.opacity == 0 for info in t.render_info)
            ]
            last_paint = max(obj.paint_sequences, default=-1)
            above = [
                t for t in visible if t.paint_sequences and min(t.paint_sequences) > last_paint
            ]
            features.update(
                coverage=coverage,
                text_overlap_count=len(overlaps),
                text_above_share=len(above) / max(1, len(visible)),
                invisible_text_share=len(invisible) / max(1, len(overlaps)),
            )
            nearby = index.query(rect, distance=min(page.width, page.height) * 0.02)
            # Weak visual cue only: compact nearby line below a visual, in any script.
            features["caption_like_nearby"] = any(
                t.bbox.y0 >= rect.y1 and t.bbox.x1 - t.bbox.x0 <= rect.x1 - rect.x0
                for i in nearby
                for t in [text[i]]
            )
            x0, y0 = (
                int(rect.x0 / raster.page_width * raster.width),
                int(rect.y0 / raster.page_height * raster.height),
            )
            x1, y1 = (
                int(np.ceil(rect.x1 / raster.page_width * raster.width)),
                int(np.ceil(rect.y1 / raster.page_height * raster.height)),
            )
            crop = array[max(0, y0) : min(raster.height, y1), max(0, x0) : min(raster.width, x1)]
            if crop.size:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                # Rendered crop includes overprinted content, not an isolated asset bitmap.
                features["edge_density"] = float(np.mean(cv2.Canny(gray, 80, 160) > 0))
                features["texture"] = float(np.std(gray) / 255)
                features["paper_like"] = bool(np.median(gray) > 237)
            if obj.fill and len(obj.fill) in {1, 3} and visible:
                fill = np.array(obj.fill * 3 if len(obj.fill) == 1 else obj.fill)
                contrasts = []
                for t in visible:
                    source = native.page.store.spans[t.source_spans[0]]
                    rgb = (
                        np.array(
                            [
                                (source.color >> 16) & 255,
                                (source.color >> 8) & 255,
                                source.color & 255,
                            ]
                        )
                        / 255
                    )
                    contrasts.append(float(np.linalg.norm(fill - rgb) / np.sqrt(3)))
                features["fill_text_contrast"] = max(contrasts, default=0)
        coverage = features["coverage"]
        above = features["text_above_share"]
        count = features["text_overlap_count"]
        edge = features["edge_density"]
        texture = features["texture"]
        role, confidence, reasons = (
            "unknown",
            0.35,
            ["Native evidence is insufficient for a confident role"],
        )
        if obj.kind in {"clip", "group"}:
            reasons = ["Graphics-state context; retain for clipping and opacity audit"]
        elif obj.bbox is None:
            confidence, reasons = 0.2, ["No visible in-page bounds; native object retained"]
        elif obj.kind == "unmatched_paint" or not obj.paint_sequences:
            reasons = ["Paint association unavailable; review native evidence"]
        elif (
            obj.kind == "image"
            and coverage >= 0.70
            and count >= 2
            and features["invisible_text_share"] >= 0.70
        ):
            role, confidence, reasons = (
                "scan_layer",
                0.97,
                ["Page-size raster behind predominantly invisible text"],
            )
        elif (
            coverage >= 0.55
            and count >= 5
            and above >= 0.70
            and (
                obj.kind in {"image", "shading"}
                or (obj.kind == "drawing" and obj.fill is not None and len(obj.path_items) <= 4)
            )
        ):
            role, confidence, reasons = (
                "background",
                0.93,
                ["Large page coverage", "Visible text is painted above the visual"],
            )
        elif (
            obj.kind == "drawing"
            and obj.fill is not None
            and count >= 3
            and above >= 0.65
            and 0.003 <= coverage < 0.55
            and (features["fill_text_contrast"] or 0) >= 0.20
            and len(obj.path_items) <= 4
        ):
            role, confidence, reasons = (
                "container",
                0.88,
                [
                    "Simple colored filled boundary behind multiple text spans",
                    "Fill contrasts with the overprinted text",
                ],
            )
        elif (
            obj.kind in {"image", "shading"}
            and 0.003 <= coverage < 0.55
            and count >= 3
            and above >= 0.65
            and texture is not None
            and edge is not None
            and texture <= (0.18 if obj.kind == "shading" else 0.05)
            and edge <= 0.16
        ):
            role, confidence, reasons = (
                "container",
                0.82,
                [
                    "Low-texture painted backdrop behind multiple visible text spans",
                    "Local placement and text painted above it",
                ],
            )
        elif (
            obj.kind == "image" and repetition is not None and obj.image_digest in repetition.images
        ):
            record = repetition.images[obj.image_digest]
            features["repeated_pages"] = len(record.page_numbers)
            if (
                len(record.page_numbers) >= 3
                and len(record.page_numbers) / repetition.page_count >= 0.20
                and record.stable_placement
                and coverage < 0.08
            ):
                role, confidence, reasons = (
                    "repeated_artifact",
                    0.86,
                    [
                        "Identical image digest repeats across many pages",
                        "Small stable normalized placement",
                    ],
                )
        if (
            role == "unknown"
            and obj.bbox is not None
            and obj.paint_sequences
            and obj.kind not in {"clip", "group", "unmatched_paint"}
        ):
            if not page.content_bbox.contains_center(obj.bbox):
                role, confidence, reasons = (
                    "decorative",
                    0.82,
                    ["Visual lies outside the explicit printed TrimBox"],
                )
            elif (
                obj.kind == "compound"
                and obj.id in supported_compounds
                and 0.0005 <= coverage < 0.5
            ):
                role, confidence, reasons = (
                    "figure_part",
                    0.77,
                    [
                        "Multiple adjacent same-run visual primitives",
                        "Local visual extent; no figure grouping claimed",
                    ],
                )
            elif obj.id in member_ids:
                role, confidence, reasons = (
                    "figure_part",
                    0.76,
                    ["Member of a geometrically consolidated local visual"],
                )
            elif (
                obj.kind == "image"
                and 0.001 <= coverage < 0.55
                and (
                    count < 5
                    or (texture is not None and texture > 0.10 and edge is not None and edge > 0.05)
                )
            ):
                role, confidence, reasons = (
                    "content_image",
                    0.80,
                    [
                        "Independent raster placement with local coverage",
                        "No scan, background or repetition evidence",
                    ],
                )
            elif not page.content_bbox.contains_center(obj.bbox):
                role, confidence, reasons = (
                    "decorative",
                    0.82,
                    ["Visual lies outside the explicit printed TrimBox"],
                )
            elif (
                obj.kind == "drawing"
                and obj.fill is not None
                and (obj.bbox.x1 - obj.bbox.x0) / page.width > 0.7
                and (obj.bbox.x1 - obj.bbox.x0) / max(0.01, obj.bbox.y1 - obj.bbox.y0) > 5
            ):
                role, confidence, reasons = (
                    "unknown",
                    0.60,
                    ["Broad filled band may be a local backdrop; visual context requires review"],
                )
            elif (
                obj.kind == "drawing"
                and len(obj.path_items) >= 5
                and 0.001 <= coverage < 0.4
                and count < 8
            ):
                role, confidence, reasons = (
                    "figure_part",
                    0.75,
                    ["Local complex vector artwork with little overlapping text"],
                )
            elif (
                obj.kind == "drawing"
                and coverage < 0.00005
                and count == 0
                and edge is not None
                and texture is not None
                and texture < 0.05
            ):
                role, confidence, reasons = (
                    "decorative",
                    0.72,
                    ["Tiny low-texture mark with no intersecting text"],
                )
        # Unsupported blend/opacity or missing placement evidence keeps uncertainty explicit.
        if role not in {"background", "scan_layer", "container"} and obj.blend_mode not in {
            None,
            "Normal",
        }:
            role, confidence, reasons = "unknown", 0.45, ["Non-normal blend requires review"]
        if role == "background" and features["paint_order_fraction"] > 0.25:
            confidence = 0.82
            reasons.append("Later paint operation lowers certainty")
        if role in {"content_image", "figure_part"} and features["caption_like_nearby"]:
            confidence = min(0.90, confidence + 0.03)
            reasons.append("Compact nearby text below the visual is a weak caption cue")
        if (
            obj.kind == "image"
            and features["overpainted_image_share"] >= 0.5
            and role not in {"background", "scan_layer"}
        ):
            role, confidence, reasons = (
                "unknown",
                0.55,
                [
                    "Raster is substantially overpainted by a later image",
                    "Rendered-crop texture cannot establish this placement's visible contribution",
                ],
            )
        if confidence < 0.70:
            role = "unknown"
        decisions.append(
            RoleDecision(
                object_id=obj.id,
                role=role,
                confidence=confidence,
                reasons=reasons,
                review_required=role == "unknown",
                features=features,
            )
        )
    return decisions
