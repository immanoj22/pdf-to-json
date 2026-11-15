"""'Apply to all similar' for review answers: one group, one Undo, same events as one by one."""

from __future__ import annotations

from book_app.decisions import Decisions


def _entries(n, fix=False):
    return [{"key": f"k{i}", "item_kind": "heading", "item": {"unit": f"u{i}"},
             **({"fix": {"op": "heading_set", "unit": f"u{i}", "level": 2}} if fix else {})}
            for i in range(n)]  # fmt: skip


def test_group_answers_match_single_answers_and_undo_together(tmp_path):
    one, many = Decisions(tmp_path / "a"), Decisions(tmp_path / "b")
    (tmp_path / "a").mkdir(), (tmp_path / "b").mkdir()
    for e in _entries(3):
        one.decide("Asha", e["key"], e["item_kind"], "accept", None, "", e["item"])
    many.decide_many("Asha", "accept", _entries(3), group="g1")
    shape = lambda d: {k: v for k, v in d.items() if k not in ("id", "at", "group")}  # noqa: E731
    assert [shape(e) for e in one.load()["events"]] == [shape(e) for e in many.load()["events"]]
    assert set(many.current()) == {"k0", "k1", "k2"}
    many.revoke_group("Asha", "g1")
    assert many.current() == {}


def test_group_fix_makes_one_edit_per_item_and_undoes_with_the_group(tmp_path):
    (tmp_path / "c").mkdir()
    log = Decisions(tmp_path / "c")
    log.decide_many("Asha", "fix", _entries(2, fix=True), group="g2")
    assert [(e["unit"], e["source"]) for e in log.edits()] == [("u0", "k0"), ("u1", "k1")]
    assert all(e["fix"]["op"] == "heading_set" for e in log.current().values())
    log.revoke_group("Asha", "g2")
    assert log.edits() == [] and log.current() == {}
