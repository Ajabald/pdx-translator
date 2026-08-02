"""Модель и представление таблицы строк.

Производительность: данные грузятся в память одним SQL-запросом (reload).
Фильтрация — повторный SQL-запрос, не QSortFilterProxyModel: комбинированные
фильтры (статус + файл + LIKE по трём полям) в SQL быстрее и проще.
Из data() в БД не ходим никогда.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from ck3loc.core import qa, tm, unit_ops
from ck3loc.core.statuses import STATUS_LABELS, Status
from ck3loc.gui import theme

COLUMNS = ("Ключ", "Файл", "EN", "RU", "Статус", "Δ", "!", "✓", "✗", "C", "И")
COL_KEY, COL_FILE, COL_EN, COL_RU, COL_STATUS, COL_CHANGE, COL_ISSUES = range(7)
COL_QS_FIRST = 7

# quick-колонки: колонка -> (глиф, целевой статус, подсказка, имя цвета в палитре)
QUICK_COLS: dict[int, tuple[str, Status, str, str]] = {
    7: ("✓", Status.REVIEWED, "Подтвердить (F10)", "quick.reviewed"),
    8: ("✗", Status.TRANSLATED, "Снять подтверждение (Shift+F10)", "quick.translated"),
    9: ("C", Status.CUSTOM, "Кастомный статус (Ctrl+F10)", "quick.custom"),
    10: ("И", Status.IGNORED, "Игнорировать (Ctrl+Shift+F10)", "quick.ignored"),
}

# характер правки оригинала: глиф, подсказка, имя цвета в палитре
CHANGE_MARKS = {
    "cosmetic": ("·", "Оригинал правили косметически (пунктуация, регистр, пробелы)",
                 "change.cosmetic"),
    "meaningful": ("!", "Оригинал изменился по смыслу — перевод нужно проверить",
                   "change.meaningful"),
}

MAX_CELL = 150

# общая с ядром — поиск устроен одинаково везде
escape_like = tm.escape_like


@dataclass
class UnitFilters:
    status: str | None = None      # значение Status или None = все
    file_rel: str | None = None    # точный rel_path файла
    file_prefix: str | None = None # префикс папки (для дерева)
    search: str = ""
    show_deleted: bool = False
    only_issues: bool = False      # только строки с замечаниями проверки


def _cell(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\\n", "⏎")
    return text[:MAX_CELL] + "…" if len(text) > MAX_CELL else text


class UnitsTableModel(QAbstractTableModel):
    unitSaved = Signal(int)   # после правки в ячейке

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id: int | None = None
        self._rows: list[sqlite3.Row] = []
        self._row_by_id: dict[int, int] = {}
        self._issues: dict[int, list[str]] = {}   # unit_id -> коды замечаний
        theme.on_change(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        """Цвета берутся в data(), поэтому достаточно попросить перерисовку."""
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, len(COLUMNS) - 1))

    # --- загрузка ---

    def clear(self) -> None:
        """Опустошить таблицу — при закрытии проекта соединение уже мертво."""
        self.beginResetModel()
        self._rows = []
        self._row_by_id = {}
        self._issues = {}
        self.project_id = None
        self.endResetModel()

    def reload(self, project_id: int, filters: UnitFilters) -> None:
        sql = [
            """SELECT u.id, u.key, f.rel_path, u.en_text, u.ru_text, u.status,
                      u.is_deleted, u.file_id, u.change_kind, u.prev_en_text
               FROM units u JOIN files f ON f.id = u.file_id
               WHERE f.project_id = ?"""
        ]
        params: list = [project_id]
        if not filters.show_deleted:
            sql.append("AND u.is_deleted = 0")
        if filters.status:
            sql.append("AND u.status = ?")
            params.append(filters.status)
        if filters.file_rel:
            sql.append("AND f.rel_path = ?")
            params.append(filters.file_rel)
        if filters.file_prefix:
            sql.append("AND f.rel_path LIKE ? || '/%'")
            params.append(filters.file_prefix)
        if filters.search:
            # pylower — Unicode-регистр (встроенный LIKE регистронезависим только
            # для ASCII); ESCAPE — чтобы % и _ в запросе искались буквально
            sql.append(
                "AND (pylower(u.key) LIKE ? ESCAPE '\\' "
                "OR pylower(u.en_text) LIKE ? ESCAPE '\\' "
                "OR pylower(u.ru_text) LIKE ? ESCAPE '\\')"
            )
            like = f"%{escape_like(filters.search.casefold())}%"
            params += [like, like, like]
        sql.append("ORDER BY f.rel_path, u.line_no, u.key")

        self.beginResetModel()
        self.project_id = project_id
        self._rows = self.conn.execute(" ".join(sql), params).fetchall()
        self._row_by_id = {r["id"]: i for i, r in enumerate(self._rows)}
        self._recheck_all()
        if filters.only_issues:
            # фильтр по замечаниям — уже после проверки: в SQL их нет
            self._rows = [r for r in self._rows if r["id"] in self._issues]
            self._row_by_id = {r["id"]: i for i, r in enumerate(self._rows)}
        self.endResetModel()

    def _recheck_all(self) -> None:
        """Проверки по загруженным строкам — колонка «!» показывает результат.

        Полный проход по 5к строк занимает около 45 мс, поэтому считаем сразу,
        а не по кнопке: замечания видны там же, где идёт работа.
        """
        self._issues.clear()
        ignored = qa.ignored_pairs(self.conn)
        for r in self._rows:
            if not r["en_text"] or not r["ru_text"]:
                continue
            codes = [c for c in qa.check_unit(r["en_text"], r["ru_text"])
                     if (r["id"], c) not in ignored]
            if codes:
                self._issues[r["id"]] = codes

    def recheck_unit(self, unit_id: int) -> None:
        """Пересчитать замечания одной строки — после сохранения перевода."""
        row = self.conn.execute(
            "SELECT id, en_text, ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()
        self._issues.pop(unit_id, None)
        if row and row["en_text"] and row["ru_text"]:
            ignored = {c for uid, c in qa.ignored_pairs(self.conn) if uid == unit_id}
            codes = [c for c in qa.check_unit(row["en_text"], row["ru_text"])
                     if c not in ignored]
            if codes:
                self._issues[unit_id] = codes

    def issues_of(self, unit_id: int) -> list[str]:
        return self._issues.get(unit_id, [])

    def refresh_row(self, unit_id: int) -> None:
        """Обновить одну строку после сохранения (без полного reload)."""
        i = self._row_by_id.get(unit_id)
        if i is None:
            return
        self.recheck_unit(unit_id)
        row = self.conn.execute(
            """SELECT u.id, u.key, f.rel_path, u.en_text, u.ru_text, u.status,
                      u.is_deleted, u.file_id, u.change_kind, u.prev_en_text
               FROM units u JOIN files f ON f.id = u.file_id WHERE u.id = ?""",
            (unit_id,),
        ).fetchone()
        if row is None:
            return
        self._rows[i] = row
        self.dataChanged.emit(self.index(i, 0), self.index(i, len(COLUMNS) - 1))

    # --- QAbstractTableModel ---

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()
        if col == COL_CHANGE:
            mark = CHANGE_MARKS.get(r["change_kind"] or "")
            if role == Qt.DisplayRole:
                return mark[0] if mark else ""
            if role == Qt.ToolTipRole:
                return mark[1] if mark else None
            if role == Qt.ForegroundRole and mark:
                return theme.qcolor(mark[2])
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
            if role == Qt.FontRole and mark:
                f = QFont()
                f.setBold(True)
                return f
            if role == Qt.BackgroundRole:
                return self._row_bg(r)
            return None
        if col == COL_ISSUES:
            codes = self._issues.get(r["id"], [])
            has_error = any(qa.CODES.get(c, ("", ""))[0] == "error" for c in codes)
            if role == Qt.DisplayRole:
                return str(len(codes)) if codes else ""
            if role == Qt.ToolTipRole and codes:
                return "\n".join(f"• {qa.CODES[c][1]}" for c in codes)
            if role == Qt.ForegroundRole and codes:
                return theme.qcolor("issue.error" if has_error else "issue.warning")
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
            if role == Qt.FontRole and has_error:
                f = QFont()
                f.setBold(True)
                return f
            if role == Qt.BackgroundRole:
                return self._row_bg(r)
            return None
        if col >= COL_QS_FIRST:
            glyph, target, tip, color_key = QUICK_COLS[col]
            if role == Qt.DisplayRole:
                return glyph
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
            if role == Qt.ToolTipRole:
                return tip
            if role == Qt.ForegroundRole:
                applicable = self._quick_applicable(r, target)
                return theme.qcolor(color_key if applicable else "quick.disabled")
            if role == Qt.FontRole:
                f = QFont()
                f.setBold(True)
                return f
            if role == Qt.BackgroundRole:
                return self._row_bg(r)
            if role == Qt.UserRole:
                return r["id"]
            return None
        if role == Qt.DisplayRole:
            if col == COL_KEY:
                return r["key"]
            if col == COL_FILE:
                return r["rel_path"]
            if col == COL_EN:
                return _cell(r["en_text"])
            if col == COL_RU:
                return _cell(r["ru_text"])
            if col == COL_STATUS:
                label = STATUS_LABELS.get(Status(r["status"]), r["status"])
                return f"{label} (удалён)" if r["is_deleted"] else label
        elif role == Qt.EditRole and col == COL_RU:
            return r["ru_text"] or ""          # сырой полный текст, не обрезка
        elif role == Qt.BackgroundRole:
            return self._row_bg(r)
        elif role == Qt.ForegroundRole:
            return theme.qcolor("text")
        elif role == Qt.ToolTipRole:
            if col == COL_EN:
                return r["en_text"]
            if col == COL_RU:
                return r["ru_text"]
        elif role == Qt.UserRole:
            return r["id"]
        return None

    @staticmethod
    def _row_bg(r: sqlite3.Row) -> QColor | None:
        c = QColor(theme.status_color(r["status"]))
        # удалённые строки приглушаем: на тёмной теме «темнее» нечитаемо,
        # поэтому там наоборот подсветляем
        return (c.lighter(130) if theme.is_dark() else c.darker(115)) \
            if r["is_deleted"] else c

    @staticmethod
    def _quick_applicable(r: sqlite3.Row, target: Status) -> bool:
        """Применима ли quick-кнопка к строке (иначе глиф приглушается)."""
        status = r["status"]
        if r["is_deleted"] or r["en_text"] is None:
            return False
        if target == Status.REVIEWED:
            return r["ru_text"] is not None and status != Status.REVIEWED.value
        if target == Status.TRANSLATED:     # «снять подтверждение»
            return status == Status.REVIEWED.value
        if target == Status.CUSTOM:
            return r["ru_text"] is not None and status != Status.CUSTOM.value
        if target == Status.IGNORED:
            return status != Status.IGNORED.value
        return False

    def flags(self, index: QModelIndex):
        base = super().flags(index)
        if not index.isValid():
            return base
        r = self._rows[index.row()]
        if index.column() == COL_RU and not r["is_deleted"] and r["en_text"] is not None:
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index: QModelIndex, value, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or index.column() != COL_RU:
            return False
        r = self._rows[index.row()]
        if str(value) == (r["ru_text"] or ""):
            return False
        unit_ops.save_ru_text(self.conn, r["id"], str(value))
        self.refresh_row(r["id"])
        self.unitSaved.emit(r["id"])
        return True

    def raw_cell(self, row: int, col: int) -> str:
        """Сырой (необрезанный) текст ячейки — для копирования."""
        if not (0 <= row < len(self._rows)):
            return ""
        r = self._rows[row]
        if col == COL_KEY:
            return r["key"]
        if col == COL_FILE:
            return r["rel_path"]
        if col == COL_EN:
            return r["en_text"] or ""
        if col == COL_RU:
            return r["ru_text"] or ""
        if col == COL_STATUS:
            return STATUS_LABELS.get(Status(r["status"]), r["status"])
        if col == COL_CHANGE:
            return r["change_kind"] or ""
        if col == COL_ISSUES:
            return "; ".join(qa.CODES[c][1] for c in self._issues.get(r["id"], []))
        return ""

    def row_data(self, row: int) -> sqlite3.Row | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    # --- утилиты для навигации ---

    def unit_id_at(self, row: int) -> int | None:
        return self._rows[row]["id"] if 0 <= row < len(self._rows) else None

    def row_of_unit(self, unit_id: int) -> int | None:
        return self._row_by_id.get(unit_id)

    def next_row_with_status(self, from_row: int, statuses: set[str]) -> int | None:
        n = len(self._rows)
        for offset in range(1, n + 1):
            i = (from_row + offset) % n
            if self._rows[i]["status"] in statuses:
                return i
        return None


class UnitsTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.horizontalHeader().setStretchLastSection(False)

    def configure_columns(self) -> None:
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_KEY, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_FILE, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_EN, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_RU, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_CHANGE, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_ISSUES, QHeaderView.Fixed)
        self.setColumnWidth(COL_KEY, 260)
        self.setColumnWidth(COL_FILE, 200)
        self.setColumnWidth(COL_STATUS, 120)
        self.setColumnWidth(COL_CHANGE, 26)
        self.setColumnWidth(COL_ISSUES, 26)
        for col in QUICK_COLS:
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.setColumnWidth(col, 26)

    def selected_unit_ids(self) -> list[int]:
        model = self.model()
        return [model.unit_id_at(i.row()) for i in self.selectionModel().selectedRows()]
