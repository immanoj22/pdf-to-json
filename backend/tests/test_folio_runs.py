"""Step 21: a short roman prelim run beside a long arabic one is found; noise is not a run."""

from book_core.furniture.labels import Label
from book_core.furniture.sequence import Candidate, SequenceConfig, fit_runs

PAGES = list(range(1, 41))


def folio(page, kind, value, quality):
    return Candidate(page, f"line-{page}", Label(kind, value, "", False), quality)


def arabic_body(first=17, quality=0.25):
    return [folio(p, "arabic", p - first + 1, quality) for p in range(first, 41)]


def test_short_roman_prelims_before_a_long_arabic_run_are_a_run():
    prelims = [folio(p, "roman", p, 0.75) for p in (10, 12, 13)]
    runs = fit_runs(PAGES, prelims + arabic_body(), SequenceConfig())
    assert [(r.series[0], r.first, r.last) for r in runs] == [("roman", 10, 13), ("arabic", 17, 40)]


def test_without_the_cheaper_run_switch_the_short_run_is_lost():
    prelims = [folio(p, "roman", p, 0.75) for p in (10, 12, 13)]
    runs = fit_runs(PAGES, prelims + arabic_body(), SequenceConfig(run_switch_share=1.0))
    assert [r.series[0] for r in runs] == ["arabic"]


def test_two_stray_numbers_inside_a_run_are_not_a_run():
    body = arabic_body(first=1, quality=0.9)
    stray = [folio(20, "arabic", 5, 0.75), folio(21, "arabic", 6, 0.75)]  # another offset
    runs = fit_runs(PAGES, body + stray, SequenceConfig())
    assert [(r.series[0], r.offset) for r in runs] == [("arabic", 0)]
