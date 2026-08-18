"""Статусы переводимых строк: значения в БД и названия для показа.

Цвета живут в gui/theme.py — их два набора (светлый и тёмный), и ядру,
которое работает без интерфейса, они не нужны.

Названия помечены `QT_TRANSLATE_NOOP`, а не переведены на месте: таблица
вычисляется на импорте, когда переводчик ещё не установлен. Переводит их
`label()` в момент показа — через неё и надо ходить, а не через словарь.
"""
from __future__ import annotations

from enum import StrEnum

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate

CTX = "Statuses"


class Status(StrEnum):
    UNTRANSLATED = "untranslated"
    MACHINE = "machine"          # машинный перевод, не проверен человеком
    AUTO = "auto"                # подставлено из памяти переводов, требует проверки
    TRANSLATED = "translated"
    REVIEWED = "reviewed"
    STALE = "stale"              # EN изменился после перевода
    IGNORED = "ignored"          # перевод не нужен (например, строка из одних тегов)
    CUSTOM = "custom"            # пользовательская пометка (аналог статуса 150 в EET)


STATUS_LABELS: dict[Status, str] = {
    Status.UNTRANSLATED: QT_TRANSLATE_NOOP("Statuses", "Not translated"),
    # «не проверен» в подписи обязательно: «Машинный» в одиночку читается как
    # законченное состояние, а это ровно то, чем машинный перевод не является
    Status.MACHINE: QT_TRANSLATE_NOOP("Statuses", "Machine (unchecked)"),
    Status.AUTO: QT_TRANSLATE_NOOP("Statuses", "Auto (from memory)"),
    Status.TRANSLATED: QT_TRANSLATE_NOOP("Statuses", "Translated"),
    Status.REVIEWED: QT_TRANSLATE_NOOP("Statuses", "Reviewed"),
    Status.STALE: QT_TRANSLATE_NOOP("Statuses", "Outdated"),
    Status.IGNORED: QT_TRANSLATE_NOOP("Statuses", "Ignored"),
    Status.CUSTOM: QT_TRANSLATE_NOOP("Statuses", "Custom"),
}


def label(status: Status | str) -> str:
    """Название статуса на текущем языке интерфейса."""
    try:
        key = Status(status)
    except ValueError:
        return str(status)
    return translate("Statuses", STATUS_LABELS[key])

# Порядок работы переводчика, а не алфавит значений: по нему идут чипы в
# статус-баре, пункты фильтра и сортировка колонки «Статус». Список один на
# всё приложение — иначе три места разъезжаются при добавлении статуса.
#
# «Машинный» стоит перед «Авто» намеренно: подстановка из памяти — это точное
# совпадение с переводом, который кто-то однажды сделал руками, а машинный
# перевод не видел человек вообще. Порядок рабочий, и наименее достоверное
# идёт первым.
STATUS_ORDER: tuple[Status, ...] = (
    Status.UNTRANSLATED, Status.MACHINE, Status.AUTO, Status.TRANSLATED,
    Status.REVIEWED, Status.STALE, Status.CUSTOM, Status.IGNORED,
)

STATUS_RANK: dict[str, int] = {s.value: i for i, s in enumerate(STATUS_ORDER)}
