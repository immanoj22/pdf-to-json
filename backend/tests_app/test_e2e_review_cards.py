"""The review cards. Two parts:

* ``test_review_model``: the plain data behind a card (questions, answers, who counts as a person,
  the order) checked in Chrome, because the model is a browser module (no node on this machine).
* ``test_keyboard_flow``: an employee works 20 mixed items with the keyboard only on a COPY of a
  converted book. Set ``REVIEW_TEST_URL`` (an app on a copy of the data, never the live app) and
  ``REVIEW_TEST_JOB``; skipped otherwise. Every answer must reach the audit log in the same shape
  as before (who, key, item_kind, action, fix, note, item), and U must take the last one back."""

from __future__ import annotations

import os

import pytest
import requests
from tests_app.test_e2e_browser import CHROME, page, playwright, server  # noqa: F401

pytestmark = pytest.mark.skipif(not os.path.exists(CHROME), reason="Chrome is not installed")

MODEL = """async () => {
  const m = await import('/assets/review_model.js');
  const fig = { kind: 'figure', editor: 'figure', unit: 'u1', reason: 'x', current: { type: 'figure', decorative: false } };
  const dash = { kind: 'character', editor: 'dash', unit: 'u2', offset: 87, reason: 'en dash or minus before a number at offset 87: kept en dash', current: { type: 'table' } };
  const dashMinus = { ...dash, reason: 'en dash or minus before a number at offset 5: kept minus' };
  const head = { kind: 'heading', editor: 'heading', unit: 'u3', reason: 'r', current: { type: 'heading', level: 3, text: 'NOTES' } };
  const stru = { kind: 'structure', severity: 'needs_review' }, must = { kind: 'list', severity: 'must_check' }, rest = { kind: 'table', severity: 'needs_review' };
  const bound = { kind: 'structure', editor: 'role', unit: 'u4', reason: 'unit boundary below confidence (Check where the unit starts and ends and what kind it is.)', current: { type: 'paragraph', text: 'The rate of formation \\nof NADH is measured.' } };
  const lines = { ...bound, reason: 'a line join inside the unit is uncertain' };
  const bullet = { kind: 'list', editor: 'role', unit: 'u5', reason: "broken bullet glyph '3/4'", current: { type: 'list', text: 'a | b' } };
  const out = {};
  const hy = { kind: 'character', editor: 'hyphen_space', unit: 'u7', offset: 21, reason: 'Hyphen followed by a space at offset 21: “acid- base” (written “acid-base” elsewhere in the book): remove the space?', current: { type: 'paragraph', text: 'Disorders of acid- base balance.' } };
  out.hyphen = [m.question(hy), m.answersFor(hy).map(a => [a.label, a.action, a.suggested || false, a.fix && a.fix.op, a.fix && a.fix.offset]), m.helpFor(hy)[0]];
  out.hyphenUnknown = m.answersFor({ ...hy, reason: 'Hyphen followed by a space at offset 21: “acid- base”: remove the space?' }).map(a => a.suggested || false);
  // two flags on one picture are one row; two different pictures stay two rows; a paragraph flag
  // and a heading flag on the same block ask different questions and stay apart
  const f1 = { key: 'k1', kind: 'figure', editor: 'figure', unit: 'p1', reason: 'layout models do not find a figure here', current: { type: 'figure' }, decision: { who: 'manoi', action: 'accept' } };
  const f2 = { ...f1, key: 'k2', reason: 'page label inferred', decision: null, severity: 'must_check' };
  const f3 = { ...f1, key: 'k3', unit: 'p2' };
  const b1 = { ...bound, key: 'k4', unit: 'p3' }, h1 = { ...head, key: 'k5', unit: 'p3' };
  const rows = m.mergeItems([f1, f2, f3, b1, h1]);
  out.merge = rows.map(r => [r.key, m.membersOf(r).map(x => x.key).join('+'), m.confirmed(r), r.severity || null]);
  out.bound = [m.question(bound), m.itemKindName(bound), m.question(lines), m.itemKindName({ kind: 'structure', reason: 'list or entry decision below confidence' })];
  out.boundAnswers = m.answersFor(bound).map(a => [a.label, a.action, a.form || null, a.fix && a.fix.op]);
  out.linesAnswers = m.answersFor(lines).map(a => a.label);
  out.bullet = [m.question(bullet), m.answersFor(bullet)[0].label];
  out.words = [m.decisionWords({ action: 'accept' }), m.decisionWords({ action: 'fix', fix: { op: 'split' } }), m.decisionWords({ action: 'skip' })];
  out.question = [m.question(fig), m.question(dash), m.question(head)];
  out.dashKept = [m.keptDash(dash), m.keptDash(dashMinus)];
  // the answer that equals the tool's result is an accept, the other one a fix
  out.dashAnswers = m.answersFor(dash).map(a => [a.label, a.action, a.suggested || false, a.fix && a.fix.char]);
  out.dashMinusAnswers = m.answersFor(dashMinus).map(a => [a.label, a.action, a.suggested || false, a.fix && a.fix.char]);
  out.fig = m.answersFor(fig).map(a => [a.label, a.action]);
  out.head = m.answersFor(head).map(a => [a.label, a.action, a.form || null]);
  out.person = [m.isPerson({ who: 'manoi' }), m.isPerson({ who: 'Claude Desktop (AI)' }), m.isPerson({ who: 'Claude Desktop' }), m.isPerson(null)];
  out.confirmed = [m.confirmed({ decision: { who: 'manoi' } }), m.confirmed({ decision: { who: 'Claude Desktop (AI)' } }), m.confirmed({})];
  out.order = m.ordered([rest, must, stru]).map(i => i.kind);
  out.similar = m.similarKey({ kind: 'list', reason: "broken bullet glyph '\\\\x99' on page 3" }) === m.similarKey({ kind: 'list', reason: "broken bullet glyph '\\\\x99' on page 9" });
  // every answer text is plain: at most 4 answers, no internal terms
  const kinds = Object.keys(m.KIND), jargon = /model|offset|unit|boundary|confidence|adapter|lists\\.marks|DTD/i;
  out.jargon = [];
  for (const k of kinds) { const it = { kind: k, editor: 'plain', reason: '', current: {} }; const q = m.question(it); if (jargon.test(q) || q.split(' ').length > 10) out.jargon.push(q);
    for (const a of m.answersFor(it)) if (jargon.test(a.label + a.hint)) out.jargon.push(a.label); }
  return out;
}"""


def test_review_model(server, page):  # noqa: F811
    page.goto(server["base"] + "/")
    r = page.evaluate(MODEL)
    assert r["question"][0] == "Is this a picture?" and "NOTES" in r["question"][2]
    assert r["dashKept"] == ["–", "−"]
    # defaults follow what the tool kept: the kept dash is the accepted, suggested answer
    assert r["dashAnswers"] == [["Range (–)", "accept", True, None], ["Minus (−)", "fix", False, "−"]]
    assert r["dashMinusAnswers"] == [["Range (–)", "fix", False, "–"], ["Minus (−)", "accept", True, None]]
    assert r["fig"][0] == ["Yes, it's a picture", "accept"] and r["fig"][1][1] == "fix"
    assert r["head"][0][1] == "accept" and r["head"][2][2] == "heading"
    assert r["person"] == [True, False, False, False]
    assert r["confirmed"] == [True, False, False]
    assert r["order"] == ["structure", "list", "table"]
    assert r["similar"] is True
    assert r["jargon"] == []
    # the hyphen-space card: one click removes the space (suggested when the book writes the compound whole)
    assert r["hyphen"][0] == "Hyphen followed by a space — remove the space?"
    assert r["hyphen"][1] == [["Yes, remove the space", "fix", True, "remove_char", 21], ["No, keep the space", "accept", False, None, None]]
    assert r["hyphenUnknown"] == [False, True]  # no evidence in the book: keeping is the suggested answer
    # a "unit" is one block of text: its flags ask about the paragraph, never about chapters
    assert r["bound"] == ["Is this one whole paragraph?", "Paragraph", "Do these lines belong to the same paragraph?", "List"]
    assert r["boundAnswers"] == [["Yes, one paragraph", "accept", None, None], ["No, split it…", "fix", "split", None],
                                 ["It continues in the next one", "fix", None, "join_next"], ["Something else…", "fix", "role", None]]
    assert "It continues in the next one" not in r["linesAnswers"]  # lines inside one block: no join offered
    assert r["bullet"] == ["Is this symbol a bullet?", "Yes, it's a bullet"]
    assert r["words"] == ["kept as it is", "changed", "skipped"]
    # one row per block and question; open until every flag on it is answered; must check wins
    assert r["merge"] == [["k1", "k1+k2", False, "must_check"], ["k3", "k3", True, None], ["k4", "k4", False, None], ["k5", "k5", False, None]]


@pytest.mark.skipif(not os.environ.get("REVIEW_TEST_URL"), reason="needs an app on a copy of a converted book")
def test_keyboard_flow():
    base, job = os.environ["REVIEW_TEST_URL"].rstrip("/"), os.environ["REVIEW_TEST_JOB"]
    assert base.rsplit(":", 1)[-1] != "8777", "never run this against the live app"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.set_default_timeout(60000)
        problems = []
        pg.on("pageerror", lambda e: problems.append(str(e)))
        pg.goto(base + "/")
        pg.evaluate("localStorage.setItem('reviewer','Keyboard Tester');localStorage.setItem('role','reviewer')")
        pg.goto(f"{base}/#/job/{job}/review")
        pg.get_by_test_id("item-card").wait_for(timeout=300000)
        before = {e["id"] for e in requests.get(f"{base}/api/jobs/{job}/decisions").json()["events"]}
        seen_kinds, answered = [], []
        pg.locator("body").click(position={"x": 5, "y": 5})  # focus on the page, not on a field
        wanted = ["structure", "figure", "heading", "list", "character", "table", "join", "language", "alt_text", "caption"]
        present = pg.get_by_test_id("filter-kind").locator("option").evaluate_all("os => os.map(o => o.value)")
        rotation = [k for k in wanted if k in present]  # only the kinds this book has
        for n in range(20):
            card = pg.get_by_test_id("item-card")
            for step in range(len(rotation)):  # mixed kinds; a kind with nothing open left is passed over
                pg.get_by_test_id("filter-kind").select_option(rotation[(n + step) % len(rotation)])
                if card.count():
                    break
            card.wait_for()
            kind, key = card.get_attribute("data-kind"), card.get_attribute("data-key")
            seen_kinds.append(kind)
            if n == 3:  # look around without deciding
                pg.locator("body").click(position={"x": 5, "y": 5})
                pg.keyboard.press("ArrowRight"); pg.keyboard.press("ArrowLeft")
                assert pg.get_by_test_id("item-card").get_attribute("data-key") == key
            has_confirm = pg.get_by_test_id("confirm").count() == 1
            if n % 5 == 4:
                pg.keyboard.press("s")
            elif has_confirm or pg.locator("[data-testid=accept]").count():
                pg.keyboard.press("Enter")
            else:
                pg.keyboard.press("1")  # a form opens: type nothing, nothing is saved
                if pg.get_by_test_id("confirm-fix").count():
                    pg.keyboard.press("Escape")
                    pg.get_by_test_id("cancel-fix").click()
                    pg.keyboard.press("s")
            answered.append(key)
            pg.wait_for_function("k => !document.querySelector('[data-testid=item-card]') || document.querySelector('[data-testid=item-card]').dataset.key !== k", arg=key)
            pg.locator("body").click(position={"x": 5, "y": 5})
        assert len(set(seen_kinds)) >= 2, seen_kinds
        data = requests.get(f"{base}/api/jobs/{job}/decisions").json()
        new = [e for e in data["events"] if e["id"] not in before and e["type"] == "decision"]
        # each answered row is in the log in order; a row that holds several flags on one block also
        # records its other keys with the same action, and their fix only points at the row's lead
        assert [k for k in dict.fromkeys(e["key"] for e in new) if k in answered] == answered
        leads = set(answered)
        for e in new:
            if e["key"] not in leads:
                assert e["fix"] is None or set(e["fix"]) == {"same_as"}, e
        assert all(e["who"] == "Keyboard Tester" for e in new)
        # the same fields as every earlier decision in the log
        old = next(e for e in data["events"] if e["id"] in before and e["type"] == "decision")
        assert set(new[0]) == set(old) or set(old) <= set(new[0]) | {"fix"}
        assert {"key", "item_kind", "action", "fix", "note", "item", "who", "at"} <= set(new[0])
        assert {e["action"] for e in new} <= {"accept", "skip", "fix"}
        # U takes the last answer back, and the item is open again
        last = answered[-1]
        pg.keyboard.press("u")
        pg.wait_for_function(
            "async ([b, j, k]) => { const d = await (await fetch(b + '/api/jobs/' + j + '/decisions')).json(); return d.decisions[k] === undefined || d.decisions[k].who !== 'Keyboard Tester'; }",
            arg=[base, job, last], timeout=120000)
        assert not problems, problems
        browser.close()
