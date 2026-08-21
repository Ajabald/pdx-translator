"""A machine translation run: batches, waiting, the report.

The split from `core/mt.py` is simple: markup shielding and the registry live
there, and everything about **a run over many rows** lives here — how to divide
them, what to do about a refusal and what to show at the end.

Three decisions, each bought with somebody else's experience:

* **batches are measured in characters, not in rows.** Services limit the size of
  a request, while the length of a localisation row wanders from `Yes` to a whole
  paragraph;
* **waiting between requests is mandatory.** ModTranslationHelper fires a request
  about every 150 ms and runs into the limits — hence its own message about an
  exhausted quota. A quarter of a second by default is cheaper than working out
  why half a run failed;
* **a batch that could not be parsed is not applied at all.** A translation that
  landed on somebody else's key is the worst thing that can happen here: it looks
  like work and is found weeks later.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pdxloc.core import mt
from pdxloc.core.i18n import fill, translate
from pdxloc.core.mt_errors import MtCancelled, MtError, MtQuotaError
from pdxloc.core.progress import ProgressCb, throttled

# The most rows in one request, even when more would fit by characters. The
# limit is not technical but a matter of legibility: less is lost on a refusal,
# and the progress does not leap fifty rows at a time.
MAX_ROWS_PER_BATCH = 50

# We will not wait longer than a minute on somebody else's request: a person is
# looking at the window.
MAX_RETRY_WAIT_SEC = 60.0

# The wait is cut into slices this size so that «Interrupt» answers during a
# pause as well.
_SLEEP_SLICE_SEC = 0.2


@dataclass
class MtRow:
    """A row handed over for translation. `unit_id` and `key` are for the report only."""

    unit_id: int
    key: str
    text: str


@dataclass
class MtReport:
    """The outcome of a run: shown in the summary and answering «what went wrong»."""

    rows_sent: int = 0
    rows_translated: int = 0
    rows_failed: int = 0
    characters: int = 0
    requests: int = 0
    seconds: float = 0.0
    cancelled: bool = False
    # rows where the translation lost a substitution: written, but broken
    placeholders_lost: list[tuple[int, str, list[str]]] = field(default_factory=list)
    # rows that could not be translated at all, with the reason
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
    """Lay the rows out into requests. Returns (batches of indices, oversized ones).

    Indices rather than texts: identical originals are an everyday matter in a
    project, and matching the result by text would mix them up.

    A row that does not fit the provider's hard limit is **not cut**: truncation
    would look like success while losing half the meaning. Such a row comes back
    in a list of its own, and the run marks it a failure.
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
    """Wait without going deaf to «Interrupt».

    The wait is counted **by adding up the slices** rather than by the clock: that
    way a `time.sleep` replaced in the tests makes the pause instant. Were there a
    loop on `monotonic` here, the suite would wait out the backoff for real — and
    people would stop running it.
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
    """One request, with retries on an exhausted quota.

    Only a quota is retried: a wrong key and an unreadable answer will not be
    cured by a retry, and would spend the time anyway.
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
    """Translate the rows and write the result through `write`.

    Writing is handed outwards deliberately: the core knows nothing about the undo
    batch or the statuses — the caller governs those, and it is also the caller's
    business to decide what to do about a row that lost a substitution.

    Interrupting does not roll back what is already written: everything written
    lies in one batch and comes back with one Ctrl+Z. `MtReport.summary` says so
    as well.
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
                # The batch is not applied at all: there is nothing to parse it with, and
                # guessing which row is which is a way to land a translation on the wrong key.
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
                    # The provider said honestly that it could not manage this row. Writing the
                    # original in the guise of a translation is not allowed: it would look like
                    # work and would travel into the mod.
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
