"""Выбор баз памяти переводов, подключённых к проекту."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

from ck3loc import project, settings
from ck3loc.core import tm_import


class TmSourcesDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Базы памяти переводов")
        self.setMinimumSize(680, 420)

        proj = conn.execute("SELECT src_lang, tgt_lang FROM projects WHERE id = 1").fetchone()
        self.src_lang = proj["src_lang"] if proj else "english"
        self.tgt_lang = proj["tgt_lang"] if proj else "russian"

        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Отмеченные базы используются для подсказок и автозаполнения "
            f"перевода ({self.src_lang} → {self.tgt_lang}).\n"
            f"Папка: {settings.bdd_dir()}")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        refresh = QPushButton("Обновить список")
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        self.index_btn = QPushButton("Построить индекс похожих строк")
        self.index_btn.setToolTip(
            "Без индекса база отвечает только на точные совпадения.\n"
            "Постройка занимает секунды и добавляет к файлу базы около 20% объёма.")
        self.index_btn.clicked.connect(self._build_index)
        row.addWidget(self.index_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.empty_hint = QLabel(
            "Баз пока нет. Создайте базу из папок локализации: "
            "меню «Инструменты → Создать базу переводов из папок…»")
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet("color: #555;")
        layout.addWidget(self.empty_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.reload()

    def reload(self) -> None:
        self.list.clear()
        enabled = set(project.get_tm_sources(self.conn))
        databases = project.list_tm_databases()
        for path, meta in databases:
            kind = project.KIND_LABELS.get(meta.get("kind", "import"), meta.get("kind", "—"))
            src, tgt = meta.get("src_lang", "?"), meta.get("tgt_lang", "?")
            try:
                indexed = int(meta.get("schema_version", 1) or 1) >= 2
            except ValueError:
                indexed = False
            item = QListWidgetItem(
                f"{meta.get('name') or path.stem}  ·  {src} → {tgt}  ·  {kind}  ·  "
                f"{meta.get('entries', '0')} записей  ·  "
                f"{'с индексом похожих' if indexed else 'без индекса похожих'}"
                f"\n{path.name}")
            item.setData(Qt.UserRole, path.name)
            same_langs = (src == self.src_lang and tgt == self.tgt_lang)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if path.name in enabled else Qt.Unchecked)
            if not same_langs:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                item.setToolTip("Языки базы не совпадают с языками проекта")
            self.list.addItem(item)
        # включённые, но пропавшие с диска
        known = {p.name for p, _ in databases}
        for name in sorted(enabled - known):
            item = QListWidgetItem(f"{name}\n(файл не найден в папке Bdd)")
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list.addItem(item)
        self.empty_hint.setVisible(self.list.count() == 0)

    def _build_index(self) -> None:
        """Достроить индекс похожих строк в выбранной базе.

        Базы подключены к проекту только на чтение, поэтому индекс строится
        отдельным соединением и только по явной команде.
        """
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Индекс", "Выберите базу в списке.")
            return
        path = settings.bdd_dir() / item.data(Qt.UserRole)
        if not path.is_file():
            QMessageBox.warning(self, "Индекс", f"Файл базы не найден:\n{path}")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            count = tm_import.build_fts_index(path)
        except (sqlite3.Error, RuntimeError, OSError) as e:
            QMessageBox.critical(self, "Индекс", f"Не удалось построить индекс:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.reload()
        QMessageBox.information(
            self, "Индекс",
            f"Индекс построен: {count} записей.\n\n"
            f"Теперь база подсказывает не только точные совпадения, "
            f"но и похожие строки.")

    def _save(self) -> None:
        names = [
            self.list.item(i).data(Qt.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.Checked
        ]
        project.set_tm_sources(self.conn, names)
        project.attach_tm_sources(self.conn, project.project_tm_paths(self.conn))
        self.accept()
