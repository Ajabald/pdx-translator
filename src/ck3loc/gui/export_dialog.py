"""Запись перевода в файлы мода.

Папка вывода живёт в проекте отдельно от `ru_root`: та — источник импорта, и
писать по умолчанию поверх неё значит затирать дерево, из которого читали.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QVBoxLayout,
)

from ck3loc import project as project_mod
from ck3loc.core.exporter import TRANSLATED_STATUSES, export_project
from ck3loc.core.models import ExportOptions


class ExportDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, project_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.setWindowTitle("Запись перевода в файлы мода")
        self.setMinimumWidth(600)

        proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        layout = QVBoxLayout(self)

        counts = conn.execute(
            f"""SELECT SUM(status IN ({','.join('?' * len(TRANSLATED_STATUSES))})
                           AND ru_text IS NOT NULL) AS exportable,
                       SUM(status = 'ignored') AS ignored
                FROM units u JOIN files f ON f.id = u.file_id
                WHERE f.project_id = ? AND u.is_deleted = 0""",
            (*TRANSLATED_STATUSES, project_id),
        ).fetchone()
        from ck3loc.core.stats import project_stats
        stats = project_stats(conn, project_id)
        total = stats.total
        translated = counts["exportable"] or 0

        note = f" · игнорировано: {counts['ignored']}" if counts["ignored"] else ""
        summary = QLabel(
            f"Всего строк: {total}, в мод пойдёт: {translated}, "
            f"без перевода: {total - translated}{note}")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.radio_translated = QRadioButton(
            f"Только переведённые ({translated} строк)")
        self.radio_all = QRadioButton(
            f"Все строки — без перевода останутся на английском ({total} строк)")
        self.radio_translated.setChecked(True)
        layout.addWidget(self.radio_translated)
        layout.addWidget(self.radio_all)

        self.stale_check = QCheckBox("Включать устаревшие переводы (EN изменился)")
        self.stale_check.setChecked(True)
        layout.addWidget(self.stale_check)

        self.backup_check = QCheckBox("Резервная копия перезаписываемых файлов")
        self.backup_check.setChecked(True)
        self.backup_check.setToolTip(
            "Прежние версии складываются в папку backups — вне дерева локализации, "
            "иначе игра прочитает копии наравне с настоящими файлами")
        layout.addWidget(self.backup_check)

        self.ru_root = proj["ru_root"]
        row = QHBoxLayout()
        row.addWidget(QLabel("Папка мода:"))
        self.path_edit = QLineEdit(project_mod.get_export_root(conn) or self.ru_root)
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("Обзор…")
        browse.setToolTip("Выбрать папку — например, папку мода в Documents")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        keys = proj.keys()
        self.src_lang = proj["src_lang"] if "src_lang" in keys else "english"
        self.tgt_lang = proj["tgt_lang"] if "tgt_lang" in keys else "russian"
        self.path_edit.textChanged.connect(self._update_preview)
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("color: #555;")
        layout.addWidget(self.preview)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #a04000;")
        layout.addWidget(self.warning)
        self._update_preview()

        last = project_mod.get_last_export_at(conn)
        if last:
            stamp = QLabel(f"Последняя запись: {last}")
            stamp.setStyleSheet("color: #555;")
            layout.addWidget(stamp)

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.hide()
        layout.addWidget(self.report_box, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.buttons.button(QDialogButtonBox.Ok).setText("Записать")
        self.buttons.accepted.connect(self._run)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Папка мода", self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def _update_preview(self) -> None:
        """Показать, как будет назван файл и что окажется в заголовке."""
        row = self.conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
            "ORDER BY rel_path LIMIT 1", (self.project_id,)).fetchone()
        text = self.path_edit.text().strip()
        root = Path(text or ".")
        if row:
            from ck3loc.core.scanner import map_relpath
            sample = map_relpath(row["rel_path"], self.src_lang, self.tgt_lang)
            self.preview.setText(
                f"Пишутся файлы *_l_{self.tgt_lang}.yml для игры, например:\n"
                f"{root / sample}\nВ начале файла: l_{self.tgt_lang}:")
        else:
            self.preview.setText(f"В начале файлов: l_{self.tgt_lang}:")
        same = bool(text) and Path(text) == Path(self.ru_root)
        self.warning.setText(
            "Это папка, из которой импортирован перевод: её файлы будут "
            "перезаписаны содержимым проекта." if same else "")
        self.warning.setVisible(same)

    def _existing_targets(self, root: Path) -> list[str]:
        """Какие файлы экспорта уже лежат в папке назначения.

        Проверяем ровно те пути, которые собираемся писать (их десятки), а не
        обходим дерево рекурсивно: папкой назначения бывает мод в Documents или
        каталог игры, и rglob по ним подвешивал окно на секунды — а на
        недопечатанном пути вроде «C:\\» и вовсе на минуты.
        """
        from ck3loc.core.scanner import map_relpath

        rows = self.conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0",
            (self.project_id,)).fetchall()
        return [rel for rel in
                (map_relpath(r["rel_path"], self.src_lang, self.tgt_lang) for r in rows)
                if (root / rel).is_file()]

    def _run(self) -> None:
        options = ExportOptions(
            mode="translated_only" if self.radio_translated.isChecked() else "all_fallback_en",
            include_stale=self.stale_check.isChecked(),
        )
        text = self.path_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "Запись перевода", "Укажите папку мода.")
            return
        out_root = Path(text)
        existing = self._existing_targets(out_root)
        if existing:
            backup = ("Прежние версии сохранятся в папке backups."
                      if self.backup_check.isChecked()
                      else "Резервная копия отключена — вернуть прежние версии будет нечем.")
            answer = QMessageBox.question(
                self, "Запись перевода",
                f"В папке уже есть {len(existing)} файлов перевода — они будут "
                f"перезаписаны содержимым проекта.\n\n"
                f"Источник истины — проект: строки, которых в нём нет, из файлов исчезнут.\n"
                f"{backup}\n\n"
                f"Продолжить?")
            if answer != QMessageBox.Yes:
                return
        self.buttons.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = export_project(self.conn, self.project_id, options,
                                    out_root=out_root,
                                    backup=self.backup_check.isChecked())
        except OSError as e:
            QMessageBox.critical(self, "Запись перевода", f"Ошибка записи:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.buttons.setEnabled(True)

        project_mod.set_export_root(self.conn, out_root)
        project_mod.set_last_export_at(self.conn)
        lines = [
            f"Файлов записано: {report.files_written}",
            f"Файлов без изменений: {report.files_unchanged}",
            f"Строк записано: {report.keys_written}",
            f"Пропущено (нет перевода): {report.keys_skipped}",
        ]
        if report.keys_fallback_en:
            lines.append(f"Оставлено на английском: {report.keys_fallback_en}")
        if report.backup_dir:
            lines.append(f"Прежние версии: {report.backup_dir}")
        lines.append("")
        lines += [f"  {rel}: {w} строк" + (f" (пропущено {s})" if s else "")
                  for rel, w, s in report.per_file]
        self.report_box.setPlainText("\n".join(lines))
        self.report_box.show()
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
