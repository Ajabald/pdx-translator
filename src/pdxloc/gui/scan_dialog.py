"""Сканирование проекта: прогресс с возможностью прервать и наглядная сводка.

ScanWorker открывает СВОЁ соединение с БД — соединения sqlite нельзя делить
между потоками.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.models import ScanStats
from pdxloc.core.statuses import Status


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)      # ScanStats
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project_path: Path, tm_paths: list[Path] | None = None):
        super().__init__()
        self.project_path = project_path
        self.tm_paths = tm_paths or []
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            from pdxloc.core.scanner import ScanCancelled, scan_project
            from pdxloc.project import open_project

            # своё соединение: подключённые базы и temp-представления живут
            # в пределах соединения и не переносятся между потоками
            conn = open_project(self.project_path, self.tm_paths)
            try:
                stats = scan_project(conn, 1, self.progress.emit, lambda: self._cancel)
            except ScanCancelled:
                conn.rollback()
                self.cancelled.emit()
                return
            finally:
                conn.close()
            self.finished.emit(stats)
        except Exception as e:  # noqa: BLE001 — показываем пользователю любую ошибку
            self.failed.emit(str(e))


class ScanProgressDialog(QDialog):
    """Модальный прогресс; сам запускает поток и закрывается по завершении."""

    def __init__(self, project_path: Path, tm_paths: list[Path] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("ScanDialog", "Scanning…"))
        self.setModal(True)
        self.setMinimumSize(560, 320)
        self.stats: ScanStats | None = None
        self.error: str | None = None
        self.was_cancelled = False

        layout = QVBoxLayout(self)
        self._label = QLabel(translate("ScanDialog", "Preparing…"))
        self._bar = QProgressBar()
        layout.addWidget(self._label)
        layout.addWidget(self._bar)

        layout.addWidget(QLabel(translate("ScanDialog", "Processed files:")))
        self._files = QListWidget()
        layout.addWidget(self._files, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._cancel_btn = QPushButton(translate("ScanDialog", "Interrupt"))
        self._cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self._cancel_btn)
        layout.addLayout(buttons)

        self._thread = QThread(self)
        self._worker = ScanWorker(project_path, tm_paths)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        # Останавливаем поток его же сигналом: сообщение о завершении приходит
        # раньше, чем run() отдаёт управление, и wait() из основного потока
        # вешал окно намертво.
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.start()

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self._bar.setMaximum(max(total, 1))
        self._bar.setValue(done)
        self._label.setText(fill(translate("ScanDialog", "File %1 of %2: %3"),
                                 done + 1, total, name))
        if name and name != "done":   # маркер сканера, не подпись
            self._files.addItem(name)
            self._files.scrollToBottom()

    def _on_cancel(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._label.setText(translate(
            "ScanDialog", "Interrupting — rolling back changes…"))
        self._worker.cancel()

    def _on_finished(self, stats: ScanStats) -> None:
        self.stats = stats
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.error = message
        self.reject()

    def _on_cancelled(self) -> None:
        self.was_cancelled = True
        self.reject()

    def closeEvent(self, event) -> None:
        if self._thread.isRunning() and not self._worker._cancel:
            self._on_cancel()      # закрытие окна = просьба прервать
            event.ignore()
            return
        # даём потоку договорить, но не виснем, если он застрял
        self._thread.quit()
        self._thread.wait(3000)
        super().closeEvent(event)


class ScanSummaryDialog(QDialog):
    """Итоги сканирования: что изменилось и как это посмотреть."""

    # (подпись, значение из ScanStats, статус для фильтра)
    ROWS = (
        (QT_TRANSLATE_NOOP("ScanDialog", "New rows"),
         "new", Status.UNTRANSLATED.value),
        (QT_TRANSLATE_NOOP("ScanDialog", "The original changed in meaning"),
         "changed_meaningful", Status.STALE.value),
        (QT_TRANSLATE_NOOP("ScanDialog", "The original was edited cosmetically"),
         "changed_cosmetic", Status.STALE.value),
        (QT_TRANSLATE_NOOP("ScanDialog", "Filled from translation memory"),
         "auto_filled", Status.AUTO.value),
        (QT_TRANSLATE_NOOP("ScanDialog", "Ignored (nothing to translate)"),
         "auto_ignored", Status.IGNORED.value),
        (QT_TRANSLATE_NOOP("ScanDialog", "Deleted from the original"),
         "deleted", None),
        (QT_TRANSLATE_NOOP("ScanDialog", "Moved to the archive"), "archived", None),
        (QT_TRANSLATE_NOOP("ScanDialog", "Unchanged"), "unchanged", None),
    )

    showRequested = Signal(str)     # статус для фильтра

    def __init__(self, stats: ScanStats, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("ScanDialog", "Scan results"))
        self.setMinimumSize(640, 460)
        self.stats = stats

        layout = QVBoxLayout(self)
        header = QLabel(fill(translate("ScanDialog",
                           "Original files: %1 · translation files: %2"),
                 stats.files_en, stats.files_ru))
        layout.addWidget(header)

        rows = [(translate("ScanDialog", label), getattr(stats, field, 0), status)
                for label, field, status in self.ROWS]
        self.table = QTableWidget(len(rows), 3)
        self.table.setHorizontalHeaderLabels(
            (translate("ScanDialog", "What"),
             translate("ScanDialog", "How many"), ""))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i, (label, value, status) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 1, item)
            if value and status:
                button = QPushButton(translate("ScanDialog", "Show"))
                button.clicked.connect(
                    lambda _, s=status: (self.showRequested.emit(s), self.accept()))
                self.table.setCellWidget(i, 2, button)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        details = self._details_text(stats)
        if details:
            self.details_btn = QPushButton(fill(translate("ScanDialog", "Show details (%1)"), len(details)))
            self.details_btn.setCheckable(True)
            self.details_btn.toggled.connect(self._toggle_details)
            layout.addWidget(self.details_btn)
            self.details = QListWidget()
            self.details.addItems(details)
            self.details.hide()
            layout.addWidget(self.details, 1)

        box = QDialogButtonBox(QDialogButtonBox.Ok)
        box.accepted.connect(self.accept)
        layout.addWidget(box, 0, Qt.AlignRight)

    @staticmethod
    def _details_text(stats: ScanStats) -> list[str]:
        lines: list[str] = []
        if stats.ru_conflict_list:
            # сканер оставляет версию проекта; принять дисковую можно только
            # осознанно — через «Проект → Загрузить перевод из мода…»
            lines.append(translate(
                "ScanDialog",
                "The discrepancies below were left as they are: the project has "
                "its own version. To take the version from the files use "
                "«Project → Load translation from mod…» with the «Overwrite "
                "existing translations» checkbox."))
        for rel, key, db_ru, disk_ru in stats.ru_conflict_list:
            lines.append(fill(translate(
                "ScanDialog", "Discrepancy with the file · %1: %2"), rel, key))
            lines.append(fill(translate(
                "ScanDialog", "      in project: %1"), db_ru[:120]))
            lines.append(fill(translate(
                "ScanDialog", "      in file:    %1"), disk_ru[:120]))
        lines += [fill(translate("ScanDialog", "Duplicate key (original) · %1"), d)
                  for d in stats.duplicate_keys]
        lines += [fill(translate("ScanDialog", "Duplicate key (translation) · %1"), d)
                  for d in stats.duplicate_keys_ru]
        lines += [fill(translate("ScanDialog", "Empty original · %1"), k)
                  for k in stats.empty_source_keys]
        lines += [fill(translate(
            "ScanDialog", "Translation file without a pair · %1"), f)
            for f in stats.orphan_ru_files]
        lines += [fill(translate("ScanDialog", "Parser · %1"), w) for w in stats.parse_warnings]
        return lines

    def _toggle_details(self, shown: bool) -> None:
        self.details.setVisible(shown)
        self.details_btn.setText(
            translate("ScanDialog", "Hide details") if shown else
            fill(translate("ScanDialog", "Show details (%1)"), self.details.count()))
