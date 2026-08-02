"""Менеджер памяти переводов: просмотр, правка и удаление записей.

Свои записи (память проекта) можно править и удалять прямо здесь; записи из
подключённых баз показываются серым — эти файлы открыты только на чтение.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableView, QVBoxLayout,
)

from ck3loc.core import tm

COLUMNS = ("Оригинал", "Перевод", "Источник", "Ключ", "Изменено")
COL_EN, COL_RU, COL_ORIGIN, COL_KEY, COL_DATE = range(5)


class TmTableModel(QAbstractTableModel):
    edited = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._rows: list[tm.TmRecord] = []

    def reload(self, *, search: str = "", only_editable: bool = False) -> None:
        self.beginResetModel()
        self._rows = tm.browse(self.conn, search=search, only_editable=only_editable)
        self.endResetModel()

    def record(self, row: int) -> tm.TmRecord | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            value = (r.en_text, r.ru_text, r.origin, r.key or "", r.updated_at)[col]
            if role == Qt.DisplayRole and col in (COL_EN, COL_RU):
                value = value.replace("\\n", "⏎")
                return value[:160] + "…" if len(value) > 160 else value
            return value
        if role == Qt.ToolTipRole and col in (COL_EN, COL_RU):
            return (r.en_text, r.ru_text)[col]
        if role == Qt.ForegroundRole and not r.editable:
            return QColor("#777")
        return None

    def flags(self, index):
        base = super().flags(index)
        if index.isValid() and index.column() == COL_RU:
            r = self._rows[index.row()]
            if r.editable:
                return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or index.column() != COL_RU:
            return False
        r = self._rows[index.row()]
        if not r.editable or str(value) == r.ru_text:
            return False
        if tm.update_entry(self.conn, r.id, str(value)):
            self.edited.emit()
            return True
        return False


class TmManagerDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Память переводов")
        self.setMinimumSize(1000, 600)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Пары «оригинал — перевод», из которых берутся подсказки и автозаполнение.\n"
            "Свои записи можно править (двойной клик по переводу) и удалять; "
            "записи подключённых баз доступны только для чтения.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        row = QHBoxLayout()
        row.addWidget(QLabel("Поиск:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("по оригиналу, переводу или ключу…")
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        self.own_only = QCheckBox("только мои записи")
        row.addWidget(self.own_only)
        layout.addLayout(row)

        self.model = TmTableModel(conn)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setColumnWidth(COL_EN, 330)
        self.table.setColumnWidth(COL_RU, 330)
        self.table.setColumnWidth(COL_ORIGIN, 140)
        self.table.setColumnWidth(COL_KEY, 150)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.delete_btn = QPushButton("Удалить выделенные")
        self.delete_btn.clicked.connect(self._delete_selected)
        buttons.addWidget(self.delete_btn)
        clear_btn = QPushButton("Очистить мою память…")
        clear_btn.clicked.connect(self._clear_own)
        buttons.addWidget(clear_btn)
        buttons.addStretch(1)
        self.count_label = QLabel()
        self.count_label.setWordWrap(True)
        buttons.addWidget(self.count_label)
        layout.addLayout(buttons)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        layout.addWidget(box)

        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self._reload)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self.own_only.toggled.connect(self._reload)
        self.model.edited.connect(self._update_counts)

        self._reload()

    def closeEvent(self, event) -> None:
        # отложенный поиск не должен пережить окно: соединение проекта к тому
        # времени бывает уже закрыто, и таймер падал на мёртвой базе
        self._debounce.stop()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        self._debounce.stop()
        super().done(result)

    def _reload(self) -> None:
        self.model.reload(
            search=self.search.text().strip(), only_editable=self.own_only.isChecked())
        self._update_counts()

    BROWSE_LIMIT = 2000

    def _update_counts(self) -> None:
        own, total = tm.counts(self.conn)
        shown = self.model.rowCount()
        extra = f" · из подключённых баз: {total - own}" if total > own else ""
        limited = " (показаны первые — уточните поиск)" if shown >= self.BROWSE_LIMIT else ""
        self.count_label.setText(f"показано: {shown}{limited} · моих записей: {own}{extra}")

    def _selected_records(self) -> list[tm.TmRecord]:
        records = [self.model.record(i.row()) for i in self.table.selectionModel().selectedRows()]
        return [r for r in records if r is not None]

    def _delete_selected(self) -> None:
        records = self._selected_records()
        own = [r for r in records if r.editable]
        if not records:
            return
        if not own:
            QMessageBox.information(
                self, "Память переводов",
                "Выделены только записи подключённых баз — они доступны только для чтения.\n"
                "Отключить базу можно в «Инструменты → Базы памяти переводов…».")
            return
        skipped = len(records) - len(own)
        note = f"\n\nЗаписи подключённых баз ({skipped}) затронуты не будут." if skipped else ""
        answer = QMessageBox.question(
            self, "Удаление",
            f"Удалить {len(own)} записей из памяти переводов?{note}\n\n"
            "Переводы самих строк проекта при этом не меняются.")
        if answer != QMessageBox.Yes:
            return
        tm.delete_entries(self.conn, [r.id for r in own])
        self._reload()

    def _clear_own(self) -> None:
        own, _ = tm.counts(self.conn)
        if not own:
            return
        answer = QMessageBox.question(
            self, "Очистить память",
            f"Удалить все {own} записей моей памяти переводов?\n\n"
            "Переводы строк проекта останутся на месте — память заполнится заново "
            "при следующем сканировании.")
        if answer == QMessageBox.Yes:
            tm.clear_own(self.conn)
            self._reload()
