"""How this piece of text was translated before.

An exact match of a whole row helps rarely; «how did we translate Kingsguard
already» helps all the time. The search runs over a substring, across the
project's own memory and every attached database.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from pdxloc.core.i18n import fill, translate
from pdxloc.core import fuzzy

COL_EN, COL_RU, COL_ORIGIN = 0, 1, 2


class ConcordanceDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, fragment: str = "", parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("Concordance", "How was this translated before"))
        self.setMinimumSize(900, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel(translate("Concordance", "Fragment:")))
        self.search = QLineEdit(fragment)
        self.search.setPlaceholderText(translate(
            "Concordance", "a word or a piece of a phrase from the original…"))
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        layout.addLayout(row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([translate("Concordance", "Original"),
                                          translate("Concordance", "Translation"),
                                          translate("Concordance", "Source")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setSectionResizeMode(COL_EN, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COL_RU, QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self._copy_row)
        layout.addWidget(self.table, 1)

        self.count_label = QLabel()
        layout.addWidget(self.count_label)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        layout.addWidget(box)

        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self._reload)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self._reload()

    def closeEvent(self, event) -> None:
        self._debounce.stop()      # a pending search must not outlive the window
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._debounce.stop()
        super().done(result)

    def _reload(self) -> None:
        records = fuzzy.concordance(self.conn, self.search.text())
        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            for col, text in ((COL_EN, r.en_text), (COL_RU, r.ru_text),
                              (COL_ORIGIN, r.origin or r.source)):
                item = QTableWidgetItem(text.replace("\n", " "))
                item.setToolTip(text)
                self.table.setItem(i, col, item)
        self.count_label.setText(
            translate("Concordance", "Nothing found") if not records else
            fill(translate("Concordance",
                           "Found: %1 · double click copies the translation"),
                 len(records)))

    def _copy_row(self, item) -> None:
        ru = self.table.item(item.row(), COL_RU)
        if ru is not None:
            QGuiApplication.clipboard().setText(ru.toolTip() or ru.text())
            self.count_label.setText(translate("Concordance", "Translation copied to the clipboard"))
