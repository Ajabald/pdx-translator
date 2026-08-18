"""Архив переводов: ключи, которых больше нет в оригинале.

Сюда попадают переводы удалённых из мода строк и опечаток в ключах. В экспорт
они не идут, но и не пропадают — отсюда их можно скопировать обратно.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableView, QVBoxLayout,
)

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate

COLUMNS = (
    QT_TRANSLATE_NOOP("Archive", "File"),
    QT_TRANSLATE_NOOP("Archive", "Key"),
    QT_TRANSLATE_NOOP("Archive", "Translation"),
    QT_TRANSLATE_NOOP("Archive", "Archived on"),
)


class ArchiveModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[sqlite3.Row] = []

    def set_rows(self, rows: list[sqlite3.Row]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return translate("Archive", COLUMNS[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            value = (r["rel_path"], r["key"], r["ru_text"], r["archived_at"])[index.column()]
            if role == Qt.DisplayRole and index.column() == 2 and len(value) > 200:
                return value[:200] + "…"
            return value
        return None

    def text_at(self, row: int) -> str:
        return self._rows[row]["ru_text"] if 0 <= row < len(self._rows) else ""

    def all_as_text(self) -> str:
        return "\n".join(f"{r['key']}\t{r['ru_text']}" for r in self._rows)


class ArchiveDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("Archive", "Archive of old translations"))
        self.setMinimumSize(900, 500)

        layout = QVBoxLayout(self)
        intro = QLabel(translate(
            "Archive",
            "Translations of keys that are gone from the mod original: deleted "
            "rows and typos in keys.\nThey do not reach the write-to-mod step "
            "but are kept here."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel(translate("Archive", "Search:")))
        self.search = QLineEdit()
        self.search.setPlaceholderText(translate("Archive", "by key, file or translation text…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._reload)
        row.addWidget(self.search, 1)
        self.count_label = QLabel("")
        row.addWidget(self.count_label)
        layout.addLayout(row)

        self.model = ArchiveModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 340)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        copy_one = QPushButton(translate("Archive", "Copy the translation"))
        copy_one.clicked.connect(self._copy_selected)
        copy_all = QPushButton(translate("Archive", "Copy everything (key + translation)"))
        copy_all.clicked.connect(self._copy_all)
        buttons.addWidget(copy_one)
        buttons.addWidget(copy_all)
        buttons.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        buttons.addWidget(box)
        layout.addLayout(buttons)

        self._reload()

    def _reload(self) -> None:
        needle = self.search.text().strip().casefold()
        if needle:
            like = f"%{needle}%"
            rows = self.conn.execute(
                "SELECT * FROM legacy_translations "
                "WHERE pylower(key) LIKE ? OR pylower(rel_path) LIKE ? OR pylower(ru_text) LIKE ? "
                "ORDER BY rel_path, key", (like, like, like)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM legacy_translations ORDER BY rel_path, key").fetchall()
        self.model.set_rows(rows)
        self.count_label.setText(
            fill(translate("Archive", "entries: %1"), len(rows)))

    def _copy_selected(self) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            QGuiApplication.clipboard().setText(self.model.text_at(indexes[0].row()))

    def _copy_all(self) -> None:
        QGuiApplication.clipboard().setText(self.model.all_as_text())
