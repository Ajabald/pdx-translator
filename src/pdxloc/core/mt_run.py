"""Прогон машинного перевода: пачки, ожидание, отчёт.

Разделение с `core/mt.py` простое: там защита разметки и реестр, здесь всё, что
касается **прогона на много строк** — как их делить, что делать при отказе и что
показать в конце.

Три решения, каждое куплено чужим опытом:

* **пачки считаются по символам, а не по строкам.** У сервисов ограничение на
  объём запроса, а длина строк в локализации гуляет от `Yes` до абзаца;
* **ждать между запросами обязательно.** ModTranslationHelper шлёт запросы
  примерно раз в 150 мс и упирается в лимиты — отсюда и его сообщение про
  исчерпанный лимит. Четверть секунды по умолчанию стоит дешевле разбора,
  почему половина прогона не удалась;
* **пачка, которую не удалось разобрать, не применяется целиком.** Перевод,
  приземлившийся на чужой ключ, — худшее, что здесь может случиться: он
  выглядит как работа и находится через недели.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pdxloc.core import mt
from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_errors import MtCancelled, MtError, MtQuotaError
from pdxloc.core.progress import ProgressCb, throttled

# Сколько строк максимум в одном запросе, даже если по символам влезло больше.
# Ограничение не техническое, а на понятность: при отказе теряется меньше, а
# прогресс не скачет через полсотни строк.
MAX_ROWS_PER_BATCH = 50

# Ждать дольше минуты по чужой просьбе не станем: человек смотрит на окно.
MAX_RETRY_WAIT_SEC = 60.0

# Ожидание режется на такие куски, чтобы «Прервать» отвечал и во время паузы.
_SLEEP_SLICE_SEC = 0.2


@dataclass
class MtRow:
    """Строка, отданная на перевод. `unit_id` и `key` нужны только отчёту."""

    unit_id: int
    key: str
    text: str


@dataclass
class MtReport:
    """Итог прогона — показывается в сводке и отвечает на «что пошло не так»."""

    rows_sent: int = 0
    rows_translated: int = 0
    rows_failed: int = 0
    characters: int = 0
    requests: int = 0
    seconds: float = 0.0
    cancelled: bool = False
    # строки, где перевод потерял подстановку: записаны, но сломаны
    placeholders_lost: list[tuple[int, str, list[str]]] = field(default_factory=list)
    # строки, которые не удалось перевести вовсе, с причиной
    failures: list[tuple[int, str, str]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            fill(translate("MtRun", "Rows translated: %1"), self.rows_translated),
            fill(translate("MtRun", "Characters sent: %1"), self.characters),
            fill(translate("MtRun", "Requests made: %1"), self.requests),
        ]
        if self.placeholders_lost:
            lines.append(fill(
                translate("MtRun", "Rows where the translation lost a "
                                   "placeholder: %1 — they are written, but "
                                   "need fixing"),
                len(self.placeholders_lost)))
        if self.rows_failed:
            lines.append(fill(translate("MtRun", "Rows not translated: %1"),
                              self.rows_failed))
        if self.cancelled:
            lines.append(translate(
                "MtRun", "Interrupted. What had been translated by then is "
                         "kept — Ctrl+Z undoes the whole run."))
        return "\n".join(lines)


def plan_batches(
    texts: Sequence[str],
    budget: int,
    *,
    max_rows: int = MAX_ROWS_PER_BATCH,
    hard_limit: int | None = None,
) -> tuple[list[list[int]], list[int]]:
    """Разложить строки по запросам. Возвращает (пачки индексов, негабаритные).

    Индексы, а не тексты: одинаковые оригиналы в проекте — обычное дело, и
    сопоставлять результат по тексту значило бы их перепутать.

    Строка, не влезающая в жёсткий предел провайдера, **не режется**: обрезка
    выглядела бы как успех, а на деле теряла бы половину смысла. Такая строка
    возвращается отдельным списком, и прогон отметит её неудачей.
    """
    batches: list[list[int]] = []
    oversized: list[int] = []
    current: list[int] = []
    size = 0

    for index, text in enumerate(texts):
        length = len(text)
        if hard_limit is not None and length > hard_limit:
            oversized.append(index)
            continue
        if current and (size + length > budget or len(current) >= max_rows):
            batches.append(current)
            current, size = [], 0
        current.append(index)
        size += length

    if current:
        batches.append(current)
    return batches, oversized


def _wait(seconds: float, should_cancel: Callable[[], bool]) -> None:
    """Подождать, не переставая слышать «Прервать».

    Ожидание отсчитывается **сложением ломтей**, а не по часам: так подменённый
    в тестах `time.sleep` делает паузу мгновенной. Крутись здесь цикл по
    `monotonic`, набор ждал бы бэкофф по-настоящему — и его перестали бы гонять.
    """
    remaining = seconds
    while remaining > 0:
        if should_cancel():
            raise MtCancelled()
        slice_seconds = min(_SLEEP_SLICE_SEC, remaining)
        time.sleep(slice_seconds)
        remaining -= slice_seconds


def _translate_batch_with_retries(
    provider,
    texts: list[str],
    src_locale: str,
    tgt_locale: str,
    *,
    retries: int,
    should_cancel: Callable[[], bool],
) -> list[tuple[str, list[str]]]:
    """Один запрос с повторами по исчерпанной квоте.

    Повторяем только квоту: неверный ключ и нечитаемый ответ от повтора не
    исправятся, а время потратят.
    """
    attempt = 0
    while True:
        if should_cancel():
            raise MtCancelled()
        try:
            return mt.translate_texts(provider, texts, src_locale, tgt_locale)
        except MtQuotaError as error:
            attempt += 1
            if attempt > retries:
                raise
            pause = error.retry_after if error.retry_after else 2.0 ** (attempt - 1)
            _wait(min(pause, MAX_RETRY_WAIT_SEC), should_cancel)


def run(
    provider,
    rows: Sequence[MtRow],
    src_locale: str,
    tgt_locale: str,
    *,
    write: Callable[[MtRow, str], None],
    budget: int = 4500,
    throttle_ms: int = 250,
    retries: int = 3,
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> MtReport:
    """Перевести строки и записать результат через `write`.

    Запись отдана наружу намеренно: ядро не знает ни про пачку отката, ни про
    статусы — этим ведает вызывающая сторона, и её же дело решить, что делать
    со строкой, потерявшей подстановку.

    Прерывание не откатывает уже записанное: всё, что записано, лежит в одной
    пачке и снимается одним Ctrl+Z. Об этом говорит и `MtReport.summary`.
    """
    report = MtReport(rows_sent=len(rows))
    if not rows:
        return report

    cancelled = should_cancel or (lambda: False)
    report_progress = throttled(progress_cb)
    started = time.monotonic()

    hard_limit = getattr(provider, "char_limit", None)
    batches, oversized = plan_batches(
        [r.text for r in rows], budget, hard_limit=hard_limit)

    for index in oversized:
        row = rows[index]
        report.rows_failed += 1
        report.failures.append((row.unit_id, row.key, translate(
            "MtRun", "The row is longer than the service accepts in one "
                     "request. It was left untouched.")))

    done = 0
    total = len(rows)
    report_progress(0, total, "")
    try:
        for batch in batches:
            texts = [rows[i].text for i in batch]
            try:
                results = _translate_batch_with_retries(
                    provider, texts, src_locale, tgt_locale,
                    retries=retries, should_cancel=cancelled)
            except MtCancelled:
                raise
            except (MtError, RuntimeError) as error:
                # Пачку не применяем целиком: разобрать её нечем, а угадывать
                # соответствие строк — способ приземлить перевод на чужой ключ.
                message = getattr(error, "message", None) or str(error)
                for i in batch:
                    row = rows[i]
                    report.rows_failed += 1
                    report.failures.append((row.unit_id, row.key, message))
                done += len(batch)
                report_progress(done, total, rows[batch[-1]].key)
                continue

            report.requests += 1
            report.characters += sum(len(t) for t in texts)
            for i, (translated, lost) in zip(batch, results, strict=True):
                row = rows[i]
                if translated is None:
                    # Провайдер честно сказал, что эту строку не осилил.
                    # Записывать оригинал под видом перевода нельзя: он выглядел
                    # бы работой и уехал бы в мод.
                    report.rows_failed += 1
                    report.failures.append((row.unit_id, row.key, translate(
                        "MtRun", "The service returned nothing for this row.")))
                    continue
                write(row, translated)
                report.rows_translated += 1
                if lost:
                    report.placeholders_lost.append((row.unit_id, row.key, lost))
            done += len(batch)
            report_progress(done, total, rows[batch[-1]].key)

            if throttle_ms and batch is not batches[-1]:
                _wait(throttle_ms / 1000.0, cancelled)
    except MtCancelled:
        report.cancelled = True

    report.seconds = time.monotonic() - started
    report_progress(total, total, "done")
    return report
