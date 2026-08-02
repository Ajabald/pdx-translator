"""Сообщения о ходе длительных операций.

Без ограничения частоты тысяча с лишним обновлений подряд забивает очередь
событий окна, и оно перестаёт отвечать — Windows помечает его «Не отвечает»,
хотя работа идёт в фоновом потоке.
"""
from __future__ import annotations

import time
from collections.abc import Callable

ProgressCb = Callable[[int, int, str], None]

# Чаще двадцати раз в секунду обновлять экран нет смысла — человек не увидит.
PROGRESS_INTERVAL_SEC = 0.05


def throttled(progress_cb: ProgressCb | None) -> ProgressCb:
    """Обёртка, пропускающая частые вызовы. Первый и последний доходят всегда."""
    if progress_cb is None:
        return lambda done, total, name: None
    last = [0.0]

    def report(done: int, total: int, name: str) -> None:
        now = time.monotonic()
        if done == 0 or done >= total or now - last[0] >= PROGRESS_INTERVAL_SEC:
            last[0] = now
            progress_cb(done, total, name)

    return report
