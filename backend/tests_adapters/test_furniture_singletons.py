"""The QC verdict warns about running head/foot lines printed once while the others repeat."""

from __future__ import annotations

from book_adapters import qc


def report(count):
    singles = {"count": count, "examples": [{"page": 86}, {"page": 109}][:count]}
    return {"status": "written", "checks": {"lossless": {"furniture_singletons": singles}}, "alt_text": {},
            "profile": {}, "settings": {}}


def test_the_verdict_warns_and_names_the_pages():
    verdict, reasons = qc.verdict(report(2))
    assert verdict == "warn" and any("2 running head/foot line(s) printed once" in r and "86, 109" in r for r in reasons)
    assert qc.verdict(report(0))[0] == "pass"
