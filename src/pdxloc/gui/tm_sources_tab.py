"""Вкладка «Базы»: какие базы памяти подключены к проекту.

Кнопок ОК/Отмена здесь нет: во вкладке они бессмысленны (закрывать нечего), а
семантика «изменил, но ещё не сохранил» только запутывала — в шапке окна те же
базы переключаются одним кликом и применяются сразу. Теперь так же и здесь.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from pdxloc import project, settings
from pdxloc.core import tm_import
from pdxloc.core import games
from pdxloc.core.i18n import fill, translate
from pdxloc.gui.widgets import HintLabel


class TmSourcesTab(QWidget):
    statusChanged = Signal(str)
    sourcesChanged = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._status = ""
        self._syncing = False

        # базы памяти сверяются по папке языка, а не по языку текста: в самой
        # базе записаны именно они (см. tm_import.create_tm_database)
        langs = project.languages(conn)
        self.src_lang, self.tgt_lang = langs.src_lang, langs.tgt_lang
        self.game = project.game(conn)

        layout = QVBoxLayout(self)
        intro = QLabel(fill(translate(
            "TmSources", "Checked databases provide suggestions and autofill "
                         "(%1 → %2). Changes apply immediately."),
            self.src_lang, self.tgt_lang))
        intro.setWordWrap(True)     # иначе подпись растягивает окно на весь экран
        layout.addWidget(intro)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        refresh = QPushButton(translate("TmSources", "Refresh the list"))
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        self.index_btn = QPushButton(translate("TmSources", "Build the similar-rows index"))
        self.index_btn.setToolTip(
            translate("TmSources",
                      "Without an index the database answers exact matches only.\n"
                      "Building takes seconds and adds about 20% to the file size."))
        self.index_btn.clicked.connect(self._build_index)
        row.addWidget(self.index_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.empty_hint = HintLabel(translate(
            "TmSources", "No databases yet. Build one from localization folders "
                         "on the «Build a database» tab."))
        layout.addWidget(self.empty_hint)

        self.reload()

    def shutdown(self) -> None:
        """Своих таймеров нет — метод есть ради единого протокола вкладок."""

    def status_text(self) -> str:
        return self._status

    # --- данные ---

    def reload(self) -> None:
        self._syncing = True
        try:
            self.list.clear()
            enabled = set(project.get_tm_sources(self.conn))
            databases = project.list_tm_databases(
                game=project.game(self.conn))
            for path, meta in databases:
                self.list.addItem(self._make_item(path, meta, enabled))
            # включённые, но пропавшие с диска
            known = {p.name for p, _ in databases}
            for name in sorted(enabled - known):
                missing = translate(
                    "TmSources", "(file not found in the Bdd folder)")
                item = QListWidgetItem(f"{name}\n{missing}")
                item.setData(Qt.UserRole, name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.list.addItem(item)
            self.empty_hint.setVisible(self.list.count() == 0)
        finally:
            self._syncing = False
        self._update_status()

    def _make_item(self, path, meta, enabled) -> QListWidgetItem:
        kind = project.KIND_LABELS.get(
            meta.get("kind", "import"), meta.get("kind", "—"))
        src, tgt = meta.get("src_lang", "?"), meta.get("tgt_lang", "?")
        try:
            indexed = int(meta.get("schema_version", 1) or 1) >= 2
        except ValueError:
            indexed = False
        entries_word = translate("TmSources", "entries")
        index_word = (translate("TmSources", "with a similarity index") if indexed
                      else translate("TmSources", "without a similarity index"))
        item = QListWidgetItem(
            f"{meta.get('name') or path.stem}  ·  {src} → {tgt}  ·  {kind}  ·  "
            f"{meta.get('entries', '0')} {entries_word}  ·  {index_word}"
            f"\n{path.name}")
        item.setData(Qt.UserRole, path.name)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if path.name in enabled else Qt.Unchecked)
        if not (src == self.src_lang and tgt == self.tgt_lang):
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setToolTip(translate("TmSources",
                      "The database languages do not match the project languages"))
        elif meta.get("game") and meta["game"] != self.game:
            # База без пометки игры молчит: собранные до появления игр ничего о
            # себе не говорят, а неизвестно — не то же самое, что неверно.
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            item.setToolTip(fill(translate(
                "TmSources", "The database is of another game — %1"),
                games.title(meta["game"])))
        return item

    def _update_status(self) -> None:
        enabled = set(project.get_tm_sources(self.conn))
        total = 0
        for path, meta in project.list_tm_databases(game=project.game(self.conn)):
            if path.name in enabled:
                try:
                    total += int(meta.get("entries", 0) or 0)
                except ValueError:
                    pass
        self._status = (
            fill(translate("TmSources",
                           "databases in the folder: %1 · attached: %2"),
                 self.list.count(), len(enabled))
            + (fill(translate("TmSources", " · entries: %1"), total)
               if total else ""))
        self.statusChanged.emit(self._status)

    # --- действия ---

    def _on_item_changed(self, _item) -> None:
        if self._syncing:
            return
        names = [
            self.list.item(i).data(Qt.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.Checked
        ]
        project.set_tm_sources(self.conn, names)
        project.attach_tm_sources(self.conn, project.project_tm_paths(self.conn))
        self._update_status()
        self.sourcesChanged.emit()

    def _build_index(self) -> None:
        """Достроить индекс похожих строк в выбранной базе.

        Базы подключены к проекту только на чтение, поэтому индекс строится
        отдельным соединением и только по явной команде.
        """
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(self, translate("TmSources", "Index"),
                translate("TmSources", "Choose a database in the list."))
            return
        path = settings.bdd_pen(self.game) / item.data(Qt.UserRole)
        if not path.is_file():        # база из времён до загонов
            path = settings.bdd_dir() / item.data(Qt.UserRole)
        if not path.is_file():
            QMessageBox.warning(self, translate("TmSources", "Index"),
                fill(translate("TmSources", "Database file not found:\n%1"), path))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            count = tm_import.build_fts_index(path)
        except (sqlite3.Error, RuntimeError, OSError) as e:
            QMessageBox.critical(self, translate("TmSources", "Index"),
                fill(translate("TmSources", "Could not build the index:\n%1"), e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.reload()
        QMessageBox.information(
            self, translate("TmSources", "Index"),
            fill(translate("TmSources",
                           "Index built: %1 entries.\n\nThe database now suggests "
                           "not only exact matches but similar rows too."), count))
