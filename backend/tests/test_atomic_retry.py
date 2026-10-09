"""Atomic cache writes retry a transient Windows lock on the final rename, boundedly and logged."""

import json
import logging
import os

import pytest

from book_core import atomic
from book_core.extraction.cache import atomic_json
from book_core.model.common import BBox
from book_core.objects.analysis import atomic_write
from book_core.reference.cache import _write


class FlakyReplace:
    """os.replace that raises a sharing violation a given number of times first."""

    def __init__(self, failures, error=PermissionError):
        self.failures = failures
        self.error = error
        self.calls = 0
        self.real = os.replace

    def __call__(self, source, target):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error(32, "The process cannot access the file", str(target))
        return self.real(source, target)


@pytest.fixture
def windows_lock(monkeypatch):
    sleeps = []
    monkeypatch.setattr(atomic, "WINDOWS", True)
    monkeypatch.setattr(atomic.time, "sleep", sleeps.append)

    def install(failures, error=PermissionError):
        flaky = FlakyReplace(failures, error)
        monkeypatch.setattr(atomic.os, "replace", flaky)
        return flaky

    return install, sleeps


def test_transient_lock_is_retried_and_logged(tmp_path, windows_lock, caplog):
    install, sleeps = windows_lock
    flaky = install(2)
    source, target = tmp_path / "a.tmp", tmp_path / "a.json"
    source.write_text("x")
    with caplog.at_level(logging.WARNING, logger="book_core.cache"):
        assert atomic.replace_with_retry(source, target) == 3
    assert target.read_text() == "x" and not source.exists()
    assert flaky.calls == 3
    assert sleeps == [0.05, 0.1]
    retries = [r for r in caplog.records if "transient_atomic_replace_retry" in r.getMessage()]
    assert len(retries) == 2


def test_retry_is_bounded_and_reraises(tmp_path, windows_lock):
    install, sleeps = windows_lock
    flaky = install(100)
    source = tmp_path / "a.tmp"
    source.write_text("x")
    with pytest.raises(PermissionError):
        atomic.replace_with_retry(source, tmp_path / "a.json")
    assert flaky.calls == atomic.ATTEMPTS
    assert len(sleeps) == atomic.ATTEMPTS - 1
    assert max(sleeps) <= atomic.MAX_DELAY and sum(sleeps) < 4.0


def test_no_retry_off_windows_or_for_other_errors(tmp_path, windows_lock, monkeypatch):
    install, sleeps = windows_lock
    source = tmp_path / "a.tmp"
    source.write_text("x")
    flaky = install(1, FileNotFoundError)
    with pytest.raises(FileNotFoundError):
        atomic.replace_with_retry(source, tmp_path / "a.json")
    assert flaky.calls == 1
    monkeypatch.setattr(atomic, "WINDOWS", False)
    flaky = install(1)
    with pytest.raises(PermissionError):
        atomic.replace_with_retry(source, tmp_path / "a.json")
    assert flaky.calls == 1 and sleeps == []


@pytest.mark.parametrize("writer", ["extraction", "objects", "reference"])
def test_every_cache_writer_survives_a_transient_lock(tmp_path, windows_lock, writer):
    install, _ = windows_lock
    flaky = install(2)
    target = tmp_path / "cache" / "1.json"
    if writer == "extraction":
        atomic_json(target, {"value": 1})
        assert json.loads(target.read_text("utf-8")) == {"value": 1}
    elif writer == "objects":
        atomic_write(target, BBox(x0=0, y0=0, x1=1, y1=1), "fingerprint")
        assert json.loads(target.read_text("utf-8"))["fingerprint"] == "fingerprint"
    else:
        _write(target, {"value": 1}, "fingerprint")
        assert json.loads(target.read_text("utf-8"))["fingerprint"] == "fingerprint"
    assert flaky.calls == 3
    assert [p.name for p in target.parent.iterdir()] == ["1.json"]
