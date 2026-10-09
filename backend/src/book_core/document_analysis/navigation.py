"""Navigation evidence from native lines and extractor-provided document metadata.

A printed entry references exact source character ranges. Indentation and outline depth
are level evidence only. Duplicate labels retain every target; absent labels stay unresolved.
No page receives a semantic zone, and no line becomes a heading here.
"""

from __future__ import annotations

import math
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

import regex

from book_core.extraction.fingerprints import stable_id
from book_core.model.spans import ExtractedPage

_LEADER = regex.compile(r"[.\u00b7\u2024\u2025\u2026_](?:\s*[.\u00b7\u2024\u2025\u2026_])+")
_WORD = regex.compile(r"\S+")
_LETTER = regex.compile(r"\p{L}")
_DIGIT = regex.compile(r"\p{N}")
_ROMAN = regex.compile(r"(?i)[ivxlcdm]+")


@dataclass(frozen=True)
class NavigationConfig:
    minimum_entries: int = 3
    minimum_reference_density: float = 0.45
    row_overlap: float = 0.5
    alignment_tolerance_fonts: float = 1.5
    maximum_title_lines: int = 3
    pairing_majority: float = 0.7

    def __post_init__(self):
        if self.minimum_entries < 2 or self.maximum_title_lines < 1:
            raise ValueError(
                "Navigation entry counts must be positive and require repeated structure"
            )
        if not 0 < self.minimum_reference_density <= 1 or not 0 < self.row_overlap <= 1:
            raise ValueError("Navigation ratios must be in (0, 1]")
        if not 0.5 < self.pairing_majority <= 1:
            raise ValueError("Pairing majority must be in (0.5, 1]")
        if self.alignment_tolerance_fonts <= 0:
            raise ValueError("Navigation alignment tolerance must be positive")


def normalize_label(label: str) -> str:
    """NFKC label equality only; no guessed offsets, folios or numeral translations."""
    return unicodedata.normalize("NFKC", label).strip()


def _label_token(text, labels):
    value = normalize_label(text.strip("()[]{}"))
    if not value or len(value.split()) != 1:
        return None
    if value in labels:
        return value
    if not regex.fullmatch(r"[\p{L}\p{N}\p{Pd}]+", value):
        return None
    if _DIGIT.search(value) or _ROMAN.fullmatch(value):
        return value
    return None


def _title_bounds(text, start, end):
    while start < end and (text[start].isspace() or text[start] in ".\u00b7\u2024\u2025\u2026_"):
        start += 1
    while end > start and (
        text[end - 1].isspace() or text[end - 1] in ".\u00b7\u2024\u2025\u2026_"
    ):
        end -= 1
    return start, end


def _refs(page, line, start=0, end=None):
    """Ranges use original span text, preserving normalization and direction evidence."""
    end = len(page.store.raw_line_text(line)) if end is None else end
    result, offset = [], 0
    for sid in line.span_ids:
        length = len(page.store.spans[sid].raw_text)
        lo, hi = max(start, offset), min(end, offset + length)
        if lo < hi:
            result.append({"span_id": sid, "start": lo - offset, "end": hi - offset})
        offset += length
    return result


def _size(page, line):
    weights = [
        (page.store.spans[s].size, max(1, len(page.store.spans[s].raw_text))) for s in line.span_ids
    ]
    total = sum(weight for _, weight in weights)
    running = 0
    for size, weight in sorted(weights):
        running += weight
        if running * 2 >= total:
            return max(size, 0.01)
    return 1.0


def _rtl(text):
    strong = [unicodedata.bidirectional(c) for c in text]
    return sum(c in {"R", "AL"} for c in strong) > strong.count("L")


def _inline(page, line, labels):
    text = page.store.raw_line_text(line)
    for match in _LEADER.finditer(text):
        for at_end in (True, False):
            lo, hi = (match.end(), len(text)) if at_end else (0, match.start())
            label_text = text[lo:hi].strip()
            label = _label_token(label_text, labels)
            if label is None:
                continue
            start, end = (
                _title_bounds(text, 0, match.start())
                if at_end
                else _title_bounds(text, match.end(), len(text))
            )
            if len(_LETTER.findall(text[start:end])) < 2:
                continue
            label_start = lo + len(text[lo:hi]) - len(text[lo:hi].lstrip())
            return {
                "line_ids": [line.id],
                "title_refs": _refs(page, line, start, end),
                "target_label": label,
                "label_refs": _refs(page, line, label_start, label_start + len(label_text)),
                "bbox": line.bbox.model_dump(),
                "label_bbox": line.bbox.model_dump(),
                "font_size": _size(page, line),
                "reference_side": "suffix" if at_end else "prefix",
                "leaders": True,
                "split_cells": False,
                "wrapped": False,
            }
    words = list(_WORD.finditer(text))
    if len(words) < 2:
        return None
    leader = bool(_LEADER.search(text))
    # Try both ends, preserving native string order. A leading reference without a leader
    # needs right-to-left evidence so numbered titles do not masquerade as page references.
    for at_end in (True, False):
        word = words[-1] if at_end else words[0]
        label = _label_token(word.group(), labels)
        if label is None or (not at_end and not leader and not _rtl(text)):
            continue
        start, end = (
            _title_bounds(text, 0, word.start())
            if at_end
            else _title_bounds(text, word.end(), len(text))
        )
        title = text[start:end]
        if len(_LETTER.findall(title)) < 2:
            continue
        return {
            "line_ids": [line.id],
            "title_refs": _refs(page, line, start, end),
            "target_label": label,
            "label_refs": _refs(page, line, word.start(), word.end()),
            "bbox": line.bbox.model_dump(),
            "label_bbox": line.bbox.model_dump(),
            "font_size": _size(page, line),
            "reference_side": "suffix" if at_end else "prefix",
            "leaders": leader,
            "split_cells": False,
            "wrapped": False,
        }
    return None


def _direction(page, line, geometry):
    evidence = geometry.get(line.id, {})
    direction = evidence.get("direction")
    if direction is None:
        vertical = any(page.store.spans[s].text_direction == "ttb" for s in line.span_ids)
        direction = (0.0, 1.0) if vertical else (1.0, 0.0)
    length = math.hypot(*direction)
    if not length or not math.isfinite(length):
        raise ValueError("Native line direction must be finite and nonzero")
    return tuple(value / length for value in direction)


def _project(box, direction):
    dx, dy = direction
    corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x0, box.y1), (box.x1, box.y1)]
    along = [x * dx + y * dy for x, y in corners]
    normal = [-x * dy + y * dx for x, y in corners]
    return {"a0": min(along), "a1": max(along), "n0": min(normal), "n1": max(normal)}


def _row_overlap(a, b):
    height = max(0.01, min(a["n1"] - a["n0"], b["n1"] - b["n0"]))
    return max(0, min(a["n1"], b["n1"]) - max(a["n0"], b["n0"])) / height


def _same_direction(a, b):
    return a[0] * b[0] + a[1] * b[1] > 0.999


def _decorate(page, line, entry, geometry):
    direction = _direction(page, line, geometry)
    entry["direction"] = list(direction)
    entry["frame_bbox"] = _project(line.bbox, direction)
    entry["frame_label_bbox"] = _project(line.bbox, direction)
    return entry


def _split_cells(page, lines, labels, used, config, geometry):
    """Compare both sides first; repeated locator edges can outweigh a nearer gutter title."""
    locators = []
    for locator in lines:
        if locator.id in used:
            continue
        label = _label_token(page.store.raw_line_text(locator).strip(), labels)
        if label is None:
            continue
        direction = _direction(page, locator, geometry)
        frame = _project(locator.bbox, direction)
        options = {}
        for title in lines:
            if title.id == locator.id or title.id in used:
                continue
            text = page.store.raw_line_text(title)
            if len(_LETTER.findall(text)) < 2 or not _same_direction(
                direction, _direction(page, title, geometry)
            ):
                continue
            title_frame = _project(title.bbox, direction)
            if _row_overlap(frame, title_frame) < config.row_overlap:
                continue
            if title_frame["a1"] <= frame["a0"]:
                side, gap = "suffix", frame["a0"] - title_frame["a1"]
            elif frame["a1"] <= title_frame["a0"]:
                side, gap = "prefix", title_frame["a0"] - frame["a1"]
            else:
                continue
            if side not in options or gap < options[side][0]:
                options[side] = (gap, title, title_frame)
        if options:
            locators.append(
                {
                    "line": locator,
                    "label": label,
                    "direction": direction,
                    "frame": frame,
                    "options": options,
                }
            )
    groups = []
    for locator in locators:
        center = (locator["frame"]["a0"] + locator["frame"]["a1"]) / 2
        size = _size(page, locator["line"])
        group = next(
            (
                g
                for g in groups
                if _same_direction(g["direction"], locator["direction"])
                and abs(g["center"] - center)
                <= config.alignment_tolerance_fonts * max(g["font_size"], size)
            ),
            None,
        )
        if group is None:
            group = {
                "direction": locator["direction"],
                "center": center,
                "font_size": size,
                "locators": [],
            }
            groups.append(group)
        group["locators"].append(locator)
    candidates = []
    for group in groups:
        votes = defaultdict(int)
        for locator in group["locators"]:
            nearest = min(locator["options"], key=lambda side: locator["options"][side][0])
            votes[nearest] += 1
        majority_side = max(votes, key=votes.get)
        support = votes[majority_side] / len(group["locators"])
        repeated = (
            len(group["locators"]) >= config.minimum_entries and support >= config.pairing_majority
        )
        for locator in group["locators"]:
            options = locator["options"]
            side = (
                majority_side
                if repeated and majority_side in options
                else min(options, key=lambda s: options[s][0])
            )
            gap, title, title_frame = options[side]
            raw_title = page.store.raw_line_text(title)
            start, end = _title_bounds(raw_title, 0, len(raw_title))
            ambiguous = not repeated or majority_side not in options
            alternatives = []
            for alternate_side, (alternate_gap, alternate, _) in options.items():
                if alternate_side == side:
                    continue
                raw_alternate = page.store.raw_line_text(alternate)
                lo, hi = _title_bounds(raw_alternate, 0, len(raw_alternate))
                alternatives.append(
                    {
                        "reference_side": alternate_side,
                        "title_refs": _refs(page, alternate, lo, hi),
                        "line_ids": [alternate.id],
                        "gap_fonts": alternate_gap / _size(page, alternate),
                    }
                )
            candidates.append(
                {
                    "line_ids": [title.id, locator["line"].id],
                    "title_refs": _refs(page, title, start, end),
                    "label_refs": _refs(page, locator["line"]),
                    "target_label": locator["label"],
                    "bbox": title.bbox.model_dump(),
                    "label_bbox": locator["line"].bbox.model_dump(),
                    "font_size": _size(page, title),
                    "reference_side": side,
                    "leaders": bool(_LEADER.search(raw_title)),
                    "split_cells": True,
                    "wrapped": False,
                    "direction": list(locator["direction"]),
                    "frame_bbox": title_frame,
                    "frame_label_bbox": locator["frame"],
                    "pairing_ambiguous": ambiguous,
                    "pairing_selected_by": "repeated_locator_side"
                    if not ambiguous
                    else "nearest_geometry_ambiguous",
                    "pairing_side_support": round(support, 4),
                    "pairing_edge_group_size": len(group["locators"]),
                    "pairing_gap_fonts": gap / _size(page, title),
                    "alternate_title_refs": alternatives,
                }
            )
    # Listing remains the source locator order, independent of columns or coordinates.
    source_order = {line.id: i for i, line in enumerate(lines)}
    return sorted(candidates, key=lambda item: source_order[item["line_ids"][-1]])


def _multiple_numeric_columns(page, lines, candidates, labels, geometry, config):
    ambiguous = 0
    for item in candidates:
        direction = item["direction"]
        row = [
            line
            for line in lines
            if _same_direction(direction, _direction(page, line, geometry))
            and _row_overlap(item["frame_bbox"], _project(line.bbox, direction))
            >= config.row_overlap
        ]
        numbers = sum(
            _label_token(page.store.raw_line_text(line).strip(), labels) is not None
            and not _LETTER.search(page.store.raw_line_text(line))
            for line in row
        )
        titles = sum(len(_LETTER.findall(page.store.raw_line_text(line))) >= 2 for line in row)
        # Multiple title/reference pairs on one baseline are valid multi-column evidence.
        # More numeric fields than text fields instead supports a numeric table structure.
        ambiguous += numbers > titles
    return ambiguous / len(candidates) >= 0.6


def resolve_title(entry: dict, pages: Sequence[ExtractedPage]) -> str:
    """Resolve source ranges on demand; printed titles are never copied into evidence."""
    if entry.get("kind") == "bookmark":
        return entry["title"]
    page = next(p for p in pages if p.geometry.page == entry["source_page"])
    parts = []
    previous = None
    for ref in entry["title_refs"]:
        span = page.store.spans[ref["span_id"]]
        if previous is not None and previous != span.line_id:
            parts.append(" ")
        parts.append(span.raw_text[ref["start"] : ref["end"]])
        previous = span.line_id
    return unicodedata.normalize("NFKC", "".join(parts)).strip()


def _wrap_native_blocks(page, lines, candidates, config, native_blocks):
    """Native block continuity is title evidence only, never a paragraph decision."""
    by_id = {line.id: line for line in lines}
    membership = defaultdict(list)
    blocks = {}
    for ordinal, block in enumerate(native_blocks):
        if block["page"] != page.geometry.page:
            continue
        blocks[ordinal] = block["line_ids"]
        for line_id in block["line_ids"]:
            membership[line_id].append(ordinal)
    for item in candidates:
        item["incomplete_wrap"] = False
        groups = {group for line_id in item["line_ids"] for group in membership[line_id]}
        if (
            item.get("pairing_ambiguous")
            or len(groups) != 1
            or any(len(membership[line_id]) != 1 for line_id in item["line_ids"])
        ):
            item["incomplete_wrap"] = True
            item["wrap_method"] = "native_block_mapping_or_pairing_ambiguous"
            continue
        group = next(iter(groups))
        block_lines = blocks[group]
        represented = sum(
            any(line_id in block_lines for line_id in candidate["line_ids"])
            for candidate in candidates
        )
        if represented != 1:
            item["incomplete_wrap"] = True
            item["wrap_method"] = "multiple_entries_in_native_block"
            continue
        title_lines = {page.store.spans[ref["span_id"]].line_id for ref in item["title_refs"]}
        first = min(block_lines.index(line_id) for line_id in title_lines)
        preceding = []
        for line_id in reversed(block_lines[:first]):
            line = by_id.get(line_id)
            if line is None:
                item["incomplete_wrap"] = True
                break
            text = page.store.raw_line_text(line)
            if len(_LETTER.findall(text)) < 2 or _label_token(text.strip(), {}) is not None:
                break
            preceding.append(line)
        capacity = max(0, config.maximum_title_lines - len(title_lines))
        if len(preceding) > capacity:
            item["incomplete_wrap"] = True
        prepend = list(reversed(preceding[:capacity]))
        item["wrap_method"] = "single_entry_native_extraction_block"
        if prepend:
            item["title_refs"] = [ref for line in prepend for ref in _refs(page, line)] + item[
                "title_refs"
            ]
            item["line_ids"] = [line.id for line in prepend] + item["line_ids"]
            item["wrapped"] = True


def _wrap_titles(page, lines, candidates, config, geometry, native_blocks=None):
    """Prefer extraction blocks; geometry-only fallback is explicit for custom extractors."""
    if native_blocks is not None:
        _wrap_native_blocks(page, lines, candidates, config, native_blocks)
        return
    used = {line_id for item in candidates for line_id in item["line_ids"]}
    ordinal = {line.id: i for i, line in enumerate(lines)}
    for item in candidates:
        if item.get("pairing_ambiguous"):
            continue
        current = item["frame_bbox"]
        previous_ordinal = ordinal[item["line_ids"][0]]
        prepend = []
        for _ in range(config.maximum_title_lines - 1):
            possible = []
            for line in lines:
                if line.id in used or ordinal[line.id] >= previous_ordinal:
                    continue
                if len(_LETTER.findall(page.store.raw_line_text(line))) < 2 or not _same_direction(
                    item["direction"], _direction(page, line, geometry)
                ):
                    continue
                frame = _project(line.bbox, item["direction"])
                gap = max(current["n0"] - frame["n1"], frame["n0"] - current["n1"])
                if not -0.2 * item["font_size"] <= gap <= 0.8 * item["font_size"]:
                    continue
                edge = "a1" if item["reference_side"] == "prefix" else "a0"
                if abs(frame[edge] - current[edge]) > 0.75 * item["font_size"]:
                    continue
                possible.append((abs(gap), line, frame))
            if len(possible) != 1:
                break
            _, line, current = possible[0]
            previous_ordinal = ordinal[line.id]
            prepend.insert(0, line)
            used.add(line.id)
        if prepend:
            item["title_refs"] = [ref for line in prepend for ref in _refs(page, line)] + item[
                "title_refs"
            ]
            item["line_ids"] = [line.id for line in prepend] + item["line_ids"]
            item["wrapped"] = True


def analyze_navigation(pages: Sequence[ExtractedPage], metadata: dict, config=None) -> dict:
    config = (
        NavigationConfig(**config) if isinstance(config, dict) else (config or NavigationConfig())
    )
    pages = list(pages)
    source = metadata.get("source_sha256")
    if any(p.source_sha256 != source for p in pages):
        raise ValueError("Navigation metadata and native pages belong to different sources")
    if len({p.geometry.page for p in pages}) != len(pages):
        raise ValueError("Duplicate page in document navigation input")
    labels = defaultdict(list)
    for row in metadata.get("page_labels", []):
        label = normalize_label(row.get("label", ""))
        if label:
            labels[label].append(row["page"])
    labels = {label: sorted(set(numbers)) for label, numbers in labels.items()}
    bookmarks = []
    for ordinal, item in enumerate(metadata.get("bookmarks", [])):
        target = item.get("target_page")
        bookmarks.append(
            {
                "id": item.get("id", stable_id(source, "bookmark", ordinal)),
                "kind": "bookmark",
                "title": item["title"],
                "source_page": None,
                "target_page": target,
                "target_pages": [target] if target is not None else [],
                "target_label": next(
                    (r["label"] for r in metadata.get("page_labels", []) if r["page"] == target),
                    None,
                ),
                "level_evidence": {"outline_depth": item["depth"]},
                "confidence": 1.0 if target is not None else 0.5,
                "action_kind": item.get("action_kind"),
            }
        )
    geometry = metadata.get("line_geometry", {})
    printed, toc_pages = [], []
    for page in pages:
        lines = [
            line
            for line in page.store.lines
            if page.store.raw_line_text(line).strip()
            and page.geometry.content_bbox.contains_center(line.bbox)
        ]
        candidates = [
            _decorate(page, line, entry, geometry)
            for line in lines
            if (entry := _inline(page, line, labels)) is not None
        ]
        used = {line_id for entry in candidates for line_id in entry["line_ids"]}
        candidates.extend(_split_cells(page, lines, labels, used, config, geometry))
        if len(candidates) < config.minimum_entries or _multiple_numeric_columns(
            page, lines, candidates, labels, geometry, config
        ):
            continue
        density = len({line_id for c in candidates for line_id in c["line_ids"]}) / max(
            len(lines), 1
        )
        leaders = sum(c["leaders"] for c in candidates)
        resolved = sum(c["target_label"] in labels for c in candidates)
        # Repeated title starts or locator edges support multi-column structures too: each
        # entry needs two local peers, rather than one fixed column count or global ordering.
        aligned = 0
        for candidate in candidates:
            edge = (
                candidate["frame_label_bbox"]["a0"]
                if candidate["reference_side"] == "prefix"
                else candidate["frame_label_bbox"]["a1"]
            )
            peers = sum(
                _same_direction(other["direction"], candidate["direction"])
                and (
                    other["reference_side"] == candidate["reference_side"]
                    or bool(other.get("pairing_ambiguous", False))
                    or bool(candidate.get("pairing_ambiguous", False))
                )
                and abs(
                    (
                        other["frame_label_bbox"]["a0"]
                        if other["reference_side"] == "prefix"
                        else other["frame_label_bbox"]["a1"]
                    )
                    - edge
                )
                <= config.alignment_tolerance_fonts
                * max(candidate["font_size"], other["font_size"])
                for other in candidates
            )
            aligned += peers >= config.minimum_entries
        structure = aligned / len(candidates)
        strong = leaders >= config.minimum_entries or (
            resolved >= config.minimum_entries and structure >= 0.6
        )
        geometry_only = (
            sum(c["split_cells"] for c in candidates) >= config.minimum_entries and structure >= 0.8
        )
        if (
            not (strong or geometry_only)
            or density < config.minimum_reference_density
            or structure < 0.6
        ):
            continue
        _wrap_titles(page, lines, candidates, config, geometry, metadata.get("native_blocks"))
        confidence = min(
            0.98, 0.45 + 0.2 * structure + 0.2 * density + 0.1 * leaders / len(candidates)
        )
        if not strong:
            confidence = min(0.6, 0.3 + 0.15 * structure + 0.15 * density)
        toc_pages.append(
            {
                "page": page.geometry.page,
                "confidence": round(confidence, 4),
                "features": {
                    "entries": len(candidates),
                    "reference_density": round(density, 4),
                    "leader_entries": leaders,
                    "resolved_labels": resolved,
                    "repeated_alignment": round(structure, 4),
                    "geometry_only_ambiguous": not strong,
                    "ambiguous_pairings": sum(bool(c.get("pairing_ambiguous")) for c in candidates),
                },
                "reasons": [
                    "Repeated page-reference rows",
                    "Shared locator-edge geometry",
                    "Leaders or resolved PDF labels"
                    if strong
                    else "Geometry-only navigation/table ambiguity",
                ],
            }
        )

        for ordinal, candidate in enumerate(candidates):
            targets = labels.get(candidate["target_label"], [])
            edge = (
                candidate["frame_bbox"]["a1"]
                if candidate["reference_side"] == "prefix"
                else candidate["frame_bbox"]["a0"]
            )
            content = _project(page.geometry.content_bbox, candidate["direction"])
            indent = (
                content["a1"] - edge
                if candidate["reference_side"] == "prefix"
                else edge - content["a0"]
            ) / candidate["font_size"]
            candidate.update(
                {
                    "id": stable_id(
                        source, "printed-navigation", page.geometry.page, *candidate["line_ids"]
                    ),
                    "kind": "printed_toc",
                    "source_page": page.geometry.page,
                    "target_page": targets[0] if len(targets) == 1 else None,
                    "target_pages": targets,
                    "label_link_confidence": 1.0
                    if len(targets) == 1
                    else (0.5 if targets else 0.0),
                    "level_evidence": {
                        "indentation_fonts": round(indent, 4),
                        "reference_side": candidate["reference_side"],
                    },
                    "confidence": round(
                        confidence * (0.65 if candidate.get("pairing_ambiguous") else 1.0), 4
                    ),
                    "geometry_only_ambiguous": not strong,
                    "native_candidate_ordinal": ordinal,
                }
            )
            printed.append(candidate)
    return {
        "source_sha256": source,
        "config": asdict(config),
        "page_labels": metadata.get("page_labels", []),
        "page_label_definitions": metadata.get("page_label_definitions", []),
        "bookmarks": bookmarks,
        "toc_pages": toc_pages,
        "printed_entries": printed,
        "entries": bookmarks + printed,
        "limitations": [
            "Confidence is heuristic, not calibrated",
            "Missing PDF labels stay unresolved; no offset is guessed",
            "Outline depth and indentation do not decide headings",
            "Short TOCs below the repeated-row minimum stay unreported",
            "Leaderless unresolved repeated rows may be tables; "
            "they remain lower-confidence evidence",
            "Split-cell side ambiguity retains alternate source title ranges",
            "Native blocks with multiple entries or ambiguous mapping "
            "retain incomplete title wraps",
            "Custom extractors without native blocks use geometry-only title wrap evidence",
        ],
    }


def resolve_entry_title(
    entry: dict, pages: Mapping[int, ExtractedPage] | Sequence[ExtractedPage]
) -> str:
    """Convenience resolver accepting the page-number mapping used by overlays and scoring."""
    return resolve_title(entry, list(pages.values()) if isinstance(pages, Mapping) else pages)
