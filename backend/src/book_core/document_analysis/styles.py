"""Character-weighted whole-book typography evidence without role decisions.

Confidence is an observed character share, not a calibrated probability. The modal
style is a body-style candidate; the complete distribution remains reviewable.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from book_core.extraction.fingerprints import stable_id
from book_core.model.spans import ExtractedPage, SourceLine, TextSpan

_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
_STYLE_SUFFIX = re.compile(
    r"(?:[\s,_-]+(?:regular|roman|normal|medium|light|thin|book|black|"
    r"(?:semi|demi|extra|ultra)?bold(?:italic|oblique)?|italic|oblique)(?:mt)?)$",
    re.IGNORECASE,
)


def normalize_font_family(font: str) -> str:
    """Remove PDF subset identity and delimited generic weight/slant suffixes.

    Native flags, rather than font-name spelling, supply bold and italic evidence.
    Unrecognised or non-delimited suffixes are deliberately retained.
    """
    family = unicodedata.normalize("NFKC", _SUBSET_PREFIX.sub("", font)).strip()
    while (stripped := _STYLE_SUFFIX.sub("", family)) != family:
        family = stripped
    return " ".join(family.casefold().split())


def _caps(text: str) -> str:
    cased = "".join(character for character in text if character.lower() != character.upper())
    if not cased:
        return "uncased"
    if cased.isupper():
        return "upper"
    if cased.islower():
        return "lower"
    if text.istitle():
        return "title"
    return "mixed"


@dataclass(frozen=True, order=True)
class _Style:
    font_family: str
    size: float
    bold: bool
    italic: bool
    color: int
    caps: str

    @property
    def key(self) -> str:
        return stable_id("document-style", json.dumps(asdict(self), sort_keys=True))


def _span_style(span: TextSpan) -> _Style:
    size = float(Decimal(str(span.size)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return _Style(
        font_family=normalize_font_family(span.font),
        size=size,
        bold=bool(span.flags & 16),
        italic=bool(span.flags & 2),
        color=span.color,
        caps=_caps(span.text),
    )


def _character_count(text: str) -> int:
    return sum(not character.isspace() for character in text)


def build_style_profile(
    pages: list[ExtractedPage], *, size_cluster_tolerance: float = 0.035
) -> dict[str, Any]:
    """Return distributions, clusters and per-native-line evidence deterministically.

    Sizes round half-up to a tenth of a point. A size cluster's max/min ratio is at
    most 1 + tolerance; complete-link bounds prevent chaining. Style clusters share
    family, weight, slant, colour and caps within a size cluster. Character weights
    count original non-whitespace Unicode codepoints. A mixed-style line retains
    its complete distribution. No line is assigned a semantic role.
    """
    if not math.isfinite(size_cluster_tolerance) or not 0 <= size_cluster_tolerance < 1:
        raise ValueError("Size-cluster tolerance must be finite and in [0, 1)")
    if len({page.source_sha256 for page in pages}) > 1:
        raise ValueError("Document evidence must describe one source")
    if len({page.geometry.page for page in pages}) != len(pages):
        raise ValueError("Duplicate extracted page in document evidence")
    weights: Counter[_Style] = Counter()
    span_counts: Counter[_Style] = Counter()
    line_evidence: list[tuple[ExtractedPage, SourceLine, Counter[_Style]]] = []
    for page in pages:
        for line in page.store.lines:
            line_weights: Counter[_Style] = Counter()
            for sid in line.span_ids:
                span = page.store.spans[sid]
                style = _span_style(span)
                count = _character_count(span.raw_text)
                weights[style] += count
                span_counts[style] += 1
                line_weights[style] += count
            line_evidence.append((page, line, line_weights))

    ordered_styles = sorted(weights, key=lambda style: (-weights[style], style))
    total = sum(weights.values())
    body = ordered_styles[0] if ordered_styles and total else None
    size_weights: Counter[float] = Counter()
    for style, count in weights.items():
        size_weights[style.size] += count
    size_groups: list[list[float]] = []
    for size in sorted(size_weights):
        if (
            not size_groups
            or (size_groups[-1][0] == 0 and size != 0)
            or size > size_groups[-1][0] * (1 + size_cluster_tolerance)
        ):
            size_groups.append([size])
        else:
            size_groups[-1].append(size)
    size_ids = {
        size: stable_id("document-size-cluster", *group) for group in size_groups for size in group
    }
    clusters: dict[str, list[_Style]] = defaultdict(list)
    style_cluster_ids: dict[_Style, str] = {}
    for style in sorted(weights):
        descriptor = {**asdict(style), "size_cluster_id": size_ids[style.size]}
        del descriptor["size"]
        cluster_id = stable_id("document-style-cluster", json.dumps(descriptor, sort_keys=True))
        clusters[cluster_id].append(style)
        style_cluster_ids[style] = cluster_id

    lines: list[dict[str, Any]] = []
    for page, line, line_weights in line_evidence:
        count = sum(line_weights.values())
        dominant = min(line_weights, key=lambda style: (-line_weights[style], style), default=None)
        relation = None
        if body is not None and dominant is not None and count:
            weighted_size = sum(style.size * mass for style, mass in line_weights.items()) / count
            relation = {
                "size_ratio": weighted_size / body.size if body.size else None,
                "dominant_size_ratio": dominant.size / body.size if body.size else None,
                "bold": dominant.bold,
                "italic": dominant.italic,
                "bold_difference": dominant.bold != body.bold,
                "italic_difference": dominant.italic != body.italic,
                "caps_difference": dominant.caps != body.caps,
                "color_difference": dominant.color != body.color,
                "font_family_difference": dominant.font_family != body.font_family,
            }
        lines.append(
            {
                "line_id": line.id,
                "page": page.geometry.page,
                "span_ids": list(line.span_ids),
                "style_key": dominant.key if dominant else None,
                "style_cluster_id": style_cluster_ids.get(dominant) if dominant else None,
                "character_count": count,
                "style_weights": {style.key: mass for style, mass in sorted(line_weights.items())},
                "confidence": line_weights[dominant] / count if dominant and count else 0.0,
                "body_relation": relation,
            }
        )
    return {
        "method": "character-weighted-native-style-evidence-v1",
        "character_weight": "original_non_whitespace_codepoints",
        "size_rounding": "0.1pt_half_up",
        "size_cluster_tolerance": size_cluster_tolerance,
        "total_characters": total,
        "body_style_key": body.key if body else None,
        "body_confidence": weights[body] / total if body and total else 0.0,
        "confidence_interpretation": "observed_character_share_not_probability",
        "styles": [
            {
                "key": style.key,
                **asdict(style),
                "character_count": weights[style],
                "span_count": span_counts[style],
                "character_share": weights[style] / total if total else 0.0,
                "size_cluster_id": size_ids[style.size],
                "style_cluster_id": style_cluster_ids[style],
            }
            for style in ordered_styles
        ],
        "size_clusters": [
            {
                "id": size_ids[group[0]],
                "sizes": group,
                "character_count": sum(size_weights[size] for size in group),
            }
            for group in size_groups
        ],
        "style_clusters": [
            {
                "id": cluster_id,
                "style_keys": [style.key for style in members],
                "character_count": sum(weights[style] for style in members),
                "size_cluster_id": size_ids[members[0].size],
            }
            for cluster_id, members in sorted(clusters.items())
        ],
        "lines": lines,
    }
