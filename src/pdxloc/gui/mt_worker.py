"""Машинный перевод в отдельном потоке.

Отдельный модуль, а не метод диалога, по двум причинам. Первая: `moveToThread`
не должен появиться в `prefs_dialog.py` — там ему не место, и тест
`tests/test_threads.py` проверяет именно расположение. Вторая: воркер нужен
двоим — «Параметрам» (проверить ключ) и диалогу пакетного перевода.

Правила, купленные двумя зависаниями (см. `tests/test_threads.py`):

* сигналы воркера подключаются **только к связанным методам**. Лямбда живёт
  дольше виджета и обращается к уже удалённому C++ объекту;
* `wait()` из потока интерфейса не звать никогда — поток останавливает себя
  сам, по своему же сигналу;
* соединение с базой воркер открывает **своё, внутри `run`**: подключённые
  базы и временные представления живут в пределах соединения.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from pdxloc.core import mt, mt_run, unit_ops
from pdxloc.core.mt_providers import ProviderConfig


class MtWorker(QObject):
    """Прогон перевода: читает строки, пишет результат, докладывает о ходе."""

    progress = Signal(int, int, str)
    finished = Signal(object)      # MtReport
    failed = Signal(str)
    cancelled = Signal()

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
            if report.cancelled:
                self.cancelled.emit()
            self.finished.emit(report)
        except Exception as e:  # noqa: BLE001 — показываем пользователю любую ошибку
            self.failed.emit(str(e))


class RowWorker(QObject):
    """Перевод одной строки: только сеть, базы не касается.

    Пакетный воркер открывает своё соединение, потому что пишет тысячи строк по
    ходу дела. Здесь писать нечего до самого конца, а медленная часть — только
    запрос; поэтому результат отдаётся сигналом, и записывает его тот, у кого
    соединение уже есть. Так не нужен ни путь к проекту, ни второе соединение
    ради одной строки.
    """

    finished = Signal(int, str, list)   # unit_id, перевод, потерянные метки
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
    """Один дешёвый запрос: принимает ли сервис ключ.

    Проверка ничего не блокирует и ничем не распоряжается: сохранённая отметка
    «ключ верен» — это подсказка, а не пропуск. Ключ протухает молча, и
    инструмент, отказавшийся работать по своей записи недельной давности,
    врал бы хуже, чем просто ошибка от сервиса.
    """

    finished = Signal(bool, str)   # успех, сообщение

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
    """Собрать настройки провайдера в одном месте.

    Собирает интерфейс, а не сам провайдер: ядро обязано импортироваться без
    Qt, а `prefs` — это уже Qt. Единая точка нужна затем, чтобы одна строка и
    пакетный прогон не разошлись в том, с какими настройками они работают.
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
    """Завести поток под воркера и запустить.

    Возвращает поток: держать ссылку обязан вызывающий, иначе Qt соберёт его
    посреди работы. Останавливать не надо — поток гасит себя сам, по сигналам
    воркера, подключённым вызывающим.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    return thread
