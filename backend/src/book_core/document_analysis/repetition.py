"""Position-conditioned whole-book repetition, retained solely as candidates."""

from __future__ import annotations

import hashlib
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from statistics import median

import regex
from rapidfuzz.fuzz import ratio

from book_core.model.spans import ExtractedPage


@dataclass(frozen=True)
class RepetitionConfig:
    edge_fraction: float = 0.12
    position_tolerance: float = 0.035
    similarity: float = 92.0
    minimum_pages: int = 3

    def __post_init__(self):
        if not 0 < self.edge_fraction < 0.5 or not 0 < self.position_tolerance < 0.5:
            raise ValueError("Band fractions must lie between zero and one half")
        if not 0 < self.similarity <= 100 or self.minimum_pages < 2:
            raise ValueError("Invalid repetition support configuration")


def masked_key(text: str) -> str:
    text = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    return regex.sub(r"\p{N}", "#", text)


def build_repetition(pages: list[ExtractedPage], config: RepetitionConfig | None = None) -> dict:
    """Never change ownership. Physical page parity is evidence, not printed-label parity.

    Compare to a fixed representative, avoiding transitive fuzzy-match chains. The band
    uses the content frame, and position consistency is relative to its extent. No line
    ordering is inferred from position. Local coverage also supports chapter running heads.
    """
    config = config or RepetitionConfig()
    by_key = defaultdict(list)
    numbers = {p.geometry.page for p in pages}
    for page in pages:
        frame = page.geometry.content_bbox
        width, height = frame.x1 - frame.x0, frame.y1 - frame.y0
        for line in page.store.lines:
            raw = page.store.raw_line_text(line)
            if not raw.strip() or not frame.contains_center(line.bbox):
                continue
            x = ((line.bbox.x0 + line.bbox.x1) / 2 - frame.x0) / width
            y = ((line.bbox.y0 + line.bbox.y1) / 2 - frame.y0) / height
            bands = []
            if y <= config.edge_fraction:
                bands.append(("top", y))
            if y >= 1 - config.edge_fraction:
                bands.append(("bottom", y))
            if x <= config.edge_fraction or x >= 1 - config.edge_fraction:
                bands.append(("side", x))
            key = masked_key(raw)
            for band, position in bands:
                by_key[band, key].append(
                    {"page": line.page, "line_id": line.id, "position": position}
                )
    groups = []
    # Partition exact keys by geometry first: one text value can occur at both side
    # edges. Its pooled median must not hide one position from a nearby fuzzy variant.
    # These sorts cluster position evidence only; native source order is untouched.
    for (band, key), occurrences in sorted(by_key.items()):
        remaining = sorted(
            occurrences, key=lambda row: (row["position"], row["page"], row["line_id"])
        )
        while remaining:
            anchor = remaining[0]["position"]
            partition = [
                row for row in remaining if row["position"] - anchor <= config.position_tolerance
            ]
            remaining = [
                row for row in remaining if row["position"] - anchor > config.position_tolerance
            ]
            center = median(row["position"] for row in partition)
            lower = min(row["position"] for row in partition)
            upper = max(row["position"] for row in partition)
            group = next(
                (
                    candidate
                    for candidate in groups
                    if candidate["band"] == band
                    and abs(candidate["position"] - center) <= config.position_tolerance
                    and max(candidate["position_max"], upper)
                    - min(candidate["position_min"], lower)
                    <= config.position_tolerance
                    and ratio(key, candidate["key"]) >= config.similarity
                ),
                None,
            )
            if group is None:
                group = {
                    "band": band,
                    "key": key,
                    "position": center,
                    "position_min": lower,
                    "position_max": upper,
                    "rows": [],
                }
                groups.append(group)
            # Keep the lexical representative fixed; bounds prevent position chaining.
            similarity = ratio(key, group["key"]) / 100
            group["rows"].extend({**row, "similarity": similarity} for row in partition)
            group["position_min"] = min(group["position_min"], lower)
            group["position_max"] = max(group["position_max"], upper)
    candidates = []
    for group in groups:
        # Split exact repeated text at distinct positions, including opposite side edges.
        remaining = sorted(group["rows"], key=lambda r: (r["position"], r["page"], r["line_id"]))
        while remaining:
            anchor = remaining[0]["position"]
            rows = [r for r in remaining if r["position"] - anchor <= config.position_tolerance]
            remaining = [r for r in remaining if r["position"] - anchor > config.position_tolerance]
            support = sorted({r["page"] for r in rows})
            if len(support) < config.minimum_pages:
                continue
            local_pages = {n for n in numbers if support[0] <= n <= support[-1]}
            parity = {}
            for name, remainder in (("odd", 1), ("even", 0)):
                observed = sum(n % 2 == remainder for n in support)
                exposure = sum(n % 2 == remainder for n in local_pages)
                parity[name] = {
                    "pages": observed,
                    "local_exposure": exposure,
                    "local_coverage": observed / exposure if exposure else 0.0,
                }
            odd_share = parity["odd"]["pages"] / len(support)
            period = "odd" if odd_share >= 0.8 else "even" if odd_share <= 0.2 else "mixed"
            coverage = len(support) / max(len(local_pages), 1)
            if period != "mixed":
                coverage = parity[period]["local_coverage"]
            similarities = [r["similarity"] for r in rows]
            # Confidence is an explicit support heuristic, never a probability of furniture.
            confidence = min(1.0, len(support) / 6) * (0.5 + 0.5 * coverage) * min(similarities)
            identity = f"{group['band']}:{group['key']}:{anchor:.6f}"
            candidates.append(
                {
                    "id": "repeat-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                    "band": group["band"],
                    "occurrences": rows,
                    "pages": support,
                    "page_coverage": len(support) / max(len(numbers), 1),
                    "local_page_coverage": len(support) / max(len(local_pages), 1),
                    "periodicity": period,
                    "parity": parity,
                    "position_center": median(r["position"] for r in rows),
                    "position_spread": max(r["position"] for r in rows) - anchor,
                    "digit_only": not bool(regex.search(r"\p{L}", group["key"])),
                    "confidence": round(confidence, 6),
                    "decision": None,
                }
            )
    return {
        "config": asdict(config),
        "candidates": candidates,
        "confidence_method": "support saturation * local parity coverage * text similarity",
        "page_parity": "physical one-based PDF pages; printed labels may differ",
    }
