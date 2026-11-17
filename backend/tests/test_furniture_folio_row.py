"""A running head on the same row as the printed folio is furniture even when the body's first
line starts right under it (journal layouts): the whitespace test is waived for such a line."""

from __future__ import annotations

from book_core.furniture.classify import FurnitureConfig
from test_furniture import LATIN, SOURCE, PageBuilder, decide_book, page_features


def journal(first_page=101, pages=24, tight=True):
    """Folio and head share the top row (y=60, 8 pt); the body starts at y=67 (tight) or y=90."""
    built = {}
    for number in range(1, pages + 1):
        page = PageBuilder(number)
        top = 67 if tight else 90
        body = [page.line(f"b{i}", 70, top + 12 * i, 540, LATIN[i % 3]) for i in range(34)]
        band = page.band("body", top, top + 420, [(70, 540, "column")])
        page.region("body", "main_text", body, band, 0)
        even = number % 2 == 0
        folio = page.line("folio", 70 if even else 520, 60, 90 if even else 540, str(first_page + number), size=8.0)
        page.region("folio", "page_number_candidate", [folio])
        head = page.line("head", 100 if even else 330, 60, 280 if even else 510,
                         "Journal Title" if even else "Section Name", size=8.0)
        page.region("head", "header_footer_candidate", [head])
        built[number] = page.build()
    return decide_book({n: page_features(*built[n]) for n in built}, {}, SOURCE)


def roles(d, number):
    return {r.line_id.split("-", 1)[1]: r.role for r in d.roles[number]}


def test_a_head_beside_the_folio_is_a_running_head_though_the_body_is_close():
    d = journal(tight=True)
    for number in (4, 5, 12, 13):
        r = roles(d, number)
        assert r["folio"] == "folio" and r["head"] == "running_head", (number, r)
        assert r["b0"] == "content"  # the body's first line is not taken with it


def test_with_room_under_the_head_nothing_changes():
    d = journal(tight=False)
    assert all(roles(d, n)["head"] == "running_head" for n in (4, 5, 12, 13))


def test_a_line_that_only_looks_like_a_head_stays_content_without_a_folio_beside_it():
    # the same tight layout, but the folio is at the bottom: the whitespace rule applies again
    built = {}
    for number in range(1, 25):
        page = PageBuilder(number)
        body = [page.line(f"b{i}", 70, 67 + 12 * i, 540, LATIN[i % 3]) for i in range(34)]
        band = page.band("body", 67, 487, [(70, 540, "column")])
        page.region("body", "main_text", body, band, 0)
        head = page.line("head", 100, 60, 280, "Journal Title", size=8.0)
        page.region("head", "header_footer_candidate", [head])
        folio = page.line("folio", 300, 750, 320, str(100 + number), size=8.0)
        page.region("folio", "page_number_candidate", [folio])
        built[number] = page.build()
    d = decide_book({n: page_features(*built[n]) for n in built}, {}, SOURCE)
    assert all(roles(d, n)["head"] == "content" for n in (4, 5, 12))
    assert FurnitureConfig().min_inward_gap == 0.75
