"""Layout-model detections computed ahead in worker processes (detection.parallel)."""

from book_core.detection import parallel
from book_core.detection.parallel import MEMORY_FLOOR_BYTES, WORKER_BYTES, prefetch, worker_count


def test_workers_are_bounded_by_the_run_the_pages_and_free_memory():
    plenty = MEMORY_FLOOR_BYTES + 16 * WORKER_BYTES
    assert worker_count(6, 500, plenty) == 6
    assert worker_count(6, 3, plenty) == 3  # never more workers than pages
    assert worker_count(6, 500, MEMORY_FLOOR_BYTES + 2 * WORKER_BYTES) == 2  # memory bound
    assert worker_count(6, 500, MEMORY_FLOOR_BYTES + WORKER_BYTES // 2) == 1  # floor kept
    assert worker_count(1, 500, plenty) == 1


def test_one_worker_or_few_pages_leave_the_work_to_the_stage(monkeypatch):
    monkeypatch.setattr(parallel, "available_memory", lambda: MEMORY_FLOOR_BYTES + 16 * WORKER_BYTES)

    def never(*_):
        raise AssertionError("no worker may start")

    monkeypatch.setattr(parallel, "ProcessPoolExecutor", never)
    assert prefetch("book.pdf", None, [], "cache", range(1, 100), workers=1) == 0
    assert prefetch("book.pdf", None, [], "cache", range(1, 3), workers=6) == 0
