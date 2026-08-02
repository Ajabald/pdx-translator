"""Статусы переводимых строк: значения в БД и русские названия.

Цвета живут в gui/theme.py — их два набора (светлый и тёмный), и ядру,
которое работает без интерфейса, они не нужны.
"""
from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    UNTRANSLATED = "untranslated"
    AUTO = "auto"                # подставлено из памяти переводов, требует проверки
    TRANSLATED = "translated"
    REVIEWED = "reviewed"
    STALE = "stale"              # EN изменился после перевода
    IGNORED = "ignored"          # перевод не нужен (например, строка из одних тегов)
    CUSTOM = "custom"            # пользовательская пометка (аналог статуса 150 в EET)


STATUS_LABELS: dict[Status, str] = {
    Status.UNTRANSLATED: "Не переведено",
    Status.AUTO: "Авто (из памяти)",
    Status.TRANSLATED: "Переведено",
    Status.REVIEWED: "Проверено",
    Status.STALE: "Устарело",
    Status.IGNORED: "Игнорировано",
    Status.CUSTOM: "Кастомный",
}
