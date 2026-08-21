"""Machine translation on a thread of its own.

A module rather than a method of the dialog, for two reasons. First:
`moveToThread` must not appear in `prefs_dialog.py` — it has no business there,
and `tests/test_threads.py` checks exactly where it lives. Second: the worker is
needed by two callers — «Preferences», to check a key, and the batch translation
dialog.

Rules paid for with two freezes (see `tests/test_threads.py`):

* the worker's signals are connected **to bound methods only**. A lambda outlives
  the widget and reaches into an already deleted C++ object;
* never call `wait()` from the interface thread — the thread stops itself, on its
  own signal;
* the worker opens a database connection **of its own, inside `run`**: attached
  databases and temporary views live within a connection.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from pdxloc.core import mt, mt_run, unit_ops
from pdxloc.core.mt_providers import ProviderConfig


class MtWorker(QObject):
    """The translation run: reads rows, writes results, reports progress.

    **There is deliberately no `cancelled` signal here**, although the
    neighbouring workers have one (`scan_dialog.ScanWorker`,
    `tm_build_tab._BuildWorker`). For those, cancelling is terminal: an
    interrupted scan and a half-built database give nothing worth reporting, and
    `cancelled` arrives **instead of** `finished`.

    Here it is the other way round. The rows that were translated before the
    cancellation are already written to the database, and the person must see the
    summary for them — so cancelling is not a state of the run but a property of
    its result, and it lives in `report.cancelled`. A separate signal cannot say
    that: it would be emitted **together with** `finished`, and a subscriber
    would have to guess which of the two is the main one.
    """

    progress = Signal(int, int, str)
    finished = Signal(object)      # MtReport; cancellation is the report.cancelled field
    failed = Signal(str)

    def __init__(
        self,
        project_path: Path,
        rows: list[mt_run.MtRow],
        provider_name: str,
        config: ProviderConfig,
        src_locale: str,
        tgt_locale: str,
        batch_id: str,
        *,
        budget: int = 4500,
        throttle_ms: int = 250,
        retries: int = 3,
    ):
        super().__init__()
        self.project_path = project_path
        self.rows = rows
        self.provider_name = provider_name
        self.config = config
        self.src_locale = src_locale
        self.tgt_locale = tgt_locale
        self.batch_id = batch_id
        self.budget = budget
        self.throttle_ms = throttle_ms
        self.retries = retries
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            from pdxloc.project import open_project

            conn = open_project(self.project_path, [])
            try:
                provider = mt.get_provider(self.provider_name, self.config)

                def write(row: mt_run.MtRow, text: str) -> None:
                    unit_ops.save_machine_text(
                        conn, row.unit_id, text, batch_id=self.batch_id)

                report = mt_run.run(
                    provider, self.rows, self.src_locale, self.tgt_locale,
                    write=write, budget=self.budget,
                    throttle_ms=self.throttle_ms, retries=self.retries,
                    progress_cb=self.progress.emit,
                    should_cancel=lambda: self._cancel)
            finally:
                conn.close()
            self.finished.emit(report)
        except Exception as e:  # noqa: BLE001 — every error is shown to the user
            self.failed.emit(str(e))


class RowWorker(QObject):
    """Translating a single row: the network only, no database at all.

    The batch worker opens a connection of its own because it writes thousands of
    rows as it goes. Here there is nothing to write until the very end, and the
    slow part is the request alone; so the result is handed over by a signal and
    written by whoever already holds a connection. That way neither a path to the
    project nor a second connection is needed for one row.
    """

    finished = Signal(int, str, list)   # unit_id, the translation, the lost placeholders
    failed = Signal(str)

    def __init__(self, unit_id: int, text: str, provider_name: str,
                 config: ProviderConfig, src_locale: str, tgt_locale: str):
        super().__init__()
        self.unit_id = unit_id
        self.text = text
        self.provider_name = provider_name
        self.config = config
        self.src_locale = src_locale
        self.tgt_locale = tgt_locale

    def run(self) -> None:
        from pdxloc.core.mt_errors import MtError

        try:
            provider = mt.get_provider(self.provider_name, self.config)
            result = mt.translate_texts(
                provider, [self.text], self.src_locale, self.tgt_locale)
        except MtError as error:
            self.failed.emit(error.message)
            return
        except Exception as error:  # noqa: BLE001
            self.failed.emit(str(error))
            return
        translated, lost = result[0]
        self.finished.emit(self.unit_id, translated, lost)


class KeyCheckWorker(QObject):
    """One cheap request: does the service accept the key.

    The check blocks nothing and governs nothing: a stored «the key is good» mark
    is a hint, not a pass. A key expires in silence, and a tool that refused to
    work on the strength of its own week-old note would lie worse than a plain
    error from the service.
    """

    finished = Signal(bool, str)   # success, message

    def __init__(self, provider_name: str, config: ProviderConfig,
                 src_locale: str, tgt_locale: str):
        super().__init__()
        self.provider_name = provider_name
        self.config = config
        self.src_locale = src_locale
        self.tgt_locale = tgt_locale

    def run(self) -> None:
        from pdxloc.core.i18n import translate
        from pdxloc.core.mt_errors import MtError

        try:
            provider = mt.get_provider(self.provider_name, self.config)
            provider.translate_batch(["Hello"], self.src_locale, self.tgt_locale)
        except MtError as error:
            self.finished.emit(False, error.message)
            return
        except Exception as error:  # noqa: BLE001
            self.finished.emit(False, str(error))
            return
        self.finished.emit(True, translate("Prefs", "The key works."))


def config_from_prefs(provider_name: str) -> ProviderConfig:
    """Gather the provider settings in one place.

    The interface gathers them, not the provider: the core must import without
    Qt, and `prefs` is already Qt. The single point exists so that a single row
    and a batch run do not disagree about the settings they work under.
    """
    from pdxloc.core import mt
    from pdxloc.gui import prefs

    return ProviderConfig(
        api_key=mt.api_key(provider_name),
        pro=prefs.get("mt/deepl_pro"),
        model=prefs.get("mt/llm_model"),
        prompt=prefs.get("mt/llm_prompt"),
        extra={"folder_id": prefs.get("mt/yandex_folder")},
        timeout=float(prefs.get("mt/timeout_sec")),
    )


def start(worker: QObject, parent: QObject) -> QThread:
    """Set a thread up for a worker and start it.

    Returns the thread: the caller must keep the reference, or Qt collects it in
    the middle of the work. There is no need to stop it — the thread puts itself
    out on the worker's signals, connected by the caller.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    return thread
