"""Layout-model detections of many pages computed ahead, in several worker processes.

The figures and equations stages ask the layout models about pages one at a time through the
validated per-page cache (``detection.cache.detect_page``). This module fills that cache first:
each spawned worker builds the same detectors, sets the same single model thread
(``book_run.fix_model_threads``) and calls the same ``detect_page``, so every cached result is
the one the stage would have computed itself. The stages then read the cache; their output is
unchanged. Pages already cached are only read back.

The number of workers is the run's worker count, bounded by the free memory: each worker
holds its own copy of the models, and ``MEMORY_FLOOR_BYTES`` stays free.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor

from book_core.telemetry import available_memory

# One worker with both layout models loaded: measured peak 1.69 GB (2026-11-13), with margin.
WORKER_BYTES = 2 * 1024**3
MEMORY_FLOOR_BYTES = 1024**3  # memory left free for the system and the app
MIN_PAGES = 4  # fewer pages are not worth starting workers for

_JOB = None


def worker_count(workers: int, pages: int, free: int | None = None) -> int:
    """Workers to start: at most the run's workers and one per page, within free memory."""
    free = available_memory() if free is None else free
    by_memory = max(0, (free - MEMORY_FLOOR_BYTES) // WORKER_BYTES)
    return int(max(1, min(workers, pages, by_memory)))


def _start(source, extractor, factories, cache_dir):
    global _JOB
    from book_core.book_run import fix_model_threads

    fix_model_threads()
    detectors = [factory(**kwargs) for factory, kwargs in factories]
    _JOB = (source, extractor, detectors, cache_dir)


def _detect(number):
    from book_core.detection.cache import detect_page

    source, extractor, detectors, cache_dir = _JOB
    for detector in detectors:
        detect_page(source, number, extractor, detector, cache_dir)
    return number


def prefetch(source, extractor, factories, cache_dir, pages, workers, progress=None) -> int:
    """Fill the detection cache for ``pages`` with every detector built from ``factories``
    (``[(class, keyword arguments)]``); returns the number of workers used (0: nothing done,
    the stage computes the pages itself)."""
    pages = list(pages)
    count = worker_count(workers, len(pages))
    if count < 2 or len(pages) < MIN_PAGES:
        return 0
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=count,
        mp_context=context,
        initializer=_start,
        initargs=(source, extractor, factories, cache_dir),
    ) as pool:
        for done, _ in enumerate(pool.map(_detect, pages), 1):
            if progress:
                progress(done, len(pages))
    return count


__all__ = ["MEMORY_FLOOR_BYTES", "WORKER_BYTES", "prefetch", "worker_count"]
