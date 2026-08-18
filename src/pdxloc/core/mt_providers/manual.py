"""Ручной веб-режим: перевод через браузер, без ключей.

Перенос приёма из ESP/ESM Translator. Инструмент склеивает пачку строк
нумерованными разделителями, человек вставляет её в любой веб-переводчик,
возвращает результат, инструмент режет обратно. Ключей не нужно вовсе, работает
с чем угодно — и это единственный режим, доступный тому, у кого нет ни одной
подписки.

**Разделители нумерованные, и это главное.** Ненумерованный разделитель ловит
только потерю строки; нумерованный ловит ещё и перестановку — а перевод,
приземлившийся на чужой ключ, выглядит как сделанная работа и находится через
недели. При любом расхождении пачка не применяется целиком.

В сеть модуль не ходит: `join` и `split` — обычные функции, и проверяются без
Qt и без сокета.
"""
from __future__ import annotations

import re

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.mt_errors import MtResponseError
from pdxloc.core.mt_providers import ProviderConfig

DEFAULT_SEPARATOR = "===%d==="


def _line(separator: str, index: int) -> str:
    return separator.replace("%d", str(index))


def join(texts: list[str], separator: str = DEFAULT_SEPARATOR) -> str:
    """Склеить пачку для вставки в переводчик."""
    parts: list[str] = []
    for index, text in enumerate(texts):
        parts.append(_line(separator, index))
        parts.append(text)
    return "\n".join(parts)


def _pattern(separator: str) -> re.Pattern:
    head, _, tail = separator.partition("%d")
    return re.compile(rf"^[ \t]*{re.escape(head)}\s*(\d+)\s*{re.escape(tail)}[ \t]*$",
                      re.M)


def split(text: str, count: int, separator: str = DEFAULT_SEPARATOR) -> list[str]:
    """Разрезать ответ обратно. Любое расхождение — отказ применить пачку.

    Сверяем не только количество: номера обязаны идти подряд от нуля. Сервис,
    поменявший куски местами, иначе прошёл бы незамеченным.
    """
    marks = list(_pattern(separator).finditer(text))
    numbers = [int(m.group(1)) for m in marks]
    if numbers != list(range(count)):
        raise MtResponseError(fill(translate(
            "Mt", "The answer has %1 separators instead of %2, or their order "
                  "changed. Nothing from this batch was applied."),
            len(marks), count))

    result: list[str] = []
    for i, mark in enumerate(marks):
        start = mark.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        result.append(text[start:end].strip("\n"))
    return result


class ManualProvider:
    """Формально провайдер, фактически — конвейер без транспорта.

    Реализует тот же договор, что и остальные, чтобы охват, экранирование
    разметки, пачка отката и сводка работали ровно так же. Сам ничего не
    переводит: за него это делает человек в браузере, а `translate_batch`
    здесь никто не зовёт.
    """

    name = "manual"
    label = QT_TRANSLATE_NOOP("Mt", "Manual — through a web translator")
    needs_key = False
    char_limit = 100_000

    def __init__(self, config: ProviderConfig | None = None):
        self.config = config or ProviderConfig()

    def supports(self, src_locale: str, tgt_locale: str) -> bool:
        return True

    def translate_batch(self, texts: list[str],
                        src_locale: str, tgt_locale: str) -> list[str | None]:
        raise MtResponseError(translate(
            "Mt", "The manual mode is driven from its own tab, not from here."))
