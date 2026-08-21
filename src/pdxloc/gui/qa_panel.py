"""The quality panel: a list of issues; a click jumps to the row."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QTableView, QVBoxLayout,
)

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core import qa_rules
from pdxloc.core.models import Issue
from pdxloc.core.qa import run_qa
from pdxloc.gui import rules_state, theme

QA_COLUMNS = (
    QT_TRANSLATE_NOOP("QaPanel", "Key"),
    QT_TRANSLATE_NOOP("QaPanel", "File"),
    QT_TRANSLATE_NOOP("QaPanel", "Issue"),
    QT_TRANSLATE_NOOP("QaPanel", "Severity"),
)

SEVERITY_LABELS = {
    qa_rules.ERROR: QT_TRANSLATE_NOOP("QaPanel", "Error"),
    qa_rules.WARNING: QT_TRANSLATE_NOOP("QaPanel", "Warning"),
    qa_rules.INFO: QT_TRANSLATE_NOOP("QaPanel", "Signal"),
}


class QaIssuesModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._issues: list[Issue] = []

    def set_issues(self, issues: list[Issue]) -> None:
        self.beginResetModel()
        self._issues = issues
        self.endResetModel()

    def issue_at(self, row: int) -> Issue | None:
        return self._issues[row] if 0 <= row < len(self._issues) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._issues)

    def columnCount(self, parent=QModelIndex()):
        return len(QA_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return translate("QaPanel", QA_COLUMNS[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        issue = self._issues[index.row()]
        if role == Qt.DisplayRole:
            return (
                issue.key, issue.file_rel_path, issue.message,
                translate("QaPanel",
                          SEVERITY_LABELS.get(issue.severity, issue.severity)),
            )[index.column()]
        if role == Qt.BackgroundRole and issue.severity == qa_rules.ERROR:
            return theme.qcolor("issue.row")
        return None


class QaReportDialog(QDialog):
    """A full check of the project, as a separate report rather than a panel.

    Day-to-day issues are visible in the «!» column of the main table; people
    come here when they want to walk the whole project in one go.
    """

    jumpToUnit = Signal(int)
    configureRule = Signal(str)     # «configure this rule» — the rule id

    def __init__(self, conn: sqlite3.Connection, project_id: int | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("QaPanel", "Project check"))
        self.setMinimumSize(900, 520)
        self.conn = conn
        self.project_id = project_id
        self._all_issues: list[Issue] = []

        body = self
        layout = QVBoxLayout(body)

        controls = QHBoxLayout()
        self.run_btn = QPushButton(translate("QaPanel", "Check"))
        self.run_btn.clicked.connect(self.run)
        controls.addWidget(self.run_btn)
        controls.addWidget(QLabel(translate("QaPanel", "Filter:")))
        self.code_combo = QComboBox()
        self.code_combo.addItem(translate("QaPanel", "All issues"), None)
        for rule in rules_state.ruleset():
            self.code_combo.addItem(rule.message_text(), rule.id)
        self.code_combo.currentIndexChanged.connect(self._apply_filter)
        controls.addWidget(self.code_combo, 1)
        self.count_label = QLabel("")
        controls.addWidget(self.count_label)
        layout.addLayout(controls)

        self.model = QaIssuesModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 320)
        self.table.activated.connect(self._jump)
        self.table.doubleClicked.connect(self._jump)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.ignore_btn = QPushButton(translate("QaPanel", "Not an error"))
        self.ignore_btn.setToolTip(
            translate("QaPanel",
                      "Mark the selected issue as false — do not show it again"))
        self.ignore_btn.clicked.connect(self._ignore_selected)
        bottom.addWidget(self.ignore_btn)
        # An issue can be false not in one row but in all of them at once, and
        # then the rule is what needs fixing — not a thousand rows marked one by
        # one
        self.configure_btn = QPushButton(translate("QaPanel", "Configure this rule…"))
        self.configure_btn.setToolTip(
            translate("QaPanel",
                      "Open the settings of the rule behind the selected issue"))
        self.configure_btn.clicked.connect(self._configure_selected)
        bottom.addWidget(self.configure_btn)
        bottom.addStretch(1)
        close_btn = QPushButton(translate("QaPanel", "Close"))
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

        if project_id is not None:
            self.run()

    def set_project(self, project_id: int | None) -> None:
        self.project_id = project_id

    def run(self) -> None:
        if self.project_id is None:
            return
        self._all_issues = run_qa(self.conn, self.project_id,
                                  ruleset=rules_state.ruleset())
        self._apply_filter()

    def _apply_filter(self) -> None:
        code = self.code_combo.currentData()
        issues = [i for i in self._all_issues if code is None or i.code == code]
        self.model.set_issues(issues)
        errors = sum(1 for i in issues if i.severity == "error")
        self.count_label.setText(fill(translate("QaPanel", "issues: %1 (errors: %2)"), len(issues), errors))

    def _jump(self, index) -> None:
        issue = self.model.issue_at(index.row())
        if issue is not None:
            self.jumpToUnit.emit(issue.unit_id)

    def _selected_issues(self) -> list[Issue]:
        rows = self.table.selectionModel().selectedRows()
        issues = [self.model.issue_at(i.row()) for i in rows]
        return [i for i in issues if i is not None]

    def _configure_selected(self) -> None:
        issues = self._selected_issues()
        if not issues:
            return
        self.configureRule.emit(issues[0].code)
        self.run()

    def _ignore_selected(self) -> None:
        from pdxloc.core import qa

        issues = self._selected_issues()
        if not issues:
            return
        for issue in issues:
            qa.ignore_issue(self.conn, issue.unit_id, issue.code)
        self.run()
