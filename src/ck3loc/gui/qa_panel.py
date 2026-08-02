"""Панель проверки качества: список проблем, клик — переход к строке."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel,
    QPushButton, QTableView, QVBoxLayout,
)

from ck3loc.core.models import Issue
from ck3loc.core.qa import CODES, run_qa

QA_COLUMNS = ("Ключ", "Файл", "Проблема", "Серьёзность")


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
            return QA_COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        issue = self._issues[index.row()]
        if role == Qt.DisplayRole:
            return (
                issue.key, issue.file_rel_path, issue.message,
                "Ошибка" if issue.severity == "error" else "Предупреждение",
            )[index.column()]
        if role == Qt.BackgroundRole and issue.severity == "error":
            return QColor("#f8d0d0")
        return None


class QaReportDialog(QDialog):
    """Полная проверка проекта — отдельным отчётом, а не панелью на экране.

    Повседневные замечания видны в колонке «!» основной таблицы; сюда ходят,
    когда нужно пройтись по всему проекту разом.
    """

    jumpToUnit = Signal(int)

    def __init__(self, conn: sqlite3.Connection, project_id: int | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Проверка проекта")
        self.setMinimumSize(900, 520)
        self.conn = conn
        self.project_id = project_id
        self._all_issues: list[Issue] = []

        body = self
        layout = QVBoxLayout(body)

        controls = QHBoxLayout()
        self.run_btn = QPushButton("Проверить")
        self.run_btn.clicked.connect(self.run)
        controls.addWidget(self.run_btn)
        controls.addWidget(QLabel("Фильтр:"))
        self.code_combo = QComboBox()
        self.code_combo.addItem("Все проблемы", None)
        for code, (_, message) in CODES.items():
            self.code_combo.addItem(message, code)
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
        self.ignore_btn = QPushButton("Не считать ошибкой")
        self.ignore_btn.setToolTip(
            "Пометить выделенное замечание как ложное — больше не показывать")
        self.ignore_btn.clicked.connect(self._ignore_selected)
        bottom.addWidget(self.ignore_btn)
        bottom.addStretch(1)
        close_btn = QPushButton("Закрыть")
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
        self._all_issues = run_qa(self.conn, self.project_id)
        self._apply_filter()

    def _apply_filter(self) -> None:
        code = self.code_combo.currentData()
        issues = [i for i in self._all_issues if code is None or i.code == code]
        self.model.set_issues(issues)
        errors = sum(1 for i in issues if i.severity == "error")
        self.count_label.setText(f"проблем: {len(issues)} (ошибок: {errors})")

    def _jump(self, index) -> None:
        issue = self.model.issue_at(index.row())
        if issue is not None:
            self.jumpToUnit.emit(issue.unit_id)

    def _ignore_selected(self) -> None:
        from ck3loc.core import qa

        rows = self.table.selectionModel().selectedRows()
        issues = [self.model.issue_at(i.row()) for i in rows]
        issues = [i for i in issues if i is not None]
        if not issues:
            return
        for issue in issues:
            qa.ignore_issue(self.conn, issue.unit_id, issue.code)
        self.run()
