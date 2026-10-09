"""Order-aware alignment of reference XML tokens to retained PDF tokens.

Stage A places reference segments (text between page markers, or fixed-size chunks when a
reference has none) on PDF pages with a Viterbi pass. Consecutive pages are free, staying or
skipping one page is cheap, and any other move is a penalised jump, so editorially moved blocks
are found without assuming one global order. Stage B aligns tokens inside each segment's page
window: unique anchors (tokens and n-grams unique on both sides), run extension, a weighted
order chain, LCS inside the gaps between chain runs, then joins/splits for hyphenation, soft
hyphens and spacing, and case/near variants. Moved runs survive only when long. Stage C spills
leftovers to neighbouring pages; stage D relocates long leftover runs anywhere when unique.

Every token ends aligned or carries an explicit unaligned cause. Nothing is guessed: ambiguous
single tokens without ordered context stay unaligned. The result is deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

import numpy as np

from book_core.model.common import BBox
from book_core.reference.pdf_tokens import PdfPage
from book_core.reference.xml_reader import ReferenceDocument

ALIGNMENT_VERSION = "reference-alignment-1"

# Base confidence of each alignment method, before the segment placement factor.
METHOD_CONFIDENCE = {
    "anchor": 1.0,
    "extension": 0.95,
    "gap": 0.9,
    "join_hyphen": 0.9,
    "join_soft_hyphen": 0.9,
    "moved": 0.85,
    "join_split": 0.75,
    "split": 0.75,
    "case": 0.7,
    "leftover": 0.6,
    "variant": 0.6,
    "spill": 0.5,
    "relocated": 0.5,
    "figure_label": 0.6,
    "context": 0.85,
}
XML_CAUSES = (
    "reference_metadata",
    "image_description",
    "no_native_pdf_text",
    "segment_not_located",
    "surplus_occurrence",
    "absent_from_pdf",
)
PDF_CAUSES = (
    "page_not_in_reference",
    "folio_candidate",
    "furniture_candidate",
    "figure_text_candidate",
    "surplus_occurrence",
    "absent_from_reference",
)


@dataclass(frozen=True)
class AlignerConfig:
    jump_penalty: float = 0.6
    stay_penalty: float = 0.05
    skip_penalty: float = 0.1
    candidate_pages: int = 12
    candidate_max_df: int = 50
    saturation_tokens: int = 100  # segment size at which placement evidence is fully weighted
    placement_floor: float = 0.3  # containment below which a segment counts as not located
    placement_full: float = 0.8  # containment giving full placement confidence
    chunk_tokens: int = 300  # pseudo-segment size for references without page markers
    min_move_run: int = 3
    relocation_ngram: int = 4
    furniture_min_pages: int = 3
    near_ratio: float = 0.8
    near_min_length: int = 4
    fuzzy_max_cells: int = 250_000


@dataclass
class Segment:
    number: int
    label: str | None
    first: int
    count: int
    page: int | None = None  # page index (0-based into pages) or None when empty
    containment: float = 0.0
    located: bool = False
    window: list[int] = field(default_factory=list)


@dataclass
class AlignmentResult:
    version: str
    config: dict
    xml_sha256: str
    dialect: str
    repairs: list[dict]
    pages: list[int]  # physical page numbers, in index order
    page_digests: list[str]
    segments: list[dict]
    xml_page: list[int]  # page index of the primary link, -1 when unaligned
    xml_ordinal: list[int]
    xml_method: list[str]
    xml_confidence: list[float]
    xml_cause: list[str]
    extra_links: list[list[int]]  # [xml, page index, ordinal] for joins/splits
    refused_links: int  # links refused because their PDF token was already claimed
    pdf_xml: list[list[int]]  # per page index, per ordinal: xml token or -1
    pdf_cause: list[list[str]]

    def to_payload(self) -> dict:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: Mapping) -> AlignmentResult:
        return cls(**payload)


class _State:
    """Mutable link tables shared by all stages."""

    def __init__(self, doc: ReferenceDocument, pages: Sequence[PdfPage]):
        n = len(doc.tokens)
        self.x_page = [-1] * n
        self.x_ord = [-1] * n
        self.x_method = [""] * n
        self.x_conf = [0.0] * n
        self.extra: list[list[int]] = []
        self.p_xml = [[-1] * len(page.tokens) for page in pages]
        self.refused = 0

    def x_free(self, i: int) -> bool:
        return self.x_page[i] < 0

    def p_free(self, page: int, ordinal: int) -> bool:
        return self.p_xml[page][ordinal] < 0

    def link(
        self, xs: Sequence[int], ys: Sequence[tuple[int, int]], method: str, factor: float
    ) -> bool:
        """Record one link; a PDF token already claimed by another link is never re-claimed."""
        if any(not self.p_free(page, ordinal) for page, ordinal in ys):
            self.refused += 1
            return False
        confidence = round(METHOD_CONFIDENCE[method] * factor, 4)
        for x in xs:
            if self.x_page[x] < 0:
                self.x_page[x], self.x_ord[x] = ys[0]
                self.x_method[x] = method
                self.x_conf[x] = confidence
            else:
                self.extra.append([x, *ys[0]])
            for page, ordinal in ys[1:]:
                self.extra.append([x, page, ordinal])
        for page, ordinal in ys:
            self.p_xml[page][ordinal] = xs[0]
        return True


# ---------------------------------------------------------------- stage A: placement


def _segments(doc: ReferenceDocument, config: AlignerConfig) -> list[Segment]:
    if doc.markers:
        starts = [0, *(marker.token_index for marker in doc.markers)]
        labels = [None, *(marker.label for marker in doc.markers)]
        ends = [*starts[1:], len(doc.tokens)]
        return [
            Segment(number, labels[number], start, end - start)
            for number, (start, end) in enumerate(zip(starts, ends, strict=True))
        ]
    size = config.chunk_tokens
    return [
        Segment(number, None, start, min(size, len(doc.tokens) - start))
        for number, start in enumerate(range(0, max(len(doc.tokens), 1), size))
    ]


def _containment(segment: Counter, page: Counter) -> float:
    total = segment.total()
    return (segment & page).total() / total if total else 0.0


def place_segments(
    doc: ReferenceDocument, pages: Sequence[PdfPage], config: AlignerConfig
) -> list[Segment]:
    segments = _segments(doc, config)
    counters = [Counter(token.value for token in page.tokens) for page in pages]
    df: Counter = Counter()
    postings: dict[str, list[int]] = defaultdict(list)
    for index, counter in enumerate(counters):
        df.update(counter.keys())
        for value in counter:
            postings[value].append(index)
    size = len(pages)
    seg_counters = [
        Counter(t.value for t in doc.tokens[s.first : s.first + s.count]) for s in segments
    ]
    emissions: list[dict[int, float]] = []
    for counter in seg_counters:
        votes: Counter = Counter()
        for value in counter:
            if 0 < df[value] <= config.candidate_max_df:
                weight = 1 / math.log2(1 + df[value])
                for index in postings[value]:
                    votes[index] += weight
        weight = min(1.0, counter.total() / config.saturation_tokens)
        emissions.append(
            {
                index: _containment(counter, counters[index]) * weight
                for index, _ in sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[
                    : config.candidate_pages
                ]
            }
        )
    if not size:
        return segments
    negative = -1e9
    score = np.zeros(size)
    for index, value in emissions[0].items():
        score[index] = value
    back = np.zeros((len(segments), size), dtype=np.int64)
    states = np.arange(size)
    for number in range(1, len(segments)):
        step = np.concatenate(([negative], score[:-1]))
        stay = score - config.stay_penalty
        skip = np.concatenate(([negative, negative], score[:-2]))[:size] - config.skip_penalty
        best_from = int(np.argmax(score))
        jump = np.full(size, score[best_from] - config.jump_penalty)
        options = np.vstack([step, stay, skip, jump])
        choice = np.argmax(options, axis=0)  # ties prefer step, then stay, skip, jump
        sources = np.select(
            [choice == 0, choice == 1, choice == 2], [states - 1, states, states - 2], best_from
        )
        back[number] = sources
        score = options[choice, states].copy()
        for index, value in emissions[number].items():
            score[index] += value
    path = [int(np.argmax(score))]
    for number in range(len(segments) - 1, 0, -1):
        path.append(int(back[number][path[-1]]))
    path.reverse()
    for segment, counter, page in zip(segments, seg_counters, path, strict=True):
        segment.page = page
        segment.containment = round(_containment(counter, counters[page]), 4)
        segment.located = counter.total() > 0 and segment.containment >= config.placement_floor
    _windows(segments, size)
    return segments


def _windows(segments: list[Segment], size: int) -> None:
    """Own page plus following unassigned pages up to the next segment's page."""
    assigned = {s.page for s in segments if s.located}
    for number, segment in enumerate(segments):
        if segment.page is None:
            continue
        window = [segment.page]
        upper = next(
            (s.page for s in segments[number + 1 :] if s.located and s.page is not None), size
        )
        if upper > segment.page:
            window += [p for p in range(segment.page + 1, upper) if p not in assigned]
        segment.window = window


# ---------------------------------------------------------------- stage B: token alignment


def _unique_anchors(x: Sequence[str], y: Sequence[str], used_x, used_y, n: int):
    def grams(values, used):
        found: dict[tuple, list[int]] = defaultdict(list)
        for i in range(len(values) - n + 1):
            if not any(used[i + k] for k in range(n)):
                found[tuple(values[i : i + n])].append(i)
        return found

    gx, gy = grams(x, used_x), grams(y, used_y)
    pairs = []
    for gram, positions in gx.items():
        if len(positions) == 1 and len(gy.get(gram, ())) == 1:
            pairs.append((positions[0], gy[gram][0]))
    return sorted(pairs)


def _runs(pairs: dict[int, int]) -> list[tuple[int, int, int]]:
    """(x start, y start, length) for maximal diagonal runs of matched pairs."""
    runs = []
    for i in sorted(pairs):
        j = pairs[i]
        if runs and runs[-1][0] + runs[-1][2] == i and runs[-1][1] + runs[-1][2] == j:
            runs[-1] = (runs[-1][0], runs[-1][1], runs[-1][2] + 1)
        else:
            runs.append((i, j, 1))
    return runs


def _chain(runs: list[tuple[int, int, int]]) -> set[int]:
    """Indices of the heaviest chain of runs increasing in both sequences."""
    best = [0] * len(runs)
    previous = [-1] * len(runs)
    for k, (i, j, length) in enumerate(runs):
        best[k] = length
        for m in range(k):
            pi, pj, pl = runs[m]
            if pi + pl <= i and pj + pl <= j and best[m] + length > best[k]:
                best[k], previous[k] = best[m] + length, m
    chain: set[int] = set()
    k = max(range(len(runs)), key=lambda r: (best[r], -r), default=-1)
    while k >= 0:
        chain.add(k)
        k = previous[k]
    return chain


def _gap_matches(xs, ys, x, y, side: str, max_cells: int) -> list[tuple[int, int]]:
    """Exact LCS inside one gap; among equal-size solutions, prefer anchored positions.

    ``side`` says which ends of the gap are bounded by chain runs: "right" (leading gap),
    "left" (trailing gap), "both" or "none". A duplicated value is matched to the occurrence
    whose distance from the bounding anchor agrees with the reference token's, so a running head
    that repeats a heading on the same page does not take the heading's place.
    """
    nx, ny = len(xs), len(ys)
    if nx * ny > max_cells:
        matcher = SequenceMatcher(None, [x[a] for a in xs], [y[b] for b in ys], autojunk=False)
        return [
            (xs[block.a + d], ys[block.b + d])
            for block in matcher.get_matching_blocks()
            for d in range(block.size)
        ]

    def cost(a, b):
        if side == "right":
            return abs((nx - a) - (ny - b))
        if side == "left":
            return abs(a - b)
        return min(abs(a - b), abs((nx - a) - (ny - b)))

    big = float(nx + ny + 1) * (nx + ny + 1)
    score = np.zeros((nx + 1, ny + 1))
    for a in range(nx - 1, -1, -1):
        for b in range(ny - 1, -1, -1):
            best = max(score[a + 1, b], score[a, b + 1])
            if x[xs[a]] == y[ys[b]]:
                best = max(best, big - cost(a, b) + score[a + 1, b + 1])
            score[a, b] = best
    found, a, b = [], 0, 0
    while a < nx and b < ny:
        if x[xs[a]] == y[ys[b]] and score[a, b] == big - cost(a, b) + score[a + 1, b + 1]:
            found.append((xs[a], ys[b]))
            a, b = a + 1, b + 1
        elif score[a, b] == score[a + 1, b]:
            a += 1
        else:
            b += 1
    return found


def _fuzzy(xs, ys, x, y, ymeta, config: AlignerConfig):
    """Ordered joins/splits/case/near variants over unmatched positions (DP, max score)."""
    if not xs or not ys or len(xs) * len(ys) > config.fuzzy_max_cells:
        return []
    nx, ny = len(xs), len(ys)
    score = np.zeros((nx + 1, ny + 1))
    move = {}
    for a in range(nx - 1, -1, -1):
        for b in range(ny - 1, -1, -1):
            best, how = score[a + 1, b], ("skip_x",)
            if score[a, b + 1] > best:
                best, how = score[a, b + 1], ("skip_y",)
            xv, yv = x[xs[a]], y[ys[b]]
            for width in (2, 3):  # one reference token over several PDF tokens
                if b + width <= ny and xv == "".join(y[ys[b + k]] for k in range(width)):
                    first = ymeta[ys[b]]
                    method = (
                        "join_hyphen"
                        if first.hyphen_break
                        else "join_soft_hyphen"
                        if first.soft_hyphen
                        else "join_split"
                    )
                    candidate = 0.9 + score[a + 1, b + width]
                    if candidate > best:
                        best, how = candidate, (method, 1, width)
            for width in (2, 3):  # several reference tokens over one PDF token
                if a + width <= nx and yv == "".join(x[xs[a + k]] for k in range(width)):
                    candidate = 0.85 + score[a + width, b + 1]
                    if candidate > best:
                        best, how = candidate, ("split", width, 1)
            if xv != yv and xv.casefold() == yv.casefold():
                candidate = 0.8 + score[a + 1, b + 1]
                if candidate > best:
                    best, how = candidate, ("case", 1, 1)
            elif min(len(xv), len(yv)) >= config.near_min_length:
                ratio = SequenceMatcher(None, xv, yv, autojunk=False).ratio()
                if ratio >= config.near_ratio and 0.6 * ratio + score[a + 1, b + 1] > best:
                    best, how = 0.6 * ratio + score[a + 1, b + 1], ("variant", 1, 1)
            score[a, b], move[a, b] = best, how
    found, a, b = [], 0, 0
    while a < nx and b < ny:
        how = move[a, b]
        if how[0] == "skip_x":
            a += 1
        elif how[0] == "skip_y":
            b += 1
        else:
            method, wx, wy = how
            found.append((method, [xs[a + k] for k in range(wx)], [ys[b + k] for k in range(wy)]))
            a, b = a + wx, b + wy
    return found


def align_window(
    state: _State,
    x_index: Sequence[int],
    y_index: Sequence[tuple[int, int]],
    doc: ReferenceDocument,
    pages: Sequence[PdfPage],
    config: AlignerConfig,
    factor: float,
) -> None:
    """Align free reference tokens to free PDF tokens of one window, in place."""
    x_index = [i for i in x_index if state.x_free(i)]
    y_index = [p for p in y_index if state.p_free(*p)]
    if not x_index or not y_index:
        return
    x = [doc.tokens[i].value for i in x_index]
    y = [pages[p].tokens[o].value for p, o in y_index]
    ymeta = [pages[p].tokens[o] for p, o in y_index]
    used_x, used_y = [False] * len(x), [False] * len(y)
    pairs: dict[int, int] = {}
    methods: dict[int, str] = {}

    def take(i, j, method):
        pairs[i], methods[i] = j, method
        used_x[i] = used_y[j] = True

    for n in (1, 2, 3):
        for i, j in _unique_anchors(x, y, used_x, used_y, n):
            # Overlapping n-grams may already have claimed a position in this pass.
            if any(used_x[i + k] or used_y[j + k] for k in range(n)):
                continue
            for k in range(n):
                take(i + k, j + k, "anchor")
    for i, j in sorted(dict(pairs).items()):  # extend every anchor run both ways
        for step in (1, -1):
            a, b = i + step, j + step
            while 0 <= a < len(x) and 0 <= b < len(y) and not used_x[a] and not used_y[b]:
                if x[a] != y[b]:
                    break
                take(a, b, "extension")
                a, b = a + step, b + step
    runs = _runs(pairs)
    chain = _chain(runs)
    for k, (i, j, length) in enumerate(runs):
        if k in chain:
            continue
        for d in range(length):
            if length >= config.min_move_run:
                methods[i + d] = "moved"
            else:
                used_x[i + d] = used_y[j + d] = False
                del pairs[i + d]
                del methods[i + d]
    ordered = sorted(runs[k] for k in chain)
    bounds = [(-1, -1, 1), *ordered, (len(x), len(y), 0)]
    for number, ((i0, j0, l0), (i1, j1, _)) in enumerate(zip(bounds, bounds[1:], strict=False)):
        xs = [a for a in range(i0 + l0, i1) if not used_x[a]]
        ys = [b for b in range(j0 + l0, j1) if not used_y[b]] if j1 >= j0 + l0 else []
        if not xs or not ys:
            continue
        left, right = number > 0, number < len(bounds) - 2
        side = {(False, True): "right", (True, False): "left", (True, True): "both"}.get(
            (left, right), "none"
        )
        for a, b in _gap_matches(xs, ys, x, y, side, config.fuzzy_max_cells):
            take(a, b, "gap")
        xs = [a for a in xs if not used_x[a]]
        ys = [b for b in ys if not used_y[b]]
        for method, fx, fy in _fuzzy(xs, ys, x, y, ymeta, config):
            state.link([x_index[a] for a in fx], [y_index[b] for b in fy], method, factor)
            for a in fx:
                used_x[a] = True
            for b in fy:
                used_y[b] = True
    for i, j in sorted(pairs.items()):
        state.link([x_index[i]], [y_index[j]], methods[i], factor)
    leftover_pass(state, x_index, y_index, doc, pages, "leftover", factor)


def leftover_pass(state, x_index, y_index, doc, pages, method, factor, min_block=2):
    """Ordered matching of what is still free: blocks of 2+ tokens, or values unique on both."""
    xs = [i for i in x_index if state.x_free(i)]
    ys = [p for p in y_index if state.p_free(*p)]
    if not xs or not ys:
        return
    xv = [doc.tokens[i].value for i in xs]
    yv = [pages[p].tokens[o].value for p, o in ys]
    cx, cy = Counter(xv), Counter(yv)
    matcher = SequenceMatcher(None, xv, yv, autojunk=False)
    for block in matcher.get_matching_blocks():
        if block.size == 0:
            continue
        if block.size < min_block and not (cx[xv[block.a]] == 1 and cy[yv[block.b]] == 1):
            continue
        for d in range(block.size):
            state.link([xs[block.a + d]], [ys[block.b + d]], method, factor)


# ---------------------------------------------------------------- stage D: relocation


def relocate(state: _State, doc: ReferenceDocument, pages: Sequence[PdfPage], n: int) -> None:
    """Long leftover reference runs matched to a unique free PDF n-gram anywhere in the book."""
    grams: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
    for page_index, page in enumerate(pages):
        free = [o for o in range(len(page.tokens)) if state.p_free(page_index, o)]
        for k in range(len(free) - n + 1):
            window = free[k : k + n]
            if window[-1] - window[0] == n - 1:
                grams[tuple(page.tokens[o].value for o in window)].append((page_index, window[0]))
    x_grams: dict[tuple, list[int]] = defaultdict(list)
    tokens = doc.tokens
    for i in range(len(tokens) - n + 1):
        if all(state.x_free(i + k) for k in range(n)):
            x_grams[tuple(tokens[i + k].value for k in range(n))].append(i)
    for gram, starts in sorted(x_grams.items(), key=lambda kv: kv[1][0]):
        targets = grams.get(gram, [])
        if len(starts) != 1 or len(targets) != 1:
            continue
        i, (page_index, ordinal) = starts[0], targets[0]
        length = 0
        while (
            i + length < len(tokens)
            and ordinal + length < len(pages[page_index].tokens)
            and state.x_free(i + length)
            and state.p_free(page_index, ordinal + length)
            and tokens[i + length].value == pages[page_index].tokens[ordinal + length].value
        ):
            length += 1
        if length >= n:
            for d in range(length):
                state.link([i + d], [(page_index, ordinal + d)], "relocated", 1.0)


# ---------------------------------------------------------------- causes


def _furniture_lines(pages: Sequence[PdfPage], min_pages: int) -> set[tuple[int, int]]:
    seen: dict[str, set[int]] = defaultdict(set)
    for index, page in enumerate(pages):
        for line in page.lines:
            seen[line.key].add(index)
    return {
        (index, line.ordinal)
        for index, page in enumerate(pages)
        for line in page.lines
        if len(seen[line.key]) >= min_pages
    }


def classify(
    state: _State,
    doc: ReferenceDocument,
    pages: Sequence[PdfPage],
    segments: Sequence[Segment],
    config: AlignerConfig,
    figure_regions: Mapping[int, Sequence[BBox]] | None,
) -> tuple[list[str], list[list[str]]]:
    elements = doc.elements
    windowed: dict[int, list[Segment]] = defaultdict(list)
    for segment in segments:
        for page in segment.window:
            windowed[page].append(segment)
    segment_of = [0] * len(doc.tokens)
    for segment in segments:
        for i in range(segment.first, segment.first + segment.count):
            segment_of[i] = segment.number
    x_cause = [""] * len(doc.tokens)
    values_by_segment: dict[int, set[str]] = {}
    for i, token in enumerate(doc.tokens):
        if not state.x_free(i):
            continue
        segment = segments[segment_of[i]]
        if segment.number not in values_by_segment:
            values_by_segment[segment.number] = {
                t.value for p in segment.window for t in pages[p].tokens
            }
        window_values = values_by_segment[segment.number]
        if doc.dialect.zone_of(token.element, elements) == "metadata":
            x_cause[i] = "reference_metadata"
        elif describes_image(doc, i):
            x_cause[i] = "image_description"
        elif segment.window and all(not pages[p].tokens for p in segment.window):
            x_cause[i] = "no_native_pdf_text"
        elif not segment.located:
            x_cause[i] = "segment_not_located"
        elif token.value in window_values:
            x_cause[i] = "surplus_occurrence"
        else:
            x_cause[i] = "absent_from_pdf"
    furniture = _furniture_lines(pages, config.furniture_min_pages)
    labels: dict[int, set[str]] = defaultdict(set)
    for segment in segments:
        if segment.label and segment.page is not None:
            labels[segment.page].add(segment.label)
    p_cause: list[list[str]] = []
    for index, page in enumerate(pages):
        causes = [""] * len(page.tokens)
        covered = index in windowed or any(x >= 0 for x in state.p_xml[index])
        reference_values = {
            doc.tokens[i].value
            for segment in windowed.get(index, ())
            for i in range(segment.first, segment.first + segment.count)
        }
        regions = (figure_regions or {}).get(page.page, ())
        for token in page.tokens:
            if not state.p_free(index, token.ordinal):
                continue
            line = page.lines[token.line]
            if not covered:
                cause = "page_not_in_reference"
            elif line.token_count == 1 and (
                token.value in labels.get(index, ()) or _folio_like(token.value)
            ):
                cause = "folio_candidate"
            elif any(_inside(line.center, region) for region in regions):
                cause = "figure_text_candidate"
            elif (index, line.ordinal) in furniture:
                cause = "furniture_candidate"
            elif token.value in reference_values:
                cause = "surplus_occurrence"
            else:
                cause = "absent_from_reference"
            causes[token.ordinal] = cause
        p_cause.append(causes)
    return x_cause, p_cause


def describes_image(doc: ReferenceDocument, i: int) -> bool:
    kind = doc.dialect.unit_kind
    element = doc.tokens[i].element
    return kind(doc.elements[doc.units[i]].name) == "image_description" or any(
        kind(doc.elements[a].name) == "image_description" for a in doc.ancestors(element)
    )


def figure_label_pass(state, doc, pages, segments, factor) -> None:
    """Image descriptions list figure labels in no reliable order: match unique values only.

    A value is linked only when it is the single free description token of its value in the
    segment and the single free PDF token of that value in the window and its neighbours.
    Repeated labels stay unaligned rather than being paired by guesswork.
    """
    for segment in segments:
        if segment.page is None or not segment.count:
            continue
        xs = [
            i
            for i in range(segment.first, segment.first + segment.count)
            if state.x_free(i) and describes_image(doc, i)
        ]
        if not xs:
            continue
        lo, hi = max(segment.window[0] - 1, 0), min(segment.window[-1] + 1, len(pages) - 1)
        ys = [
            (p, o)
            for p in range(lo, hi + 1)
            for o in range(len(pages[p].tokens))
            if state.p_free(p, o)
        ]
        x_values = Counter(doc.tokens[i].value for i in xs)
        y_positions: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for p, o in ys:
            y_positions[pages[p].tokens[o].value].append((p, o))
        for i in xs:
            value = doc.tokens[i].value
            if x_values[value] == 1 and len(y_positions.get(value, ())) == 1:
                state.link([i], y_positions[value], "figure_label", factor(segment))


def context_pass(state, doc, pages, config: AlignerConfig, max_x: int = 4, max_y: int = 6):
    """Short unaligned reference runs sandwiched between aligned neighbours on one page.

    The neighbours fix the PDF interval, so exact matches, joins/splits (glued or broken
    words), case and near variants are resolved with ordered context, never by value alone.
    """
    n = len(doc.tokens)
    i = 0
    while i < n:
        if not state.x_free(i):
            i += 1
            continue
        end = i
        while end < n and state.x_free(end):
            end += 1
        if 0 < i and end < n and end - i <= max_x and doc.units[i - 1] == doc.units[end]:
            p0, o0 = state.x_page[i - 1], state.x_ord[i - 1]
            p1, o1 = state.x_page[end], state.x_ord[end]
            span = range(o0 + 1, o1)
            if (
                p0 == p1
                and 0 < len(span) <= max_y
                and all(state.p_free(p0, o) for o in span)
                and state.x_method[i - 1] not in {"relocated", "figure_label"}
            ):
                x = [doc.tokens[k].value for k in range(i, end)]
                y = [pages[p0].tokens[o].value for o in span]
                meta = [pages[p0].tokens[o] for o in span]
                xs, ys = list(range(len(x))), list(range(len(y)))
                for a, b in _gap_matches(xs, ys, x, y, "both", config.fuzzy_max_cells):
                    state.link([i + a], [(p0, span[b])], "context", 1.0)
                xs = [a for a in xs if state.x_free(i + a)]
                ys = [b for b in ys if state.p_free(p0, span[b])]
                for method, fx, fy in _fuzzy(xs, ys, x, y, meta, config):
                    state.link([i + a for a in fx], [(p0, span[b]) for b in fy], method, 1.0)
        i = end


def _folio_like(value: str) -> bool:
    return value.isdigit() or (value.lower() == value and set(value) <= set("ivxlcdm"))


def _inside(point: tuple[float, float], box: BBox) -> bool:
    return box.x0 <= point[0] <= box.x1 and box.y0 <= point[1] <= box.y1


# ---------------------------------------------------------------- entry point


def align(
    doc: ReferenceDocument,
    pages: Sequence[PdfPage],
    config: AlignerConfig | None = None,
    figure_regions: Mapping[int, Sequence[BBox]] | None = None,
) -> AlignmentResult:
    config = config or AlignerConfig()
    state = _State(doc, pages)
    segments = place_segments(doc, pages, config)

    def factor(segment: Segment) -> float:
        return min(1.0, segment.containment / config.placement_full)

    # Stage B: consecutive segments sharing a page are aligned together.
    groups: list[list[Segment]] = []
    for segment in segments:
        if segment.page is None or not segment.count:
            continue
        if groups and groups[-1][-1].page == segment.page and groups[-1][-1].window:
            groups[-1].append(segment)
        else:
            groups.append([segment])
    for group in groups:
        window = list(dict.fromkeys(p for s in group for p in s.window))
        xs = [i for s in group for i in range(s.first, s.first + s.count)]
        ys = [(p, o) for p in window for o in range(len(pages[p].tokens))]
        align_window(state, xs, ys, doc, pages, config, min(factor(s) for s in group))
    # Stage C: spill to neighbouring pages.
    for segment in segments:
        if segment.page is None or not segment.count:
            continue
        near = [p for p in (segment.window[0] - 1, segment.window[-1] + 1) if 0 <= p < len(pages)]
        xs = range(segment.first, segment.first + segment.count)
        ys = [(p, o) for p in near for o in range(len(pages[p].tokens))]
        leftover_pass(state, xs, ys, doc, pages, "spill", factor(segment))
    figure_label_pass(state, doc, pages, segments, factor)
    # Stage D: unique long runs anywhere, then short runs fixed by aligned neighbours.
    relocate(state, doc, pages, config.relocation_ngram)
    context_pass(state, doc, pages, config)
    x_cause, p_cause = classify(state, doc, pages, segments, config, figure_regions)
    return AlignmentResult(
        version=ALIGNMENT_VERSION,
        config=asdict(config),
        xml_sha256=doc.sha256,
        dialect=doc.dialect.name,
        repairs=[asdict(repair) for repair in doc.repairs],
        pages=[page.page for page in pages],
        page_digests=[page.digest for page in pages],
        segments=[
            {
                "segment": s.number,
                "label": s.label,
                "first": s.first,
                "count": s.count,
                "page": pages[s.page].page if s.page is not None and pages else None,
                "containment": s.containment,
                "located": s.located,
                "window": [pages[p].page for p in s.window],
                "aligned": sum(1 for i in range(s.first, s.first + s.count) if not state.x_free(i)),
            }
            for s in segments
        ],
        xml_page=state.x_page,
        xml_ordinal=state.x_ord,
        xml_method=state.x_method,
        xml_confidence=state.x_conf,
        xml_cause=x_cause,
        extra_links=state.extra,
        refused_links=state.refused,
        pdf_xml=state.p_xml,
        pdf_cause=p_cause,
    )
