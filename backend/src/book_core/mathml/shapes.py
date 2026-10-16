"""Characters of recurring drawn glyph shapes, recognised once per book.

A producer that draws equations as filled outlines repeats one outline per character at any
size (``equations.glyphs.shape_signature`` is scale- and position-free). Each shape is
recognised once, from two kinds of model evidence:

1. **Isolated reading**: the outline is rasterized alone (its own path, no neighbours) and
   read by the formula recognizer; upright markup (``\\mathrm``, ``\\mathbf``, ``\\mathsf``)
   marks an upright letter.
2. **Context votes**: in every equation whose image-path reading has exactly as many
   characters as the provisional drawn reading, aligned characters vote for the shapes they
   fall on. Votes are kept per vertical position class (on the baseline, on the math axis,
   raised), so a shape that is a decimal point on the baseline and a product dot on the
   axis gets both readings.

Geometry is learned from the book as well: a shape's unit height is the height of its tallest
well-populated size cluster (scripts are smaller copies), and its descent below the baseline
is the median offset of its bottom from the baseline of the glyphs set beside it.
"""

import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import cv2
import numpy as np

from book_core.equations import glyphs as glyph_rules

RASTER_HEIGHT = 64  # pixels of a rendered shape
RASTER_PAD = 24
CURVE_STEPS = 16
SIZE_CLUSTER = 1.1  # heights within this ratio form one size cluster
CLUSTER_SHARE = 0.15  # a unit-size cluster holds at least this share of occurrences
ROW_OVERLAP = 0.5
MIN_VOTES = 3
VOTE_SHARE = 0.6
LOW, MID = 0.15, 0.45  # centre above the row baseline, in sizes: baseline / axis / raised
ISOLATED_CONFIDENCE = 0.8
AGREED_CONFIDENCE = 0.95
CONTEXT_CONFIDENCE = 0.85
DISPUTED_CONFIDENCE = 0.6
UPRIGHT = ("\\mathrm", "\\mathbf", "\\mathsf", "\\textrm", "\\text", "\\operatorname", "\\upmu")
CONFIG = {
    "raster_height": RASTER_HEIGHT,
    "raster_pad": RASTER_PAD,
    "curve_steps": CURVE_STEPS,
    "size_cluster": SIZE_CLUSTER,
    "cluster_share": CLUSTER_SHARE,
    "row_overlap": ROW_OVERLAP,
    "min_votes": MIN_VOTES,
    "vote_share": VOTE_SHARE,
    "position_classes": [LOW, MID],
}


@dataclass
class ShapeLabel:
    char: str | None
    italic: bool | None
    confidence: float
    isolated: str | None = None  # the isolated reading (characters) or None
    isolated_latex: str | None = None
    votes: dict = field(default_factory=dict)  # {position class: {char: count}}
    by_position: dict = field(default_factory=dict)  # {position class: char} overrides
    flags: list = field(default_factory=list)

    def record(self):
        return {
            "char": self.char,
            "italic": self.italic,
            "confidence": self.confidence,
            "isolated": self.isolated,
            "isolated_latex": self.isolated_latex,
            "votes": self.votes,
            "by_position": self.by_position,
            "flags": self.flags,
        }


class ShapeTable:
    """Labels and learned geometry of a book's drawn shapes."""

    def __init__(self, labels=None, unit=None, descent=None):
        self.labels = labels or {}
        self.unit = unit or {}
        self.descents = descent or {}

    def label(self, signature, position=None):
        found = self.labels.get(signature)
        if found is None or found.char is None:
            return None
        if position is not None and position in found.by_position:
            return _Reading(found.by_position[position], found.italic)
        return _Reading(found.char, found.italic)

    def scale(self, signature, height):
        unit = self.unit.get(signature)
        return height / unit if unit else 1.0

    def descent(self, signature):
        return self.descents.get(signature, 0.0)


@dataclass
class _Reading:
    char: str
    italic: bool | None


# --- geometry ---------------------------------------------------------------------------


def unit_heights(heights_by_shape):
    """{signature: unit height}: the tallest size cluster holding a fair share of a shape's
    heights (scripts are smaller copies of the same outline)."""
    units = {}
    for signature, heights in heights_by_shape.items():
        ordered = sorted(heights)
        clusters, current = [], [ordered[0]]
        for height in ordered[1:]:
            if height > current[-1] * SIZE_CLUSTER:
                clusters.append(current)
                current = [height]
            else:
                current.append(height)
        clusters.append(current)
        need = max(1, CLUSTER_SHARE * len(ordered))
        kept = [c for c in clusters if len(c) >= need] or clusters
        units[signature] = statistics.median(kept[-1])
    return units


def _rows(items):
    """Groups of (signature, box, size) that share a row (vertical overlap, similar size)."""
    rows = []
    for item in sorted(items, key=lambda i: (i[1][1], i[1][0])):
        _, box, size = item
        placed = False
        for row in rows:
            _, other, other_size = row[0]
            overlap = min(box[3], other[3]) - max(box[1], other[1])
            small = min(box[3] - box[1], other[3] - other[1])
            if overlap >= ROW_OVERLAP * small and abs(size - other_size) <= 0.15 * other_size:
                row.append(item)
                placed = True
                break
        if not placed:
            rows.append([item])
    return rows


def descents(regions, units, book_size, rounds=2):
    """{signature: descent below the baseline, in sizes} from rows of glyphs in regions.

    ``regions``: [[(signature, box)]] per region."""
    found = {}
    for _ in range(rounds):
        offsets = defaultdict(list)
        for items in regions:
            sized = [
                (s, b, (b[3] - b[1]) / units[s] * book_size if units.get(s) else book_size)
                for s, b in items
            ]
            for row in _rows(sized):
                if len(row) < 3:
                    continue
                baselines = [b[3] - found.get(s, 0.0) * size for s, b, size in row]
                reference = statistics.median(baselines)
                for s, b, size in row:
                    offsets[s].append((b[3] - reference) / size)
        found = {s: statistics.median(v) for s, v in offsets.items() if len(v) >= MIN_VOTES}
    return found


def position_class(centre_above_baseline, size):
    ratio = centre_above_baseline / size if size else 0.0
    if ratio < LOW:
        return "baseline"
    if ratio < MID:
        return "axis"
    return "raised"


# --- isolated readings ------------------------------------------------------------------


def _contours(items, scale, ox, oy):
    contours, current, last = [], [], None

    def point(x, y):
        return ((x - ox) * scale, (y - oy) * scale)

    for item in items:
        values = item.coordinates
        points = [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]
        if item.operator == "re":
            if current:
                contours.append(current)
                current = []
            x0, y0, x1, y1 = values[:4]
            contours.append([point(x0, y0), point(x1, y0), point(x1, y1), point(x0, y1)])
            last = None
            continue
        start = points[0]
        if last is None or abs(start[0] - last[0]) > 1e-3 or abs(start[1] - last[1]) > 1e-3:
            if current:
                contours.append(current)
            current = [point(*start)]
        if item.operator == "l":
            current.append(point(*points[1]))
            last = points[1]
        elif item.operator == "c":
            p0, p1, p2, p3 = (np.array(p) for p in points[:4])
            for t in np.linspace(0, 1, CURVE_STEPS)[1:]:
                q = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2
                q = q + t**3 * p3
                current.append(point(*q))
            last = points[3]
        elif item.operator == "qu":
            current += [point(*p) for p in points[1:]] + [point(*points[0])]
            last = points[0]
    if current:
        contours.append(current)
    return contours


def rasterize(obj):
    """PNG bytes of one drawn outline alone, black on white, at a fixed height."""
    box = obj.bbox
    height = max(box.y1 - box.y0, 1e-6)
    scale = RASTER_HEIGHT / height
    width = int(np.ceil((box.x1 - box.x0) * scale)) + 2 * RASTER_PAD
    image = np.full((RASTER_HEIGHT + 2 * RASTER_PAD, max(width, 2 * RASTER_PAD + 1)), 255, np.uint8)
    contours = [
        np.round(np.array(c) + RASTER_PAD).astype(np.int32)
        for c in _contours(obj.path_items, scale, box.x0, box.y0)
        if len(c) >= 2
    ]
    if contours:
        cv2.fillPoly(image, contours, 0, lineType=cv2.LINE_AA)
    ok, data = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise ValueError("Could not encode a shape image")
    return data.tobytes()


def isolated_reading(latex):
    """(characters, italic) of a recognizer reading of one shape, or (None, None) when the
    reading has structure or is not one to three plain characters."""
    from book_core.mathml.latex import from_latex
    from book_core.mathml.tree import TOKENS, leaves

    tree = from_latex(latex)
    if tree is None:
        return None, None
    flat = tree.kind in TOKENS or (
        tree.kind == "row" and all(c.kind in TOKENS for c in tree.children)
    )
    text = "".join(leaves(tree)).replace(" ", "").replace(" ", "")
    if not flat or not 1 <= len(text) <= 3:
        return None, None
    letters = [c for c in text if unicodedata.category(c)[0] == "L"]
    italic = None
    if letters:
        italic = not any(marker in latex for marker in UPRIGHT)
    # Styled letters (mathematical bold, sans-serif) are their plain letters here: the
    # style is kept as ``italic``.
    return unicodedata.normalize("NFKC", text), italic


# --- decision ---------------------------------------------------------------------------


def decide(isolated, isolated_latex, italic, votes, fold):
    """ShapeLabel from the isolated reading and context votes {class: {char: count}}."""
    votes = {position: Counter(counter) for position, counter in votes.items()}
    total = Counter()
    for counter in votes.values():
        total.update(counter)
    flags = []
    char, confidence = None, 0.0
    if sum(total.values()) >= MIN_VOTES:
        top, count = total.most_common(1)[0]
        if count >= VOTE_SHARE * sum(total.values()):
            char = top
            agree = isolated is not None and fold(isolated) == fold(top)
            confidence = AGREED_CONFIDENCE if agree else CONTEXT_CONFIDENCE
            if isolated is not None and not agree:
                flags.append("context votes overrule the isolated reading")
    if char is None and isolated is not None:
        char = isolated
        confidence = ISOLATED_CONFIDENCE
        if total:
            top = total.most_common(1)[0][0]
            if fold(top) != fold(isolated):
                confidence = DISPUTED_CONFIDENCE
                flags.append("isolated reading and context votes disagree")
    by_position = {}
    if char is not None:
        for position, counter in votes.items():
            n = sum(counter.values())
            if n < MIN_VOTES:
                continue
            top, count = counter.most_common(1)[0]
            if count >= VOTE_SHARE * n and fold(top) != fold(char):
                by_position[position] = top
    if char is not None and len(char) == 1 and unicodedata.category(char)[0] != "L":
        italic = None
    return ShapeLabel(
        char=char,
        italic=italic,
        confidence=confidence,
        isolated=isolated,
        isolated_latex=isolated_latex,
        votes={p: dict(sorted(c.items())) for p, c in sorted(votes.items())},
        by_position=dict(sorted(by_position.items())),
        flags=flags,
    )


def shape_of(obj):
    """Signature of a drawn object that can carry a character (not a bar or rule)."""
    if obj.kind != "drawing" or obj.bbox is None or not obj.path_items:
        return None
    return glyph_rules.shape_signature(obj)
