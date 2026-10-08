"""Typed region proposals from lanes, blocks and line evidence. Never paragraphs.

Lines in one lane are grouped by vertical proximity and shared dominant style; groups are
typed by combining several cues (position in the scope, rules, neighbouring figures,
style contrast with the scope's body style, isolation). Font size alone never decides a
heading. Low confidence becomes `unknown` with the proposal kept for review.
"""

from dataclasses import dataclass, field
from statistics import median

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.layout.blocks import contains, expand, union
from book_core.layout.models import Region

UNKNOWN_BELOW = 0.6
EDGE_ZONE = 0.07
BOLD_FLAG = 16
DIGIT = regex.compile(r"\p{Nd}")
WHITESPACE = regex.compile(r"\s")


@dataclass
class Group:
    lines: list
    scope_id: str
    band: object = None
    lane: object = None
    style: tuple | None = None
    type: str = "main_text"
    confidence: float = 0.8
    reasons: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    @property
    def bbox(self):
        return union(line.bbox for line in self.lines)


def raw_text(line, store):
    return "".join(store.spans[sid].raw_text for sid in line.span_ids)


def dominant_style(lines, store):
    weights = {}
    for line in lines:
        for sid in line.span_ids:
            span = store.spans[sid]
            count = len(span.raw_text.strip())
            if count:
                key = (span.font, round(span.size, 1), span.color, bool(span.flags & BOLD_FLAG))
                weights[key] = weights.get(key, 0) + count
    return max(weights, key=weights.get) if weights else None


def group_lane(lines, store, pitch):
    """Union lines that touch vertically, overlap horizontally and share a dominant style."""
    styles = {line.id: dominant_style([line], store) for line in lines}
    parent = {line.id: line.id for line in lines}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for i, a in enumerate(lines):
        for b in lines[i + 1 :]:
            if styles[a.id] != styles[b.id]:
                continue
            gap = max(b.bbox.y0 - a.bbox.y1, a.bbox.y0 - b.bbox.y1)
            overlap = min(a.bbox.x1, b.bbox.x1) - max(a.bbox.x0, b.bbox.x0)
            if gap <= 0.8 * pitch and overlap > 0:
                parent[find(b.id)] = find(a.id)
    groups = {}
    for line in lines:
        groups.setdefault(find(line.id), []).append(line)
    return list(groups.values())


def adjacent_figure(box, figures, pitch, unit):
    for figure in figures:
        f = figure.bbox
        horizontal_overlap = min(box.x1, f.x1) - max(box.x0, f.x0)
        vertical_overlap = min(box.y1, f.y1) - max(box.y0, f.y0)
        below = 0 <= box.y0 - f.y1 <= 2 * pitch and horizontal_overlap > 0.3 * (box.x1 - box.x0)
        above = 0 <= f.y0 - box.y1 <= 1.5 * pitch and horizontal_overlap > 0.3 * (box.x1 - box.x0)
        beside = (
            max(f.x0 - box.x1, box.x0 - f.x1) <= 3 * unit
            and max(f.x0 - box.x1, box.x0 - f.x1) >= -1
            and vertical_overlap >= 0.5 * (box.y1 - box.y0)
        )
        if below or above or beside:
            return figure
    return None


def type_groups(groups, context):
    store = context["store"]
    content = context["content"]
    body = context["body_style"]
    figures = context["figures"]
    rules = context["rules"]
    top_band = context["top_band"]
    page_body_size = body[1] if body else 10.0
    height = content.y1 - content.y0
    for group in groups:
        box = group.bbox
        lines = group.lines
        scope_body = context["scope_body"].get(group.scope_id) or body
        style = group.style
        text = " ".join(raw_text(line, store).strip() for line in lines)
        pitch = context["pitch"]
        size = style[1] if style else page_body_size
        lane_kind = group.lane.kind if group.lane is not None else None
        group.evidence = {
            "lines": len(lines),
            "lane_kind": lane_kind,
            "size_ratio": round(size / max(0.01, scope_body[1] if scope_body else size), 3),
        }
        centre = (box.y0 + box.y1) / 2
        rule = next(
            (
                r
                for r in rules
                if r.features.get("orientation") == "horizontal"
                and r.bbox.y1 <= box.y0 + 1
                and box.y0 - r.bbox.y1 <= 3 * pitch
                and (r.bbox.x1 - r.bbox.x0) >= 0.4 * context["scope_width"][group.scope_id]
                and r.bbox.y0 >= content.y0 + 0.6 * height
                and min(r.bbox.x1, box.x1) - max(r.bbox.x0, box.x0) > 0
                and not context["between"](r, group)
            ),
            None,
        )
        body_size = scope_body[1] if scope_body else page_body_size
        if rule is not None and len(lines) <= 4 and size <= body_size:
            group.type, group.confidence = "footnote_candidate", 0.72
            group.reasons = ["Short block directly below a wide horizontal rule in the lower page"]
            continue
        figure = adjacent_figure(box, figures, pitch, page_body_size)
        if lane_kind == "caption" or (
            figure is not None and style != scope_body and len(lines) <= 8
        ):
            group.type, group.confidence = "caption_candidate", 0.72
            group.reasons = ["Short block adjacent to a figure with non-body style"]
            if lane_kind == "caption":
                group.reasons = ["Text lane beside a figure"]
            continue
        in_edge = group.scope_id == context["page_scope"] and (
            centre <= content.y0 + EDGE_ZONE * height or centre >= content.y1 - EDGE_ZONE * height
        )
        small = size <= 1.3 * page_body_size and len(lines) <= 2
        if in_edge and small:
            compact = text.strip()
            if (
                len(lines) == 1
                and len(compact) <= 8
                and not WHITESPACE.search(compact)
                and (DIGIT.search(compact))
            ):
                group.type, group.confidence = "page_number_candidate", 0.75
                group.reasons = ["Short numeric token in the page edge zone"]
            else:
                group.type, group.confidence = "header_footer_candidate", 0.7
                group.reasons = ["Small text in the page edge zone"]
                if DIGIT.search(compact):
                    group.evidence["contains_number"] = True
            continue
        differs = style is not None and scope_body is not None and style != scope_body
        ratio = size / max(0.01, scope_body[1]) if scope_body else 1.0
        if (
            differs
            and len(lines) <= 3
            and ratio >= 1.6
            and group.band is not None
            and group.band.id == top_band
            and len(group.band.lanes) == 1
        ):
            group.type, group.confidence = "title_candidate", 0.78
            group.reasons = [
                "Large distinct style in the first single-lane band of the page",
                "Few lines",
            ]
            continue
        if differs and len(lines) <= 3 and len(text) <= 160:
            cues = []
            if ratio >= 1.15:
                cues.append("larger than body")
            if style[3] and not scope_body[3]:
                cues.append("bold against regular body")
            if style[2] != scope_body[2]:
                cues.append("colour differs from body")
            if context["isolated_above"](group):
                cues.append("whitespace or lane start above")
            if context["body_below"](group):
                cues.append("body text follows")
            if len(cues) >= 3 or (len(cues) >= 2 and ratio >= 1.15):
                group.type = "heading_candidate"
                group.confidence = min(0.88, 0.6 + 0.07 * len(cues))
                group.reasons = ["Distinct short block: " + ", ".join(cues)]
                continue
        if lane_kind in {"sidebar", "margin", "card"}:
            group.type, group.confidence = "sidebar", 0.7
            group.reasons = [f"Free text in a {lane_kind} lane"]
            continue
        if lane_kind == "figure":
            group.type, group.confidence = "caption_candidate", 0.62
            group.reasons = ["Free text inside a figure lane"]
            continue
        group.type, group.confidence = "main_text", 0.8 if lane_kind == "column" else 0.65
        group.reasons = ["Text in a column lane"] if lane_kind == "column" else ["Unlaned text"]


def make_region(group_type, lines, scope_id, band, lane, confidence, reasons, evidence, **extra):
    reviewed = confidence < UNKNOWN_BELOW
    bbox = extra.pop("bbox", None) or union(line.bbox for line in lines)
    key = [*sorted(line.id for line in lines), "|", *sorted(extra.get("object_ids", []))]
    return Region(
        id=stable_id("region", *key),
        type="unknown" if reviewed else group_type,
        proposed_type=group_type if reviewed else None,
        bbox=bbox,
        scope_id=scope_id,
        band_id=band.id if band is not None else None,
        lane_index=lane.index if lane is not None else None,
        line_ids=[line.id for line in lines],
        confidence=confidence,
        reasons=reasons + (["Low confidence: kept as unknown for review"] if reviewed else []),
        evidence=evidence,
        review_required=reviewed or group_type == "unknown",
        **extra,
    )


def merge_main_text(groups, pitch):
    """Adjacent main-text groups in one lane form one region; this is not paragraphing."""
    result = []
    pending = [g for g in groups if g.type == "main_text"]
    others = [g for g in groups if g.type != "main_text"]
    parent = list(range(len(pending)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(pending):
        for j in range(i + 1, len(pending)):
            b = pending[j]
            if a.band is not b.band or a.lane is not b.lane or a.scope_id != b.scope_id:
                continue
            ab, bb = a.bbox, b.bbox
            gap = max(bb.y0 - ab.y1, ab.y0 - bb.y1)
            overlap = min(ab.x1, bb.x1) - max(ab.x0, bb.x0)
            if gap <= 1.5 * pitch and overlap > 0:
                parent[find(j)] = find(i)
    merged = {}
    for i, group in enumerate(pending):
        target = merged.setdefault(find(i), group)
        if target is not group:
            target.lines = [*target.lines, *group.lines]
    result.extend(merged.values())
    result.extend(others)
    return result


def median_pitch(lines):
    heights = [line.bbox.y1 - line.bbox.y0 for line in lines if not line.blank]
    return median(heights) if heights else 12.0


def locate(bands, scope_id, bbox):
    cx, cy = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
    candidates = [
        band
        for band in bands
        if band.scope_id == scope_id and band.bbox.y0 - 1 <= cy <= band.bbox.y1 + 1
    ]
    if not candidates:
        return None, None
    band = min(candidates, key=lambda b: b.bbox.y1 - b.bbox.y0)
    lane = next((lane for lane in band.lanes if lane.x0 - 1 <= cx <= lane.x1 + 1), None)
    return band, lane


def embedded(line, figure, store):
    if contains(expand(figure.bbox, 2), line.bbox, tolerance=0):
        return True
    text = raw_text(line, store).strip()
    short = len(text) <= 30 and len(regex.findall(r"[\p{L}\p{M}\p{N}]+", text)) <= 4
    margin = max(12.0, 1.2 * line.font_size)
    return short and expand(figure.bbox, margin).contains_center(line.bbox)
