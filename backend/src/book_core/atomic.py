"""The final rename of an atomic cache write, with a bounded retry for Windows file locks.

On Windows a virus scanner, indexer or a concurrent reader can hold the target briefly, and
``os.replace`` then fails with a sharing violation (``PermissionError``). The rename is retried a
few times with a short, growing delay and each retry is logged. Other errors, other platforms
and an exhausted retry budget raise unchanged, so a real permission problem is never hidden.
"""

import logging
import os
import time

LOG = logging.getLogger("book_core.cache")
WINDOWS = os.name == "nt"
ATTEMPTS = 8
FIRST_DELAY = 0.05
MAX_DELAY = 1.0


def replace_with_retry(temporary, target, *, attempts=ATTEMPTS):
    """``os.replace(temporary, target)``, retried on transient Windows locks only.

    Returns the number of attempts used. At most ``attempts - 1`` sleeps, about 3.6 s in all.
    """
    delay = FIRST_DELAY
    for attempt in range(1, attempts + 1):
        try:
            os.replace(temporary, target)
            return attempt
        except PermissionError as error:
            if not WINDOWS or attempt == attempts:
                raise
            LOG.warning(
                "transient_atomic_replace_retry target=%s attempt=%d/%d delay=%.2fs error=%s",
                target,
                attempt,
                attempts,
                delay,
                error,
            )
            time.sleep(delay)
            delay = min(MAX_DELAY, delay * 2)
    raise AssertionError("unreachable")
