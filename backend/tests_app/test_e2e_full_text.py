"""Browse cards show the whole text: when the block is selected or being edited, with a Show full
text / Collapse toggle on each card, and a global "Full text: on/off" switch in the toolbar that is
remembered per user. Real book (job c98738ed66eff60d, page 30); a separate test app, a reviewer."""

from __future__ import annotations

import pytest

from .test_e2e_to_paragraph import CHROME, JOB, page, playwright, seeded, server, units  # noqa: F401
from .test_e2e_editor import open_edit

pytestmark = [
    pytest.mark.skipif(not CHROME or not JOB.is_file() and not (JOB / "job.json").is_file(), reason="no Chrome or job"),
]


def shown(pg, uid):
    return " ".join(row(pg, uid).locator(".bbody").first.inner_text().split())


def row(pg, uid):
    return pg.locator(f"[data-testid=unit][data-unit='{uid}']").first


def whole(r):
    return " ".join(" ".join(i["text"].split()) for i in r["items"])


def test_full_text_in_cards(server, page):  # noqa: F811
    base = server["base"]
    jid = seeded(server, page)
    # lists with an item the collapsed card cuts (more than 160 characters)
    long = [r for r in units(base, jid, 30) if r["type"] == "list" and any(len(i["text"]) > 165 for i in r["items"])]
    assert len(long) >= 2, "page 30 has two lists with a long item"
    a, b = long[0], long[1]
    full_a, full_b = whole(a), whole(b)
    page.locator("[data-testid=unit]").first.wait_for()
    cut = lambda uid: "…" in shown(page, uid)  # noqa: E731

    # collapsed by default: cut with "…", a Show full text button
    assert cut(a["id"]) and shown(page, a["id"]) != full_a
    toggle = row(page, a["id"]).get_by_test_id("toggle-full")
    assert toggle.inner_text() == "Show full text"
    toggle.click()
    assert shown(page, a["id"]) == full_a and toggle.inner_text() == "Collapse"
    toggle.click()
    assert cut(a["id"]) and toggle.inner_text() == "Show full text"

    # selecting a block shows it whole; selecting another collapses the first again
    row(page, a["id"]).locator(".bbody").click()
    assert shown(page, a["id"]) == full_a
    row(page, b["id"]).locator(".bbody").click()
    assert shown(page, b["id"]) == full_b and cut(a["id"])

    # editing a block shows it whole too
    row(page, b["id"]).locator(".bbody").click()
    open_edit(page, a["id"])
    assert shown(page, a["id"]) == full_a

    # the global switch: every card whole, remembered after a reload, off again
    switch = page.get_by_test_id("browse-full-toggle")
    assert switch.inner_text() == "Full text: off"
    switch.click()
    assert switch.inner_text() == "Full text: on"
    assert all(shown(page, r["id"]) == whole(r) for r in long)
    page.reload()
    page.locator("[data-testid=unit]").first.wait_for(timeout=400000)
    assert page.get_by_test_id("browse-full-toggle").inner_text() == "Full text: on"
    assert shown(page, b["id"]) == full_b
    page.get_by_test_id("browse-full-toggle").click()
    assert page.get_by_test_id("browse-full-toggle").inner_text() == "Full text: off"
    assert [uid for uid in (a["id"], b["id"]) if cut(uid)], "collapsed again (the selected block may stay whole)"
