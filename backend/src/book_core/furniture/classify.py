"""Whole-book furniture decisions over per-line evidence (``furniture.features``).

Classes: running_head, running_foot, folio, production_mark, repeated_box and content. No
class is decided by one cue. Rules (no page numbers, coordinates, fonts, scripts or books):

- production_mark: text whose centre lies outside the content frame (the TrimBox slug area);
  inside the frame, only tiny repeated edge text with file-name or date/time shapes.
- folio: a label-like edge line chosen by the whole-book sequence (``furniture.sequence``);
  its candidates are re-weighted by the style that most printed folios share, then refitted.
  Numbers in tables, figures or lists are folios only when they fit that sequence and slot.
- running_head / running_foot: a slot, meaning lines that share an edge, a style and a narrow
  edge distance on many pages. A slot qualifies on joint evidence: recurrence with high local
  coverage (all pages, or one parity), the line being the outermost text with whitespace
  inward, text no larger than about the body size (or larger, when the slot alternates sides
  with page parity or repeats one text), and short lines. Its text may repeat or
  vary (dictionary guide words). Lines inside figures or tables join only an established slot.
- title in a running-head slot: a slot line whose (digit-masked) text is printed on one page only,
  while the slot's other pages repeat their texts (at least ``title_min_recurring_share`` of the
  slot's lines share a text with another line), is the title of the section that opens on that
  page, not a running head: books print the full title on the opening page and a short form
  on the pages after it. It stays content (a heading follows from its style and place, never
  from this stage). A slot whose lines are nearly all different (dictionary guide words) is
  left alone.
- title that opens a run (second rule): the first page of a run of at least ``title_run_pages``
  pages that carry the same slot text (consecutive pages, or every second page when the slot
  alternates sides with page parity, so odd and even pages are never mixed), when the page before
  carries another text, and the page looks like where a section starts: a line of about the
  head's size directly under it (a title in more than one line), or far more white space under
  the head than on the run's later pages (a picture or a large block opens the page). Anything
  else stays a running head.
- Neither title rule applies when the same text (or a line inside it) is set larger than the
  head on a page within ``title_heading_span`` pages: that is the section's real heading, and the
  head is its running head, not its title.
- repeated_box: constant (digit-masked) long text repeated on several pages inside a drawn
  box or frame (native drawings). It stays content, tagged; a client profile may drop it
  later, never this stage. Repeated text without drawn box geometry stays plain content.
- content: everything else. Low-confidence furniture stays content and is flagged.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from statistics import median

import regex

from book_core.furniture.labels import label_candidates, parse_label
from book_core.furniture.models import REVIEW_BELOW
from book_core.furniture.sequence import Candidate, SequenceConfig, page_labels


@dataclass(frozen=True)
class FurnitureConfig:
    edge_fraction: float = 0.12  # running heads/feet and folios lie this close to an edge
    slot_depth_tolerance: float = 0.012  # of the frame extent
    min_pages: int = 3
    min_local_coverage: float = 0.4
    segment_gap: int = 4  # pages; a slot's local range is split at longer absences
    min_inward_gap: float = 0.75  # font sizes of whitespace between furniture and content
    max_size_ratio: float = 1.25  # of the body size
    max_tokens: int = 12  # longer repeated text is a designed box, not a running head
    box_min_tokens: int = 13
    production_size_ratio: float = 0.75
    folio_max_rank: int = 2  # text lines between a folio and its edge
    title_min_slot_pages: int = 6  # a running-head slot needs this many lines to show a title in it
    title_min_recurring_share: float = 0.8  # of the slot's lines that share a text with another
    title_run_pages: int = 4  # a run opened by a title: this page plus at least three more
    title_display_ratio: float = 0.9  # a line this large (of the head) right under it: a title line
    title_gap_factor: float = 4.0  # the white space under the head, against the run's later pages
    title_gap_min: float = 4.5  # ... and at least this many font sizes
    title_heading_ratio: float = 1.3  # the same text set this much larger nearby is a real heading
    title_heading_span: int = 2  # ... on a page within this many pages

    def __post_init__(self):
        if not 0 < self.edge_fraction < 0.5 or self.min_pages < 2:
            raise ValueError("Invalid furniture configuration")


# Step 7 streams whose text belongs to an object: such lines never found a slot.
NOT_FURNITURE_STREAMS = frozenset({"figure", "table", "credit", "card"})
_FILE = regex.compile(r"\S\.[\p{L}]{2,4}\b|[\p{L}\p{N}]_[\p{L}\p{N}]")
_DATE = regex.compile(r"\p{N}{1,4}\s*[/:.-]\s*\p{N}{1,2}\s*[/:.-]\s*\p{N}{1,4}|\p{N}{1,2}:\p{N}{2}")


FOLIO_SIZE_SPREAD = 1.8  # a folio's type size vs the book's printed folios of its series


def _group_id(*parts):
    return "furn-" + hashlib.sha256("/".join(map(str, parts)).encode()).hexdigest()[:16]


def body_style(features):
    weights = Counter()
    for rows in features.values():
        for row in rows:
            if row.stream == "main" and not row.blank and row.inside_content:
                weights[row.style] += len(row.text.strip())
    return weights.most_common(1)[0][0] if weights else None


def _coverage(pages, all_pages, gap):
    """Local coverage: present pages over the pages within ``gap`` of any present page.

    A run of pages scores near one and a lone page about 1 / (2 * gap + 1). The parity
    variant measures pages of the dominant parity against exposed pages of that parity, for
    heads printed on odd or even pages only.
    """
    present = set(pages)
    known = set(all_pages)
    exposed = {q for p in present for q in range(p - gap, p + gap + 1) if q in known}
    plain = len(present) / len(exposed) if exposed else 0.0
    parity_count = Counter(p % 2 for p in present)
    parity, count = parity_count.most_common(1)[0] if present else (0, 0)
    dominant = count / max(len(present), 1)
    same = [q for q in exposed if q % 2 == parity]
    by_parity = count / len(same) if same else 0.0
    return plain, (by_parity if dominant >= 0.9 else plain), dominant


def _alternation(rows):
    """Share of slot lines whose inline side follows one parity rule (verso/recto)."""
    sided = [(r.page % 2, r.side) for r in rows if r.side != "centre"]
    if len(sided) < 2:
        return None
    best = 0
    for even_side in ("start", "end"):
        odd_side = "end" if even_side == "start" else "start"
        agree = sum(side == (even_side if parity == 0 else odd_side) for parity, side in sided)
        best = max(best, agree)
    parities = {parity for parity, _ in sided}
    return best / len(sided) if len(parities) == 2 else None


class Classifier:
    def __init__(self, features, metadata=None, config=None, sequence=None, box_lines=None):
        self.features = features  # {page: [LineFeatures]}
        # box_lines(page, rows) -> ids of rows inside a drawn box (``furniture.boxes``)
        self.box_lines = box_lines
        self._box_cache = {}
        self.pages = sorted(features)
        self.metadata = metadata or {}
        self.config = config or FurnitureConfig()
        self.sequence_config = sequence or SequenceConfig()
        self.body = body_style(features)
        self.body_size = self.body[1] if self.body else None
        self.roles = {}  # (page, line_id) -> dict
        self.folio_lines = defaultdict(list)
        self.folio_edges = defaultdict(list)
        self.groups = []

    # ------------------------------------------------------------------ helpers
    def _rows(self):
        for page in self.pages:
            yield from self.features[page]

    def _size_ratio(self, row):
        return row.font_size / self.body_size if self.body_size else 1.0

    def _edge_text(self, row):
        return (
            row.inside_content
            and not row.blank
            and row.depth <= self.config.edge_fraction
            and row.visible
        )

    def _rank(self, row):
        """Text lines between a line and its edge, not counting folios at that edge."""
        folios = self.folio_edges.get((row.page, row.edge), [])
        return max(0, row.outer_rank - sum(_beyond(row, f) for f in folios))

    def _set(self, row, role, confidence, reasons, group=None, evidence=None, review=None):
        self.roles[(row.page, row.line_id)] = {
            "role": role,
            "confidence": round(confidence, 4),
            "reasons": reasons,
            "group_id": group,
            "evidence": evidence or {},
            "review_required": confidence < REVIEW_BELOW if review is None else review,
        }

    # ------------------------------------------------------------------ stages
    def production_marks(self):
        for row in self._rows():
            if not row.inside_content:
                self._set(
                    row,
                    "production_mark",
                    0.95,
                    ["centre outside the content frame (TrimBox slug area); not printed"],
                    evidence={"outside_trim": True},
                )
        # Inside the frame: tiny edge text with file/date shapes repeated on several pages.
        shapes = defaultdict(list)
        for row in self._rows():
            if (
                self._edge_text(row)
                and (row.page, row.line_id) not in self.roles
                and row.depth <= self.config.edge_fraction / 3
                and self._size_ratio(row) <= self.config.production_size_ratio
                and (_FILE.search(row.text) or _DATE.search(row.text))
            ):
                shapes[(row.edge, row.style)].append(row)
        for key, rows in shapes.items():
            pages = sorted({r.page for r in rows})
            if len(pages) < self.config.min_pages:
                continue
            group = _group_id("production", *key)
            self.groups.append(
                self._group(
                    group,
                    "production_mark",
                    key[0],
                    rows,
                    0.75,
                    ["tiny repeated edge text with file/date shapes"],
                )
            )
            for row in rows:
                self._set(
                    row,
                    "production_mark",
                    0.75,
                    [
                        "tiny edge text with a file-name or date/time shape",
                        f"repeated on {len(pages)} pages",
                    ],
                    group,
                )

    def _folio_candidates(self, style_weight=None):
        candidates = []
        for row in self._rows():
            if not self._edge_text(row) or (row.page, row.line_id) in self.roles:
                continue
            options = [(label, False) for label in label_candidates(row.text)]
            if not options and row.edge_label is not None and row.tokens <= self.config.max_tokens:
                options = [(row.edge_label[1], True)]
            for label, embedded in options:
                candidate = self._folio_candidate(row, label, embedded, style_weight)
                if candidate.quality > 0:  # a zero weight rules the line out as a folio
                    candidates.append(candidate)
        return candidates

    def _folio_candidate(self, row, label, embedded, style_weight):
        quality = 1.0 - row.depth / self.config.edge_fraction * 0.5
        if row.outer_rank > self.config.folio_max_rank:
            quality *= 0.4
        # A number inside a figure or table is usually one of its labels; a label that is the
        # only line of its region (a page number set in a drawn badge) is not.
        if row.stream in NOT_FURNITURE_STREAMS and row.region_lines > 1:
            quality *= 0.3
        if row.region_lines > 2:
            quality *= 0.5
        if embedded:
            quality *= 0.6
        if style_weight is not None:
            quality *= style_weight(row, label)
        return Candidate(row.page, row.line_id, label, round(quality, 4), embedded)

    def folios(self):
        candidates = self._folio_candidates()
        labels, runs, _ = page_labels(self.pages, candidates, self.metadata, self.sequence_config)
        # Re-weight by the style and edge shared by most printed folios, then refit.
        row_of = {(r.page, r.line_id): r for r in self._rows()}
        printed = [(d, row_of[(d.page, d.folio.line_id)]) for d in labels if d.folio is not None]
        # Folios of one series (roman prelims, arabic body) share a style; a short series set
        # differently from a long one is judged against its own folios, not the book's.
        styles = Counter((d.kind, r.edge, r.style[:2] + r.style[3:]) for d, r in printed)
        totals = Counter(d.kind for d, _ in printed)

        sizes = defaultdict(list)
        for d, r in printed:
            sizes[d.kind].append(r.font_size)
        typical = {kind: median(found) for kind, found in sizes.items()}

        def weight(row, label):
            total = totals[label.series[0]]
            share = styles[(label.series[0], row.edge, row.style[:2] + row.style[3:])] / total \
                if total else 0.0
            value = 0.5 + 0.5 * min(1.0, share * 3)
            # A number set far larger (or smaller) than the book's printed folios of its series
            # is a display number (a chapter number on an opener), not that folio.
            size = typical.get(label.series[0])
            if size and not 1 / FOLIO_SIZE_SPREAD <= row.font_size / size <= FOLIO_SIZE_SPREAD:
                return 0.0
            return value

        candidates = self._folio_candidates(weight)
        labels, runs, comparison = page_labels(
            self.pages, candidates, self.metadata, self.sequence_config
        )
        self.labels, self.runs, self.metadata_comparison = labels, runs, comparison
        self.folio_style = {run.index: Counter() for run in runs}
        by_page = {d.page: d for d in labels}
        for decision in labels:
            if decision.folio is None:
                continue
            row = row_of[(decision.page, decision.folio.line_id)]
            self.folio_style[decision.run][(row.edge, row.style)] += 1
        self.folio_lines = defaultdict(list)
        self.folio_edges = defaultdict(list)
        for decision in labels:
            if decision.folio is None:
                continue
            row = row_of[(decision.page, decision.folio.line_id)]
            group = _group_id("folio-run", decision.run)
            evidence = {"label": decision.label, "run": decision.run, "edge": row.edge}
            if decision.folio.embedded:
                role = "running_head" if row.edge in {"top", "left"} else "running_foot"
                self._set(
                    row,
                    role,
                    decision.confidence,
                    ["furniture line carrying the printed folio", *decision.reasons],
                    group,
                    evidence,
                )
            else:
                self._set(
                    row, "folio", decision.confidence, list(decision.reasons), group, evidence
                )
            self.folio_lines[decision.page].append(row.line_id)
            self.folio_edges[(row.page, row.edge)].append(row)
            # Overprinted copies: identical text at the same place.
            for other in self.features[decision.page]:
                if (
                    other.line_id != row.line_id
                    and (other.page, other.line_id) not in self.roles
                    and other.key == row.key
                    and _same_place(other.bbox, row.bbox)
                ):
                    self._set(
                        other,
                        self.roles[(row.page, row.line_id)]["role"],
                        decision.confidence,
                        ["overprinted copy of the folio line"],
                        group,
                        evidence,
                    )
                    self.folio_lines[decision.page].append(other.line_id)
        self._metadata_folios(labels)
        self.by_page = by_page

    def _metadata_folios(self, labels):
        """Front-matter pages labelled by trusted metadata: the edge line printing exactly that
        label is the folio (Step 9 correctness rule); the marker keeps source ``metadata``."""
        for decision in labels:
            if decision.source != "metadata" or decision.label is None:
                continue
            matches = [
                row
                for row in self.features[decision.page]
                if self._edge_text(row)
                and (row.page, row.line_id) not in self.roles
                and self._rank(row) <= self.config.folio_max_rank
                and row.stream not in NOT_FURNITURE_STREAMS
                and any(label.render() == decision.label for label in label_candidates(row.text))
            ]
            if len(matches) != 1:
                continue  # none, or ambiguous: the label stays metadata-only
            row = matches[0]
            self._set(
                row,
                "folio",
                0.8,
                [
                    "front-matter edge line printing the trusted metadata label",
                    *decision.reasons,
                ],
                _group_id("folio-metadata"),
                {"label": decision.label, "edge": row.edge},
            )
            self.folio_lines[decision.page].append(row.line_id)
            self.folio_edges[(row.page, row.edge)].append(row)

    def running(self):
        config = self.config
        rows = [
            r for r in self._rows() if self._edge_text(r) and (r.page, r.line_id) not in self.roles
        ]
        by_style = defaultdict(list)
        for row in rows:
            # Colour is not part of a slot: feet change colour on dark pages.
            by_style[(row.edge, row.style[:2] + row.style[3:])].append(row)
        slots = []
        for (edge, style), members in by_style.items():
            members.sort(key=lambda r: (r.depth, r.page, r.line_id))
            while members:
                anchor = members[0].depth
                slot = [r for r in members if r.depth - anchor <= config.slot_depth_tolerance]
                members = [r for r in members if r.depth - anchor > config.slot_depth_tolerance]
                slots.append(((edge, style, round(anchor, 4)), slot))
        for key, slot in slots:
            self._judge_slot(key, slot)

    def _judge_slot(self, key, slot):
        config = self.config
        edge, style, _ = key
        outer = [
            r
            for r in slot
            if r.stream not in NOT_FURNITURE_STREAMS
            and self._rank(r) <= 1
            and (r.inward_gap is None or r.inward_gap >= config.min_inward_gap)
        ]
        pages = sorted({r.page for r in outer})
        if len(pages) < config.min_pages:
            return
        plain, coverage, _ = _coverage(pages, self.pages, config.segment_gap)
        keys = Counter(r.key for r in outer)
        constant = keys.most_common(1)[0][1] / len(outer)
        tokens = median(r.tokens for r in outer)
        size_ratio = median(self._size_ratio(r) for r in outer)
        isolated = sum(
            r.inward_gap is None or r.inward_gap >= config.min_inward_gap for r in slot
        ) / len(slot)
        outermost = sum(self._rank(r) == 0 for r in outer) / len(outer)
        alternation = _alternation(outer)
        evidence = {
            "pages": len(pages),
            "local_coverage": round(coverage, 4),
            "plain_coverage": round(plain, 4),
            "constant_text_share": round(constant, 4),
            "median_tokens": tokens,
            "size_ratio": round(size_ratio, 4),
            "isolated_share": round(isolated, 4),
            "outermost_share": round(outermost, 4),
            "side_alternation": None if alternation is None else round(alternation, 4),
        }
        reasons, score = [], 0.0
        if coverage >= config.min_local_coverage:
            score += 0.3
            reasons.append(f"recurs on {len(pages)} pages, local coverage {coverage:.0%}")
        if outermost >= 0.8:
            score += 0.2
            reasons.append("outermost text at its edge")
        if isolated >= 0.8:
            score += 0.15
            reasons.append("whitespace separates it from the content")
        if size_ratio <= config.max_size_ratio:
            score += 0.15
            reasons.append("no larger than body text")
        if alternation is not None and alternation >= 0.9:
            score += 0.15
            reasons.append("side alternates with page parity")
        elif constant >= 0.5:
            score += 0.1
            reasons.append("constant (digit-masked) text")
        if tokens <= config.max_tokens:
            score += 0.05
        blocking = []
        if coverage < config.min_local_coverage:
            blocking.append("sparse recurrence")
        # A running head may be set larger than the body (a chapter's title repeated on its
        # pages). A title prints once; the slot recurs as the outermost, isolated short line,
        # alternating sides with page parity or repeating one text.
        recurring = (
            coverage >= config.min_local_coverage
            and outermost >= 0.8
            and isolated >= 0.8
            and tokens <= config.max_tokens
            and ((alternation is not None and alternation >= 0.9) or constant >= 0.8)
        )
        if size_ratio > config.max_size_ratio and recurring:
            reasons.append("larger than body text, but recurs as the outermost isolated line")
        elif size_ratio > config.max_size_ratio:
            blocking.append("larger than body text")
        if tokens > config.max_tokens:
            blocking.append("long text")
        confidence = min(0.97, score)
        role = "running_head" if edge in {"top", "left"} else "running_foot"
        group = _group_id("slot", *key)
        if blocking:
            # Repeated constant blocks are designed content; the rest is plain content.
            if constant >= 0.5 and tokens >= config.box_min_tokens:
                return  # handled by repeated_boxes
            if score >= 0.6:
                self.groups.append(
                    self._group(
                        group,
                        "content",
                        edge,
                        outer,
                        round(score, 4),
                        ["furniture-like slot kept as content: " + ", ".join(blocking)],
                        evidence,
                    )
                )
                for row in outer:
                    self._set(
                        row,
                        "content",
                        0.55,
                        ["furniture-like slot kept as content: " + ", ".join(blocking)],
                        group,
                        evidence,
                        review=True,
                    )
            return
        if confidence < REVIEW_BELOW:
            for row in outer:
                self._set(
                    row,
                    "content",
                    1 - confidence,
                    ["weak furniture evidence; kept as content"],
                    group,
                    evidence,
                    review=True,
                )
            return
        self.groups.append(self._group(group, role, edge, outer, confidence, reasons, evidence))
        members = {(r.page, r.line_id) for r in outer}
        for row in slot:
            if (row.page, row.line_id) in members:
                self._set(row, role, confidence, reasons, group, evidence)
            elif row.stream in NOT_FURNITURE_STREAMS and row.page in pages and row.outer_rank <= 1:
                continue  # figure/table text at an established slot stays content
            elif row.outer_rank <= 1 and row.key in keys:
                self._set(
                    row,
                    role,
                    confidence * 0.8,
                    [*reasons, "same text as the slot, less isolated"],
                    group,
                    evidence,
                )

    def titles_in_slots(self):
        """Running-head slot lines that are a section's title (see the module notes): the text is
        printed once while the slot's other lines repeat texts. They become content again and
        leave the slot group; every other line of the slot keeps its role."""
        config = self.config
        for index, group in enumerate(self.groups):
            if group.role != "running_head":
                continue
            rows = [
                r
                for r in self._rows()
                if (self.roles.get((r.page, r.line_id)) or {}).get("group_id") == group.id
                and self.roles[(r.page, r.line_id)]["role"] == "running_head"
            ]
            if len(rows) < config.title_min_slot_pages:
                continue
            keys = Counter(r.key for r in rows)
            share = sum(1 for r in rows if keys[r.key] >= 2) / len(rows)
            if share < config.title_min_recurring_share:
                continue
            key_at = {r.page: r.key for r in rows}
            stride = self._slot_stride(key_at)
            titles = [
                r
                for r in rows
                if keys[r.key] == 1
                and regex.search(r"\p{L}", r.key)
                and r.stream not in NOT_FURNITURE_STREAMS
                # a title opens a new run: the same text on both sides means a stray line
                and not (
                    key_at.get(r.page - stride) is not None
                    and key_at.get(r.page - stride) == key_at.get(r.page + stride)
                )
                and not self._printed_larger_nearby(r)
            ]
            if titles:
                reasons = [
                    "running-head slot text printed on one page only while the slot's other pages "
                    "repeat a text: the title of the section that opens here; kept as content"
                ]
                for row in titles:
                    self._set(
                        row,
                        "content",
                        0.85,
                        reasons,
                        group.id,
                        {"slot_lines": len(rows), "recurring_share": round(share, 3)},
                        review=False,
                    )
                gone = {r.line_id for r in titles}
                rows = [r for r in rows if r.line_id not in gone]
                self.groups[index] = group.model_copy(
                    update={
                        "line_ids": [i for i in group.line_ids if i not in gone],
                        "pages": sorted({r.page for r in rows}),
                    }
                )
            group = self.groups[index]
            # second rule: the first page of a run that looks like where a section starts
            opens = self._run_openers(rows)
            if opens:
                for row in opens:
                    self._set(
                        row,
                        "content",
                        0.8,
                        [
                            "first page of a run of the same running-head text that looks like "
                            "where a section starts: its title, kept as content"
                        ],
                        group.id,
                        {"slot_lines": len(rows), "run_opener": True},
                        review=False,
                    )
                gone = {r.line_id for r in opens}
                self.groups[index] = group.model_copy(
                    update={
                        "line_ids": [i for i in group.line_ids if i not in gone],
                        "pages": sorted({r.page for r in rows if r.line_id not in gone}),
                    }
                )

    def _printed_larger_nearby(self, row):
        """The same text (or the line inside a longer one) is set larger than ``row`` on a page
        within the configured span: a real heading, so ``row`` is its running head."""
        config = self.config
        for page in range(row.page - config.title_heading_span, row.page + config.title_heading_span + 1):
            for other in self.features.get(page, ()):
                if (
                    other is row
                    or other.blank
                    or not other.inside_content
                    or other.font_size < config.title_heading_ratio * row.font_size
                ):
                    continue
                if (self.roles.get((page, other.line_id)) or {}).get("role") in ("running_head", "running_foot", "folio"):
                    continue
                short, long_ = sorted((row.key, other.key), key=len)
                if row.key == other.key or (len(short) >= 12 and short in long_):
                    return True
        return False

    @staticmethod
    def _slot_stride(key_at, default=1):
        """1 when the slot's text carries on from page to page, 2 when it carries on from every
        second page (the slot alternates sides with page parity), else ``default``."""
        for stride in (1, 2):
            pairs = [(p, p + stride) for p in key_at if p + stride in key_at]
            if pairs and sum(1 for p, q in pairs if key_at[p] == key_at[q]) / len(pairs) >= 0.5:
                return stride
        return default

    def _run_openers(self, rows):
        """Slot lines that open a run of the same text and look like a section start (see the
        module notes). The stride is one page, or two when the slot alternates by page parity."""
        config = self.config
        key_at = {r.page: r.key for r in rows}
        row_at = {r.page: r for r in rows}
        stride = self._slot_stride(key_at, default=None)
        if stride is None:
            return []
        found = []
        for page in sorted(key_at):
            key = key_at[page]
            before = key_at.get(page - stride)
            if before is None or before == key or not regex.search(r"\p{L}", key):
                continue
            run = [page]
            while key_at.get(run[-1] + stride) == key:
                run.append(run[-1] + stride)
            if len(run) < config.title_run_pages:
                continue
            # The row is already a member of the slot (the same text as its other pages), so a
            # head the layout step grouped with the opener's big picture (a figure stream) counts.
            row = row_at[page]
            if self._printed_larger_nearby(row) or not self._opens_a_section(
                row, [row_at[q] for q in run[1:4]]
            ):
                continue
            found.append(row)
        return found

    def _opens_a_section(self, row, later):
        """The page looks like where a section starts: a line of about the head's size right
        under the head (a title set in more than one line), or much more white space under the
        head than on the next pages of the run (a picture or a block opens the page)."""
        config = self.config
        for other in self.features[row.page]:
            if (
                other is not row
                and other.inside_content
                and not other.blank
                and other.visible
                and other.font_size >= config.title_display_ratio * row.font_size
                and -row.font_size <= other.bbox[1] - row.bbox[3] <= 1.5 * row.font_size
            ):
                return True
        gaps = [r.inward_gap for r in later if r.inward_gap is not None]
        if row.inward_gap is None or not gaps:
            return False
        return row.inward_gap >= max(config.title_gap_min, config.title_gap_factor * median(gaps))

    def repeated_boxes(self):
        """Long constant text repeated on several pages AND drawn in a box or frame.

        Repetition alone never makes a box (Step 8 decision 4): unboxed occurrences stay plain
        content with a reason. Box evidence comes from ``box_lines`` (native drawings).
        """
        config = self.config
        by_key = defaultdict(list)
        for row in self._rows():
            if row.inside_content and not row.blank and (row.page, row.line_id) not in self.roles:
                by_key[row.key].append(row)
        for key, rows in by_key.items():
            pages = sorted({r.page for r in rows})
            if len(pages) < config.min_pages or not regex.search(r"\p{L}", key):
                continue
            tokens = median(r.tokens for r in rows)
            if tokens < config.box_min_tokens:
                continue
            boxed = [r for r in rows if r.line_id in self._boxed(r.page)]
            unboxed = [r for r in rows if r.line_id not in self._boxed(r.page)]
            boxed_pages = sorted({r.page for r in boxed})
            group = _group_id("repeated", key)
            evidence = {
                "pages": len(pages),
                "boxed_pages": len(boxed_pages),
                "median_tokens": tokens,
            }
            plain = [f"constant text repeated on {len(pages)} pages without a drawn box"]
            if len(boxed_pages) < config.min_pages:
                for row in rows:
                    self._set(row, "content", 0.9, plain, group, evidence)
                continue
            reasons = [
                f"constant text repeated on {len(pages)} pages",
                f"drawn box or frame on {len(boxed_pages)} pages",
                "designed block: content, tagged repeated_box",
            ]
            self.groups.append(
                self._group(group, "repeated_box", None, boxed, 0.85, reasons, evidence)
            )
            regions = defaultdict(set)
            for row in boxed:
                regions[row.page].add(row.region_id)
                self._set(row, "repeated_box", 0.85, reasons, group, evidence)
            for row in unboxed:
                self._set(row, "content", 0.8, plain, group, evidence)
            # Other lines of the same block that are inside the drawn box belong to it.
            for page, region_ids in regions.items():
                for other in self.features[page]:
                    if (
                        other.region_id in region_ids
                        and (page, other.line_id) not in self.roles
                        and other.inside_content
                        and not other.blank
                        and other.line_id in self._boxed(page)
                    ):
                        self._set(
                            other,
                            "repeated_box",
                            0.75,
                            ["in the same drawn block as a repeated box line"],
                            group,
                        )

    def _boxed(self, page):
        if page not in self._box_cache:
            self._box_cache[page] = (
                set(self.box_lines(page, self.features[page])) if self.box_lines else set()
            )
        return self._box_cache[page]

    def _group(self, group_id, role, edge, rows, confidence, reasons, evidence=None):
        from book_core.furniture.models import FurnitureGroup

        return FurnitureGroup(
            id=group_id,
            role=role,
            edge=edge,
            pages=sorted({r.page for r in rows}),
            line_ids=[r.line_id for r in rows],
            confidence=round(min(1.0, confidence), 4),
            reasons=reasons,
            evidence=evidence or {},
        )

    def run(self):
        self.production_marks()
        self.folios()
        self.running()
        self.titles_in_slots()
        self.repeated_boxes()
        for row in self._rows():
            if (row.page, row.line_id) not in self.roles:
                reasons = ["no furniture evidence"]
                if row.blank:
                    reasons = ["blank line; no text"]
                self._set(row, "content", 0.9, reasons)
        return self


def _beyond(row, other):
    """Whether ``other`` lies between ``row`` and their shared edge (centre comparison)."""
    a, b = row.bbox, other.bbox
    if row.edge in {"top", "bottom"}:
        c, d = (a[1] + a[3]) / 2, (b[1] + b[3]) / 2
        return d < c if row.edge == "top" else d > c
    c, d = (a[0] + a[2]) / 2, (b[0] + b[2]) / 2
    return d < c if row.edge == "left" else d > c


def _same_place(a, b, tolerance=2.0):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def config_dict(config: FurnitureConfig, sequence: SequenceConfig):
    return {
        **{f"furniture.{k}": v for k, v in asdict(config).items()},
        **{f"sequence.{k}": v for k, v in asdict(sequence).items()},
    }


__all__ = ["Classifier", "FurnitureConfig", "body_style", "config_dict", "parse_label"]
