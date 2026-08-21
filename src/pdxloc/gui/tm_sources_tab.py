"""The «Databases» tab: which memory databases are attached to the project.

There are no OK/Cancel buttons here: inside a tab they mean nothing (there is
nothing to close), and «changed but not saved yet» only confused people — in the
window header the very same databases are toggled with one click and apply at
once. Now it works the same way here.
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

        # memory databases are matched by language folder, not by text locale:
        # the folder is what the database itself records
        # (see tm_import.create_tm_database)
        langs = project.languages(conn)
        self.src_lang, self.tgt_lang = langs.src_lang, langs.tgt_lang
        self.game = project.game(conn)

        layout = QVBoxLayout(self)
        intro = QLabel(fill(translate(
            "TmSources", "Checked databases provide suggestions and autofill "
                         "(%1 → %2). Changes apply immediately."),
            self.src_lang, self.tgt_lang))
        intro.setWordWrap(True)     # otherwise the label stretches the window across the screen
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
        """No timers of its own; the method exists for the shared tab protocol."""

    def status_text(self) -> str:
        return self._status

    # --- data ---

    def reload(self) -> None:
        self._syncing = True
        try:
            self.list.clear()
            enabled = set(project.get_tm_sources(self.conn))
            databases = project.list_tm_databases(
                game=project.game(self.conn))
            for path, meta in databases:
                self.list.addItem(self._make_item(path, meta, enabled))
            # enabled, but gone from the disk
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
            # A database with no game recorded stays silent: the ones built
            # before games existed say nothing about themselves, and unknown is
            # not the same as wrong.
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

    # --- actions ---

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
        """Build the similar-rows index in the selected database.

        Databases are attached to the project read-only, so the index is built
        through a connection of its own and only on an explicit command.
        """
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(self, translate("TmSources", "Index"),
                translate("TmSources", "Choose a database in the list."))
            return
        path = settings.bdd_pen(self.game) / item.data(Qt.UserRole)
        if not path.is_file():        # a database from before the per-game pens
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
