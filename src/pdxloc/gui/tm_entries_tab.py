"""Вкладка «Записи»: просмотр, правка и удаление пар памяти переводов.

Свои записи (память проекта) правятся и удаляются прямо здесь; записи
подключённых баз показываются приглушённым цветом — эти файлы открыты только
на чтение.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget,
)

from pdxloc.core import tm
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.gui import theme
from pdxloc.gui.sorting import SortState
from pdxloc.gui.widgets import HintLabel

COLUMNS = (
    QT_TRANSLATE_NOOP("TmEntries", "Original"),
    QT_TRANSLATE_NOOP("TmEntries", "Translation"),
    QT_TRANSLATE_NOOP("TmEntries", "Source"),
    QT_TRANSLATE_NOOP("TmEntries", "Key"),
    QT_TRANSLATE_NOOP("TmEntries", "Changed"),
)
COL_EN, COL_RU, COL_ORIGIN, COL_KEY, COL_DATE = range(5)

MAX_CELL = 160
BROWSE_LIMIT = 2000


def _sort_key(column: int):
    if column == COL_EN:
        return lambda r: r.en_text.casefold()
    if column == COL_RU:
        return lambda r: r.ru_text.casefold()
    if column == COL_ORIGIN:
        return lambda r: (r.origin or "").casefold()
    if column == COL_KEY:
        return lambda r: (r.key or "").casefold()
    return lambda r: r.updated_at or ""


class TmTableModel(QAbstractTableModel):
    edited = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._rows: list[tm.TmRecord] = []
        self._natural: dict[int, int] = {}
        self._sort: tuple[int, bool] | None = None
        theme.on_change(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        """Цвет нередактируемых записей берётся в data() — хватит перерисовки."""
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, len(COLUMNS) - 1))

    def reload(self, *, search: str = "", only_editable: bool = False) -> None:
        self.beginResetModel()
        self._rows = tm.browse(
            self.conn, search=search, only_editable=only_editable, limit=BROWSE_LIMIT)
        # порядок из SQL — «лучший источник и свежее выше»; к нему возвращает
        # третий клик по заголовку
        self._natural = {r.id: i for i, r in enumerate(self._rows)}
        self._rows = self._sorted_rows()
        self.endResetModel()

    def set_sort(self, spec: tuple[int, bool] | None) -> None:
        if spec == self._sort:
            return
        self._sort = spec
        if self._rows:
            self.beginResetModel()
            self._rows = self._sorted_rows()
            self.endResetModel()

    def _sorted_rows(self) -> list[tm.TmRecord]:
        nat = self._natural
        if self._sort is None:
            return sorted(self._rows, key=lambda r: nat[r.id])
        column, descending = self._sort
        key = _sort_key(column)
        return sorted(self._rows, key=lambda r: (key(r), nat[r.id]), reverse=descending)

    def record(self, row: int) -> tm.TmRecord | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return translate("TmEntries", COLUMNS[section])
        if role == Qt.ToolTipRole:
            return translate("TmEntries",
                             "Click — ascending, again — descending, again — "
                             "as the database returns it")
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
                return value[:MAX_CELL] + "…" if len(value) > MAX_CELL else value
            return value
        if role == Qt.ToolTipRole and col in (COL_EN, COL_RU):
            return (r.en_text, r.ru_text)[col]
        if role == Qt.ForegroundRole and not r.editable:
            return theme.qcolor("tm.readonly")
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


class TmEntriesTab(QWidget):
    statusChanged = Signal(str)

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._status = ""

        layout = QVBoxLayout(self)

        # Вводного абзаца на три строки больше нет: он занимал место в самом
        # верху каждый раз, а сказать хотел ровно то, что и так видно по
        # цвету строк и подсказкам.
        row = QHBoxLayout()
        row.addWidget(QLabel(translate("TmEntries", "Search:")))
        self.search = QLineEdit()
        self.search.setPlaceholderText(translate("TmEntries", "by original, translation or key…"))
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        self.own_only = QCheckBox(translate("TmEntries", "my entries only"))
        self.own_only.setToolTip(
            translate("TmEntries",
                      "Hide entries of attached databases — they are read only"))
        row.addWidget(self.own_only)
        layout.addLayout(row)

        self.model = TmTableModel(conn, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)

        header = self.table.horizontalHeader()
        # Оригинал и перевод тянутся, служебные колонки — по содержимому:
        # раньше все пять стояли фиксированной ширины и текст обрывался.
        header.setSectionResizeMode(COL_EN, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_RU, QHeaderView.Stretch)
        for col in (COL_ORIGIN, COL_KEY, COL_DATE):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._on_header_clicked)
        self.sort = SortState()
        layout.addWidget(self.table, 1)

        layout.addWidget(HintLabel(
            translate("TmEntries",
                      "Double click on a translation to edit it. Entries of "
                      "attached databases are dimmed: their files are open "
                      "read only.")))

        buttons = QHBoxLayout()
        self.delete_btn = QPushButton(translate("TmEntries", "Delete selected"))
        self.delete_btn.clicked.connect(self._delete_selected)
        buttons.addWidget(self.delete_btn)
        self.clear_btn = QPushButton(translate("TmEntries", "Clear my memory…"))
        self.clear_btn.clicked.connect(self._clear_own)
        buttons.addWidget(self.clear_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self.own_only.toggled.connect(self.reload)
        self.model.edited.connect(self._update_counts)

        self.reload()

    def shutdown(self) -> None:
        """Погасить отложенный поиск.

        Таймер не должен пережить окно: соединение проекта к тому времени
        бывает уже закрыто, и отложенный запрос падал на мёртвой базе.
        """
        self._debounce.stop()

    def status_text(self) -> str:
        return self._status

    # --- данные ---

    def reload(self) -> None:
        # Явная перезагрузка отменяет отложенную: иначе таймер поиска мог
        # сработать уже после закрытия проекта и упасть на мёртвой базе.
        self._debounce.stop()
        self.model.reload(
            search=self.search.text().strip(), only_editable=self.own_only.isChecked())
        self._update_counts()

    def _on_header_clicked(self, column: int) -> None:
        self.sort.click(column)
        header = self.table.horizontalHeader()
        if self.sort.column is None:
            self.model.set_sort(None)
            header.setSortIndicatorShown(False)
            return
        descending = self.sort.step == 2
        self.model.set_sort((self.sort.column, descending))
        header.setSortIndicatorShown(True)
        header.setSortIndicator(
            self.sort.column, Qt.DescendingOrder if descending else Qt.AscendingOrder)

    def _update_counts(self) -> None:
        own, total = tm.counts(self.conn)
        shown = self.model.rowCount()
        extra = (fill(translate("TmEntries", " · from attached databases: %1"),
                      total - own) if total > own else "")
        limited = (translate("TmEntries", " (first ones shown — refine the search)")
                   if shown >= BROWSE_LIMIT else "")
        self._status = fill(
            translate("TmEntries", "shown: %1%2 · my entries: %3%4"),
            shown, limited, own, extra)
        self.statusChanged.emit(self._status)

    # --- действия ---

    def _show_menu(self, pos) -> None:
        menu = QMenu(self.table)
        menu.addAction(self.delete_btn.text(), self._delete_selected)
        menu.addAction(self.clear_btn.text(), self._clear_own)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _selected_records(self) -> list[tm.TmRecord]:
        rows = self.table.selectionModel().selectedRows()
        records = [self.model.record(i.row()) for i in rows]
        return [r for r in records if r is not None]

    def _delete_selected(self) -> None:
        records = self._selected_records()
        own = [r for r in records if r.editable]
        if not records:
            return
        if not own:
            QMessageBox.information(
                self, translate("TmEntries", "Translation memory"),
                translate("TmEntries",
                          "Only entries of attached databases are selected — "
                          "they are read only.\nA database can be detached on "
                          "the «Databases» tab."))
            return
        skipped = len(records) - len(own)
        note = (fill(translate("TmEntries",
                               "\n\nEntries of attached databases (%1) will not "
                               "be touched."), skipped) if skipped else "")
        answer = QMessageBox.question(
            self, translate("TmEntries", "Deletion"),
            fill(translate("TmEntries",
                           "Delete %1 entries from the translation memory?%2\n\n"
                           "The translations of the project rows themselves do "
                           "not change."), len(own), note))
        if answer != QMessageBox.Yes:
            return
        tm.delete_entries(self.conn, [r.id for r in own])
        self.reload()

    def _clear_own(self) -> None:
        own, _ = tm.counts(self.conn)
        if not own:
            return
        answer = QMessageBox.question(
            self, translate("TmEntries", "Clear the memory"),
            fill(translate("TmEntries",
                           "Delete all %1 entries of my translation memory?\n\n"
                           "The translations of the project rows stay in place — "
                           "the memory fills up again on the next scan."), own))
        if answer == QMessageBox.Yes:
            tm.clear_own(self.conn)
            self.reload()
