"""Progress reports for long operations.

Without a rate limit a thousand-odd updates in a row flood the window event
queue and the window stops responding — Windows marks it «Not responding» even
though the work itself runs in a background thread.
"""
from __future__ import annotations

import time
from collections.abc import Callable

ProgressCb = Callable[[int, int, str], None]

# More than twenty updates a second is pointless: nobody can read them.
PROGRESS_INTERVAL_SEC = 0.05


def throttled(progress_cb: ProgressCb | None) -> ProgressCb:
    """A wrapper that drops calls coming too fast.

    The first and the last one always get through: without them the bar would
    never appear at the start nor reach the end.
    """
    if progress_cb is None:
        return lambda done, total, name: None
    last = [0.0]

    def report(done: int, total: int, name: str) -> None:
        now = time.monotonic()
        if done == 0 or done >= total or now - last[0] >= PROGRESS_INTERVAL_SEC:
            last[0] = now
            progress_cb(done, total, name)

    return report
