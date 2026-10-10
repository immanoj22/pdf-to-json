"""Book-level evidence for paragraphs: line pitch per font size, and spelling attestations.

- Line pitch: the median baseline advance between consecutive lines of one Step 4 region in
  one Step 7 lane, per rounded font size, over the whole book. Gaps are judged against the
  local pitch, falling back to this profile, so thresholds follow the book's own typesetting.
- Spelling: the Step 6 casefolded vocabulary (unchanged rule) attests joined words; a
  compound lexicon counts hyphenated words written inside a line (never at a line end), which
  attests real compounds. Counts are evidence, not decisions.
"""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median

import regex

from book_core.paragraphs.geometry import frame

TOKEN = regex.compile(r"[\p{L}\p{M}\p{N}]+")
HYPHENS = "-‐‑"  # hard hyphens; U+00AD (soft hyphen) is handled separately
SOFT_HYPHEN = "­"
_COMPOUND = regex.compile(r"([\p{L}\p{M}\p{N}]+)[-‐‑]([\p{L}\p{M}\p{N}]+)")


def size_key(size):
    return round(size * 2) / 2


@dataclass
class Profile:
    """Mutable accumulator; ``freeze`` returns plain data for the cache key and the model."""

    advances: dict = field(default_factory=lambda: defaultdict(list))
    compounds: Counter = field(default_factory=Counter)

    def add_page(self, page, layout, order):
        region_of = {lid: r.id for r in layout.regions for lid in r.line_ids}
        lines = {line.id: line for line in layout.lines}
        sequence = {"next_in_lane", "next_in_stream"}
        for edge in order.edges:
            if edge.kind not in sequence:
                continue
            a, b = lines.get(edge.source), lines.get(edge.target)
            if a is None or b is None or region_of[a.id] != region_of[b.id]:
                continue
            fa, fb = frame(a), frame(b)
            if abs(fa.size - fb.size) > 0.25:
                continue
            advance = fb.block - fa.block
            if 0.5 * fa.size < advance < 3.0 * fa.size:
                self.advances[size_key(fa.size)].append(advance)
        store = page.store
        for line in store.lines:
            raw = store.raw_line_text(line)
            if not raw.strip() or not page.geometry.content_bbox.contains_center(line.bbox):
                continue
            text = unicodedata.normalize("NFKC", raw).rstrip()
            for match in _COMPOUND.finditer(text):
                if match.end() == len(text):
                    continue  # a line-end hyphen is the question, not evidence
                self.compounds[f"{match.group(1)}-{match.group(2)}".casefold()] += 1

    def freeze(self):
        pitch = {
            str(size): round(median(values), 4)
            for size, values in sorted(self.advances.items())
            if len(values) >= 5
        }
        return {"pitch_by_size": pitch, "compounds": dict(sorted(self.compounds.items()))}


def pitch_for(profile, size):
    """Book pitch for a font size: exact size, else the nearest profiled size scaled."""
    table = {float(k): v for k, v in profile["pitch_by_size"].items()}
    if not table:
        return 1.2 * size
    key = size_key(size)
    if key in table:
        return table[key]
    nearest = min(table, key=lambda k: abs(k - key))
    return table[nearest] * size / nearest


def hyphen_evidence(left, right, vocabulary, compounds):
    """Counts for a line-end hyphen between fragments ``left`` and ``right``."""
    joined = (left + right).casefold()
    compound = f"{left}-{right}".casefold()
    return {
        "joined_attested": int(vocabulary.get(joined, 0)),
        "compound_attested": int(compounds.get(compound, 0)),
        "left_attested": int(vocabulary.get(left.casefold(), 0)),
        "right_attested": int(vocabulary.get(right.casefold(), 0)),
    }
