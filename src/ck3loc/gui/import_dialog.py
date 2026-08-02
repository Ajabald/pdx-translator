"""Загрузка перевода из готового дерева локализации.

Предпросмотр обязателен: операция меняет тысячи строк разом, и до нажатия
кнопки должно быть видно, сколько именно строк и что в них станет. Записанное
уходит одной пачкой и снимается одним Ctrl+Z.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ck3loc.core import unit_ops
from ck3loc.core.loc_import import ImportOptions, import_translations


class ImportDialog(QDialog):
    imported = Signal()      # строки изменились — обновить таблицу и счётчики

    def __init__(self, conn: sqlite3.Connection, project_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.setWindowTitle("Загрузить перевод из мода")
        self.setMinimumWidth(640)

        proj = conn.execute(
            "SELECT ru_root, tgt_lang FROM projects WHERE id = ?", (project_id,)).fetchone()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        intro = QLabel(
            "Принять переводы из папки с готовыми файлами локализации — например, "
            "из чужого перевода этого мода или из своих правок, сделанных прямо в файлах.")
        intro.setWordWrap(True)      # иначе окно растягивается на всю ширину экрана
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel("Папка перевода:"))
        self.path_edit = QLineEdit(proj["ru_root"])
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        self.overwrite = QCheckBox("Перезаписывать существующие переводы")
        self.overwrite.setToolTip(
            "Выключено — принимаются только строки, у которых перевода ещё нет")
        layout.addWidget(self.overwrite)
        self.skip_equal = QCheckBox("Не принимать строки, где перевод совпадает с оригиналом")
        self.skip_equal.setChecked(True)
        layout.addWidget(self.skip_equal)

        for w in (self.overwrite, self.skip_equal):
            w.toggled.connect(self._preview)
        self.path_edit.editingFinished.connect(self._preview)

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Принять переводы")
        self.buttons.accepted.connect(self._run)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._preview()

    # --- служебное ---

    def _options(self) -> ImportOptions:
        return ImportOptions(overwrite=self.overwrite.isChecked(),
                             skip_equal_to_source=self.skip_equal.isChecked())

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Папка перевода", self.path_edit.text())
        if path:
            self.path_edit.setText(path)
            self._preview()

    def _report(self, dry_run: bool, batch_id: str | None = None):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return import_translations(
                self.conn, self.project_id, Path(self.path_edit.text().strip() or "."),
                self._options(), dry_run=dry_run, batch_id=batch_id)
        finally:
            QApplication.restoreOverrideCursor()

    def _preview(self) -> None:
        try:
            report = self._report(dry_run=True)
        except (FileNotFoundError, OSError) as e:
            self.report_box.setPlainText(str(e))
            self.ok_button.setEnabled(False)
            return
        lines = [report.summary_ru()]
        if report.samples:
            lines += ["", "Что изменится (первые строки):"]
            lines += [f"  {key}: {(before or '(пусто)')[:60]} → {after[:60]}"
                      for key, before, after in report.samples[:20]]
        if report.warnings:
            lines += ["", f"Предупреждения парсера: {len(report.warnings)}"]
        self.report_box.setPlainText("\n".join(lines))
        self.ok_button.setEnabled(report.imported > 0)

    def _run(self) -> None:
        preview = self._report(dry_run=True)
        answer = QMessageBox.question(
            self, "Загрузка перевода",
            f"Принять {preview.imported} строк из выбранной папки?\n\n"
            f"Операция записывается одной пачкой — её можно отменить целиком "
            f"через «Проект → Отменить последнюю операцию» (Ctrl+Z).")
        if answer != QMessageBox.Yes:
            return
        batch = unit_ops.new_batch_id()
        try:
            report = self._report(dry_run=False, batch_id=batch)
        except OSError as e:
            QMessageBox.critical(self, "Загрузка перевода", f"Ошибка чтения:\n{e}")
            return
        self.report_box.setPlainText(
            report.summary_ru() + "\n\nГотово. Отменить целиком — Ctrl+Z.")
        self.ok_button.setEnabled(False)
        self.imported.emit()
