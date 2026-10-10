"""Whole-book folio sequence: printed page labels fitted to physical pages.

Each folio candidate (a label-like line in a page edge zone) implies a state: its label series
(arabic, roman lower/upper, or one prefix) and its offset, physical page minus label value. A
Viterbi pass over the physical pages picks one state per page (or none). Staying in a state is
free, so pages without a printed folio inside a run keep the run's state; switching costs a
penalty, so a new run needs several agreeing pages. A switch is a section reset or an
unnumbered insert. Then:

- printed: the page's chosen candidate fits its run (source ``printed``);
- interpolated: a page between two printed folios of one run (source ``inferred``);
- extrapolated: at most ``extrapolate`` pages beyond a run's first or last printed folio, when
  the label stays positive and collides with no printed label (source ``inferred``, review);
- otherwise the page has no label (front covers, inserts, unnumbered back matter).

Optional PDF page-label metadata is compared, never trusted blindly. It is trusted when it
agrees with the printed folios on enough pages, and then labels only front matter (pages
before the first printed run) that has no fitted printed folio (source ``metadata``). Inside
or after the runs, inference decides and metadata only confirms or flags. Nothing
depends on page numbers, coordinates, fonts, a script or a book.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from book_core.furniture.labels import Label, parse_label


@dataclass(frozen=True)
class SequenceConfig:
    switch_penalty: float = 2.5
    extrapolate: int = 2
    metadata_min_pages: int = 5
    metadata_min_agreement: float = 0.9
    min_run_printed: int = 2  # a run needs this many printed folios to label other pages

    def __post_init__(self):
        if self.switch_penalty <= 0 or self.extrapolate < 0 or self.min_run_printed < 1:
            raise ValueError("Invalid folio sequence configuration")
        if not 0.5 < self.metadata_min_agreement <= 1:
            raise ValueError("Metadata agreement must be in (0.5, 1]")


@dataclass(frozen=True)
class Candidate:
    page: int
    line_id: str
    label: Label
    quality: float  # 0..1 position/style evidence; never a probability
    embedded: bool = False  # the label sits at an end of a longer furniture line

    @property
    def state(self):
        return (self.label.series, self.page - self.label.value)


@dataclass
class Run:
    index: int
    series: tuple[str, str, bool]
    offset: int
    printed: dict[int, Candidate] = field(default_factory=dict)

    @property
    def first(self):
        return min(self.printed)

    @property
    def last(self):
        return max(self.printed)

    def label(self, page):
        value = page - self.offset
        if value < 1:
            return None
        kind, prefix, upper = self.series
        return Label(kind, value, prefix, upper).render()


@dataclass(frozen=True)
class PageLabel:
    page: int
    label: str | None
    kind: str  # arabic | roman | prefixed | none
    source: str  # printed | metadata | inferred | none
    confidence: float
    run: int | None
    folio: Candidate | None
    metadata_label: str | None
    reasons: tuple[str, ...]
    review_required: bool


def fit_runs(pages: list[int], candidates: list[Candidate], config: SequenceConfig) -> list[Run]:
    """Viterbi over physical pages; states are (series, offset) or none."""
    by_page = defaultdict(dict)
    for candidate in candidates:
        state = candidate.state
        best = by_page[candidate.page].get(state)
        if best is None or candidate.quality > best.quality:
            by_page[candidate.page][state] = candidate
    states = sorted({c.state for c in candidates}, key=repr)
    none = None
    all_states = [none, *states]
    score = {s: 0.0 if s is none else -config.switch_penalty for s in all_states}
    back = []
    for page in pages:
        best_state = max(score, key=lambda s: (score[s], s is none))
        best_value = score[best_state]
        new, pointers = {}, {}
        for state in all_states:
            stay = score[state]
            switch = best_value - config.switch_penalty
            if stay >= switch:
                value, pointer = stay, state
            else:
                value, pointer = switch, best_state
            emission = by_page[page].get(state).quality if state in by_page[page] else 0.0
            new[state] = value + emission
            pointers[state] = pointer
        score = new
        back.append(pointers)
    state = max(score, key=lambda s: (score[s], s is none))
    path = []
    for pointers in reversed(back):
        path.append(state)
        state = pointers[state]
    path.reverse()
    runs: list[Run] = []
    previous = object()
    for page, state in zip(pages, path, strict=True):
        if state is not none and state != previous:
            runs.append(Run(len(runs), state[0], state[1]))
        previous = state
        if state is not none and state in by_page[page]:
            runs[-1].printed[page] = by_page[page][state]
    return [run for run in runs if len(run.printed) >= config.min_run_printed]


def _metadata_trust(metadata, printed, config):
    pairs = [(metadata[p], label) for p, label in printed.items() if metadata.get(p)]
    agree = sum(a == b for a, b in pairs)
    rate = agree / len(pairs) if pairs else None
    trusted = len(pairs) >= config.metadata_min_pages and rate >= config.metadata_min_agreement
    return trusted, {"compared_pages": len(pairs), "agreeing_pages": agree, "agreement": rate}


def page_labels(
    pages: list[int],
    candidates: list[Candidate],
    metadata: dict[int, str] | None = None,
    config: SequenceConfig | None = None,
) -> tuple[list[PageLabel], list[Run], dict]:
    """One label decision per physical page, the fitted runs and a metadata comparison."""
    config = config or SequenceConfig()
    metadata = {p: v for p, v in (metadata or {}).items() if v}
    runs = fit_runs(pages, candidates, config)
    printed_page = {p: (run, c) for run in runs for p, c in run.printed.items()}
    trusted, comparison = _metadata_trust(
        metadata, {p: r.label(p) for p, (r, _) in printed_page.items()}, config
    )
    decided = []
    for page in pages:
        meta = metadata.get(page)
        if page in printed_page:
            run, candidate = printed_page[page]
            label = run.label(page)
            support = len(run.printed)
            confidence = round(min(0.99, 0.6 + 0.35 * candidate.quality + 0.01 * support), 4)
            reasons = [
                f"printed folio fits a run of {support} printed labels",
                f"{run.series[0]} series, offset {run.offset}",
            ]
            if candidate.embedded:
                reasons.append("label at the end of a furniture line")
            review = confidence < 0.6
            if meta is not None and meta != label:
                reasons.append(f"PDF page-label metadata differs: {meta!r}")
                review = True
            decided.append(
                PageLabel(
                    page,
                    label,
                    run.series[0],
                    "printed",
                    confidence,
                    run.index,
                    candidate,
                    meta,
                    tuple(reasons),
                    review,
                )
            )
            continue
        inside = [run for run in runs if run.first < page < run.last]
        before = [run for run in runs if run.last < page]
        after = [run for run in runs if run.first > page]
        options = []
        if inside:
            run = inside[0]
            options.append((run, 0.85, "between printed folios of one run"))
        else:
            # Sequences restart at 1 on unnumbered openers: when the next run's label 1 falls
            # in the gap, the pages from there on belong to it (the rest stay with the run
            # before, within the extrapolation limit).
            restart = after[0].offset + 1 if after else None
            gap_start = before[-1].last + 1 if before else 1
            if restart is not None and gap_start <= restart <= page:
                options.append((after[0], 0.75, "a run that restarts at 1 in the gap"))
            elif before and page - before[-1].last <= config.extrapolate:
                options.append((before[-1], 0.5, "after the last printed folio of a run"))
            if after and after[0].first - page <= config.extrapolate:
                options.append((after[0], 0.45, "before the first printed folio of a run"))
        # An extrapolated label may not repeat a printed label of a neighbouring run (inserted
        # unnumbered pages); repeats across distant resets are legitimate. Interpolated
        # labels lie strictly inside their own run and are unique there.
        nearby = (
            set() if inside else {r.label(p) for r in before[-1:] + after[:1] for p in r.printed}
        )
        chosen = None
        for run, confidence, reason in options:
            label = run.label(page)
            if label is None or label in nearby:
                continue
            chosen = (run, label, confidence, reason)
            break
        front = not runs or page < runs[0].first
        if trusted and meta is not None and front:
            # Front matter only (Step 9 correctness rule): metadata that agrees with the
            # fitted printed folios elsewhere labels pages before the first printed run.
            reasons = [
                "front matter without a fitted printed folio; PDF page-label metadata agrees "
                "with the printed folios elsewhere"
            ]
            disagrees = chosen is not None and chosen[1] != meta
            if chosen is not None:
                reasons.append(
                    f"sequence would infer {chosen[1]!r}" if disagrees else "sequence agrees"
                )
            parsed = parse_label(meta)
            decided.append(
                PageLabel(
                    page,
                    meta,
                    parsed.kind if parsed else "other",
                    "metadata",
                    0.55 if disagrees else 0.9,
                    chosen[0].index if chosen is not None and not disagrees else None,
                    None,
                    meta,
                    tuple(reasons),
                    disagrees,
                )
            )
            continue
        if chosen is not None:
            run, label, confidence, reason = chosen
            reasons = ["no printed folio; " + reason]
            if trusted and meta is not None:
                if meta == label:
                    confidence = max(confidence, 0.9)
                    reasons.append("trusted PDF page-label metadata agrees")
                else:
                    confidence = min(confidence, 0.55)
                    reasons.append(f"trusted PDF page-label metadata differs: {meta!r}")
            decided.append(
                PageLabel(
                    page,
                    label,
                    run.series[0],
                    "inferred",
                    confidence,
                    run.index,
                    None,
                    meta,
                    tuple(reasons),
                    confidence < 0.6,
                )
            )
            continue
        reasons = ["no printed folio and no run to infer from"]
        if meta is not None:
            reasons.append(
                f"trusted PDF page-label metadata {meta!r} not used outside front matter"
                if trusted
                else f"untrusted PDF page-label metadata {meta!r} not used"
            )
        decided.append(
            PageLabel(page, None, "none", "none", 0.5, None, None, meta, tuple(reasons), False)
        )
    comparison["trusted"] = trusted
    comparison["pages_with_metadata"] = len(metadata)
    comparison["disagreeing_pages"] = sorted(
        d.page for d in decided if d.metadata_label and d.label and d.metadata_label != d.label
    )
    return decided, runs, comparison
