"""The «Marked „not an error“» tab: bringing silenced issues back.

Split out of `rules_window.py` — the tab stands on its own and overlaps with the
rule settings only in that the two share a window.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from pdxloc.core import qa
from pdxloc.core.i18n import fill, translate
from pdxloc.gui import rules_state


class IgnoresTab(QWidget):
    """Silenced issues, and the way back into the check.

    `qa.unignore_issue` had existed from the start but was called from nowhere in
    the interface: mark an issue as false by mistake, and the only way back was
    editing the database by hand.
    """

    changed = Signal()

    def __init__(self, conn: sqlite3.Connection | None, parent=None):
        super().__init__(parent)
        self.conn = conn
        layout = QVBoxLayout(self)

        # An empty list says nothing about what this tab is or how anything
        # gets here — and it gets here from another window, from the F6 report.
        # An empty state has to answer the question «what is this», or people
        # ask it out loud.
        self.empty_label = QLabel(translate(
            "RulesWindow",
            "Nothing has been silenced yet.\n\n"
            "This is where issues go after the «Not an error» button in the "
            "check report (F6): a silenced issue stops showing up both in the "
            "report and in the «!» column of the table. From here it can be "
            "put back into the check."))
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setEnabled(False)      # muted: this is not an error
        layout.addWidget(self.empty_label, 1)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.return_btn = QPushButton(translate("RulesWindow", "Return to the check"))
        self.return_btn.clicked.connect(self._return_selected)
        row.addWidget(self.return_btn)
        self.return_all_btn = QPushButton(translate("RulesWindow", "Return all"))
        self.return_all_btn.clicked.connect(self._return_all)
        row.addWidget(self.return_all_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        if self.conn is None:
            return
        try:
            rows = self.conn.execute(
                """SELECT g.unit_id, g.code, u.key, f.rel_path
                   FROM qa_ignores g
                   JOIN units u ON u.id = g.unit_id
                   JOIN files f ON f.id = u.file_id
                   ORDER BY f.rel_path, u.key"""
            ).fetchall()
        except sqlite3.Error:
            rows = []
        rules = rules_state.ruleset()
        for row in rows:
            item = QListWidgetItem(
                f"{row['key']} — {rules.message(row['code'])}  ({row['rel_path']})")
            item.setData(Qt.UserRole, (row["unit_id"], row["code"]))
            self.list.addItem(item)
        self.return_btn.setEnabled(bool(rows))
        self.return_all_btn.setEnabled(bool(rows))
        # The list and the explanation share one spot: there is no point showing
        # an empty list, and the explanation would only be in the way once the
        # list has something in it
        self.list.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)

    def status_text(self) -> str:
        n = self.list.count()
        if not n:
            return translate("RulesWindow", "Nothing is marked «not an error».")
        return fill(translate("RulesWindow", "Marked «not an error»: %1."), n)

    def _return(self, pairs) -> None:
        if self.conn is None or not pairs:
            return
        for unit_id, code in pairs:
            qa.unignore_issue(self.conn, unit_id, code)
        self.reload()
        self.changed.emit()

    def _return_selected(self) -> None:
        self._return([i.data(Qt.UserRole) for i in self.list.selectedItems()])

    def _return_all(self) -> None:
        if not self.list.count():
            return
        if QMessageBox.question(
                self, translate("RulesWindow", "Return all"),
                fill(translate("RulesWindow",
                               "Return all %1 issues to the check?"),
                     self.list.count())
        ) != QMessageBox.Yes:
            return
        self._return([self.list.item(i).data(Qt.UserRole)
                      for i in range(self.list.count())])

    def shutdown(self) -> None:
        pass
