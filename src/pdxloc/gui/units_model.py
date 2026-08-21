"""The model and the view of the row table.

Performance: the data is loaded into memory by a single SQL query (reload).
Filtering is another SQL query rather than a QSortFilterProxyModel: combined
filters — status plus file plus a LIKE over three fields — are both faster and
simpler in SQL. data() never goes to the database.

Sorting, by contrast, happens entirely in memory. It cannot be done in SQL: the
«!» column, the number of issues, does not exist in the database at all — it is
computed by `_recheck_all()` after the selection, and the same `only_issues`
filters the list in post-processing. An SQL path would need a second,
Python-side implementation for that one column, while reordering 5k rows in
memory takes single-digit milliseconds against a full reload with the checks
recomputed.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from pdxloc import settings
from pdxloc.core import qa, qa_rules, statuses as statuses_mod, tm, unit_ops
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, translate
from pdxloc.core.statuses import STATUS_RANK, Status
from pdxloc.gui import prefs, rules_state, theme

CTX = "UnitsTable"

COLUMNS = (
    QT_TRANSLATE_NOOP("UnitsTable", "Key"),
    QT_TRANSLATE_NOOP("UnitsTable", "File"),
    "EN", "RU",
    QT_TRANSLATE_NOOP("UnitsTable", "Status"),
    "Δ", "!", "✓", "✗",
    QT_TRANSLATE_NOOP("UnitsTable", "C"),      # the first letter of «custom»
    QT_TRANSLATE_NOOP("UnitsTable", "I"),      # the first letter of «ignore»
)
COL_KEY, COL_FILE, COL_EN, COL_RU, COL_STATUS, COL_CHANGE, COL_ISSUES = range(7)
COL_QS_FIRST = 7

# the quick columns: column -> (glyph, target status, tooltip, colour name in
# the palette). The letter glyphs («C», «I») are translated together with the
# header — the same strings in the same context; otherwise the Russian interface
# would keep Latin letters in the column.
QUICK_COLS: dict[int, tuple[str, Status, str, str]] = {
    7: ("✓", Status.REVIEWED,
        QT_TRANSLATE_NOOP("UnitsTable", "Validate (F10)"), "quick.reviewed"),
    8: ("✗", Status.TRANSLATED,
        QT_TRANSLATE_NOOP("UnitsTable", "Unvalidate (Shift+F10)"), "quick.translated"),
    9: ("C", Status.CUSTOM,
        QT_TRANSLATE_NOOP("UnitsTable", "Custom status (Ctrl+F10)"), "quick.custom"),
    10: ("I", Status.IGNORED,
         QT_TRANSLATE_NOOP("UnitsTable", "Ignore (Ctrl+Shift+F10)"), "quick.ignored"),
}

# the nature of an edit to the original: glyph, tooltip, colour name in the
# palette
CHANGE_MARKS = {
    "cosmetic": ("·", QT_TRANSLATE_NOOP(
        "UnitsTable", "The original was edited cosmetically "
                      "(punctuation, case, spaces)"), "change.cosmetic"),
    "meaningful": ("!", QT_TRANSLATE_NOOP(
        "UnitsTable", "The original changed in meaning — check the translation"),
        "change.meaningful"),
}

# The cell truncation is a module variable rather than a settings read inside
# _cell(): that one is called on every paint of every cell. A subscriber
# refreshes it
MAX_CELL = prefs.get("editor/cell_limit")

# shared with the core: the search works the same way everywhere
escape_like = tm.escape_like


def _worst_severity(codes: list[str]) -> str:
    """The heaviest severity among a row's issues; the «!» is coloured by it.

    The severity of a rule is configurable, so we ask the rule set rather than
    count «error or no error»: in the recommended set `inconsistent` is lowered to
    a signal, and colouring it as a warning would be a lie.
    """
    rules = rules_state.ruleset()
    return min((rules.severity(c) for c in codes),
               key=lambda s: qa_rules.SEVERITY_RANK.get(s, 9),
               default=qa_rules.WARNING)

# A tooltip on the header: what a click does. Without it a column 26 pixels wide
# stays a cryptogram.
SORT_HINTS = {
    COL_KEY: QT_TRANSLATE_NOOP("UnitsTable", "Sort by key"),
    COL_FILE: QT_TRANSLATE_NOOP("UnitsTable", "Sort by file"),
    COL_EN: QT_TRANSLATE_NOOP("UnitsTable", "Sort by original text"),
    COL_RU: QT_TRANSLATE_NOOP("UnitsTable", "Sort by translated text"),
    COL_STATUS: QT_TRANSLATE_NOOP(
        "UnitsTable", "Sort by status — in working order, not alphabetically"),
    COL_CHANGE: QT_TRANSLATE_NOOP(
        "UnitsTable", "Sort by kind of change to the original: meaningful first"),
    COL_ISSUES: QT_TRANSLATE_NOOP(
        "UnitsTable", "Click — rows with issues on top. Click again — only those. "
                      "Again — as it was"),
}
SORT_CYCLE_HINT = QT_TRANSLATE_NOOP(
    "UnitsTable", "Click — ascending, again — descending, again — as it was")

# The data columns: everything except the button columns ✓ ✗ C I. Both «View»
# submenus are built from this list — «Sort» and «Columns» alike: sorting and
# hiding make sense for exactly what shows data, and a button is neither.
DATA_COLUMNS: tuple[tuple[int, str], ...] = (
    (COL_KEY, QT_TRANSLATE_NOOP("UnitsTable", "Key")),
    (COL_FILE, QT_TRANSLATE_NOOP("UnitsTable", "File")),
    (COL_EN, QT_TRANSLATE_NOOP("UnitsTable", "Original")),
    (COL_RU, QT_TRANSLATE_NOOP("UnitsTable", "Translation")),
    (COL_STATUS, QT_TRANSLATE_NOOP("UnitsTable", "Status")),
    (COL_CHANGE, QT_TRANSLATE_NOOP("UnitsTable", "Change to original")),
    (COL_ISSUES, QT_TRANSLATE_NOOP("UnitsTable", "Issues")),
)
SORT_COLUMNS = DATA_COLUMNS     # the old name: the sort submenu called it

_CHANGE_RANK = {"meaningful": 0, "cosmetic": 1}
_NUM_RE = re.compile(r"(\d+)")


def _text_key(value: str | None) -> tuple[int, tuple]:
    """A text key: empty goes last, and numbers compare as numbers.

    Localisation keys are numbered throughout (`agot_bla_2`, `agot_bla_10`), and
    lexicographic order puts 10 before 2. The tuple elements are of a single shape
    on purpose: otherwise int and str fall out when neighbouring parts are
    compared.
    """
    if not value:
        return (1, ())
    return (0, tuple((0, int(p), "") if p.isdigit() else (1, 0, p)
                     for p in _NUM_RE.split(value.casefold()) if p))


@dataclass
class UnitFilters:
    status: str | None = None      # a Status value, or None for all of them
    file_rel: str | None = None    # the exact rel_path of a file
    file_prefix: str | None = None # a folder prefix, for the tree
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
        self._issue_rank: dict[int, tuple[int, int]] = {}   # unit_id -> (всего, ошибок)
        # порядок из SQL: третий клик по заголовку возвращает именно его
        self._natural_rank: dict[int, int] = {}
        self._sort: tuple[int, bool] | None = None    # (колонка, по убыванию)
        theme.on_change(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        """The colours come from data(), so asking for a repaint is enough."""
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, len(COLUMNS) - 1))

    # --- loading ---

    def clear(self) -> None:
        """Empty the table: by the time a project closes the connection is dead."""
        self.beginResetModel()
        self._rows = []
        self._row_by_id = {}
        self._issues = {}
        self._issue_rank = {}
        self._natural_rank = {}
        self.project_id = None
        self.endResetModel()

    def reload(self, project_id: int, filters: UnitFilters) -> None:
        sql = [
            """SELECT u.id, u.key, f.rel_path, u.en_text, u.ru_text, u.status,
                      u.is_deleted, u.file_id, u.change_kind, u.prev_en_text,
                      u.qa_hash, u.qa_codes
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
            # pylower gives Unicode case folding — the built-in LIKE is case-insensitive for
            # ASCII only; ESCAPE makes % and _ in a query match literally
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
        # естественный порядок запоминаем до фильтрации и сортировки
        self._natural_rank = {r["id"]: i for i, r in enumerate(self._rows)}
        self._recheck_all()
        if filters.only_issues:
            # фильтр по замечаниям — уже после проверки: в SQL их нет
            self._rows = [r for r in self._rows if r["id"] in self._issues]
        self._rows = self._sorted_rows()
        self._reindex()
        self.endResetModel()

    def _reindex(self) -> None:
        self._row_by_id = {r["id"]: i for i, r in enumerate(self._rows)}

    def _recheck_all(self) -> None:
        """Проверки по загруженным строкам — колонка «!» показывает результат.

        Считаем сразу, а не по кнопке: замечания видны там же, где идёт работа.
        Полный проход стоит дорого — 3,35 с на 124 893 строках ванильной HOI4, —
        поэтому строка помнит свой результат до следующей правки (см. `core/qa`),
        и заново считаются только те, где текст или набор правил изменились.
        """
        self._issues.clear()
        self._issue_rank.clear()
        ignored = qa.ignored_pairs(self.conn)
        found = qa.cached_issues(self.conn, self._rows, rules_state.ruleset())
        for unit_id, codes in found.items():
            codes = [c for c in codes if (unit_id, c) not in ignored]
            if codes:
                self._set_issues(unit_id, codes)

    def _set_issues(self, unit_id: int, codes: list[str]) -> None:
        """Замечания строки и её вес для сортировки колонки «!».

        Число ошибок считаем здесь, а не в data(): раньше `has_error`
        пересчитывался на каждую отрисовку ячейки.
        """
        self._issues[unit_id] = codes
        rules = rules_state.ruleset()
        errors = sum(1 for c in codes if rules.severity(c) == qa_rules.ERROR)
        self._issue_rank[unit_id] = (len(codes), errors)

    def recheck_unit(self, unit_id: int) -> None:
        """Пересчитать замечания одной строки — после сохранения перевода."""
        self._issues.pop(unit_id, None)
        self._issue_rank.pop(unit_id, None)
        ignored = {c for uid, c in qa.ignored_pairs(self.conn) if uid == unit_id}
        codes = [c for c in qa.recheck_one(self.conn, unit_id, rules_state.ruleset())
                 if c not in ignored]
        if codes:
            self._set_issues(unit_id, codes)

    def issues_of(self, unit_id: int) -> list[str]:
        return self._issues.get(unit_id, [])

    def issue_count(self) -> int:
        """Сколько загруженных строк имеют замечания — для чипа «!»."""
        return len(self._issues)

    # --- сортировка ---

    def set_sort(self, spec: tuple[int, bool] | None) -> None:
        """Задать порядок и сразу переставить строки."""
        if spec == self._sort:
            return
        self._sort = spec
        self.apply_sort()

    def apply_sort(self) -> None:
        """Переставить строки по текущему ключу.

        layoutChanged, а не beginResetModel: сброс гасит выделение, текущий
        индекс и позицию прокрутки — а строка, на которой стоит переводчик,
        обязана остаться выбранной и видимой.
        """
        if not self._rows:
            return
        self.layoutAboutToBeChanged.emit()
        old = [i for i in self.persistentIndexList() if i.isValid()]
        pinned = [(self._rows[i.row()]["id"], i.column()) for i in old]
        self._rows = self._sorted_rows()
        self._reindex()
        self.changePersistentIndexList(
            old, [self.index(self._row_by_id[uid], col) for uid, col in pinned])
        self.layoutChanged.emit()

    def _sorted_rows(self) -> list[sqlite3.Row]:
        nat = self._natural_rank
        if self._sort is None:
            return sorted(self._rows, key=lambda r: nat[r["id"]])
        column, descending = self._sort
        key = self._sort_key(column)
        # Естественный ранг вторым элементом: строки с одинаковым ключом (весь
        # файл при сортировке по имени файла) остаются в порядке строк файла,
        # а не как ляжет.
        return sorted(self._rows, key=lambda r: (key(r), nat[r["id"]]),
                      reverse=descending)

    def _sort_key(self, column: int):
        """Ключ сортировки колонки.

        У служебных колонок первый клик означает «сверху то, что требует
        внимания», а не алфавит: статус идёт в порядке работы переводчика,
        правки — от смысловых к косметическим, замечания — от многих к
        немногим. Второй клик переворачивает.
        """
        if column == COL_KEY:
            return lambda r: _text_key(r["key"])
        if column == COL_FILE:
            return lambda r: _text_key(r["rel_path"])
        if column == COL_EN:
            return lambda r: _text_key(r["en_text"])
        if column == COL_RU:
            return lambda r: _text_key(r["ru_text"])
        if column == COL_STATUS:
            return lambda r: (STATUS_RANK.get(r["status"], len(STATUS_RANK)),
                              bool(r["is_deleted"]))
        if column == COL_CHANGE:
            return lambda r: _CHANGE_RANK.get(r["change_kind"] or "", 2)
        if column == COL_ISSUES:
            # more issues first; on an equal count the rows holding errors come first
            return lambda r: tuple(-n for n in self._issue_rank.get(r["id"], (0, 0)))
        return lambda r: 0

    def refresh_row(self, unit_id: int) -> None:
        """Refresh one row after a save, without a full reload."""
        i = self._row_by_id.get(unit_id)
        if i is None:
            return
        self.recheck_unit(unit_id)
        row = self.conn.execute(
            """SELECT u.id, u.key, f.rel_path, u.en_text, u.ru_text, u.status,
                      u.is_deleted, u.file_id, u.change_kind, u.prev_en_text,
                      u.qa_hash, u.qa_codes
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
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return translate("UnitsTable", COLUMNS[section])
        if role == Qt.ToolTipRole:
            hint = SORT_HINTS.get(section)
            if hint is None:
                return None
            hint = translate("UnitsTable", hint)
            if section == COL_ISSUES:
                return hint
            cycle = translate("UnitsTable", SORT_CYCLE_HINT)
            return f"{hint}.\n{cycle}"
        return None

    def retranslate(self) -> None:
        """Re-read the header in the new language.

        The row data is left alone: that is the text of the mod, not of the
        interface. The statuses are interface text, though — the common
        dataChanged repaints those.
        """
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(COLUMNS) - 1)
        if self._rows:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(len(self._rows) - 1, len(COLUMNS) - 1))

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
                return translate("UnitsTable", mark[1]) if mark else None
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
            has_error = self._issue_rank.get(r["id"], (0, 0))[1] > 0
            if role == Qt.DisplayRole:
                return str(len(codes)) if codes else ""
            if role == Qt.ToolTipRole and codes:
                rules = rules_state.ruleset()
                return "\n".join(f"• {rules.message(c)}" for c in codes)
            if role == Qt.ForegroundRole and codes:
                return theme.qcolor(f"issue.{_worst_severity(codes)}")
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
                # the letter glyphs are translated together with the header: otherwise the
                # Chinese interface would keep Latin letters in the column
                return translate("UnitsTable", glyph)
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
            if role == Qt.ToolTipRole:
                return translate("UnitsTable", tip)
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
                label = statuses_mod.label(r["status"])
                deleted = translate("UnitsTable", "deleted")
                return f"{label} ({deleted})" if r["is_deleted"] else label
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
        # deleted rows are muted: on a dark theme «darker» is unreadable, so there we
        # lighten them instead
        return (c.lighter(130) if theme.is_dark() else c.darker(115)) \
            if r["is_deleted"] else c

    @staticmethod
    def _quick_applicable(r: sqlite3.Row, target: Status) -> bool:
        """Whether a quick button applies to a row; if not, the glyph is muted."""
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
        """The raw, untruncated text of a cell, for copying."""
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
            return statuses_mod.label(r["status"])
        if col == COL_CHANGE:
            return r["change_kind"] or ""
        if col == COL_ISSUES:
            rules = rules_state.ruleset()
            return "; ".join(rules.message(c) for c in self._issues.get(r["id"], []))
        return ""

    def row_data(self, row: int) -> sqlite3.Row | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    # --- navigation helpers ---

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
        self.setAlternatingRowColors(False)
        self.horizontalHeader().setStretchLastSection(False)
        self._apply_prefs()
        prefs.on_change(self._on_pref_changed)

    def _on_pref_changed(self, key: str) -> None:
        global MAX_CELL

        if key == "editor/cell_limit":
            MAX_CELL = prefs.get(key)
            self.viewport().update()
        elif key in ("editor/row_height", "editor/show_grid"):
            self._apply_prefs()

    def _apply_prefs(self) -> None:
        self.verticalHeader().setDefaultSectionSize(prefs.get("editor/row_height"))
        self.setShowGrid(prefs.get("editor/show_grid"))

    def enable_header_sorting(self, on_click) -> None:
        """A click on a header sorts; ✓ ✗ C I stay buttons.

        `setSortingEnabled` is deliberately left off — see `gui/sorting.py`.
        """
        header = self.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(on_click)

    def show_sort_indicator(self, spec: tuple[int, bool] | None) -> None:
        header = self.horizontalHeader()
        if spec is None:
            header.setSortIndicatorShown(False)
            return
        column, descending = spec
        header.setSortIndicatorShown(True)
        header.setSortIndicator(
            column, Qt.DescendingOrder if descending else Qt.AscendingOrder)

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
        self.restore_column_widths()

    # --- column widths ---
    #
    # Only the columns that can actually be dragged are saved, that is, the
    # `Interactive` ones. A `Stretch` width is computed from the window and a
    # `Fixed` one is constant — recording those would one day restore a stretched
    # column at the fixed width of a past window.
    #
    # The key is the English column label rather than its number, by the same
    # argument as for the hidden columns (`view/hidden_columns`). Let somebody
    # insert a column in the middle and the numbers would shift, sending a width
    # to the wrong column.
    #
    # `header.saveState()` is deliberately not used: it drags along the section
    # order together with the sort indicator, while sorting in this window is
    # governed by `SortState` and restored by it — two owners of one indicator
    # drift apart in silence.

    def _resizable_columns(self) -> list[tuple[int, str]]:
        header = self.horizontalHeader()
        return [(col, label) for col, label in DATA_COLUMNS
                if header.sectionResizeMode(col) == QHeaderView.Interactive]

    def save_column_widths(self) -> None:
        widths = {label: self.columnWidth(col)
                  for col, label in self._resizable_columns()
                  if self.columnWidth(col) > 0}
        settings.qsettings().setValue(
            "view/column_widths", "|".join(f"{k}={v}" for k, v in sorted(widths.items())))

    def restore_column_widths(self) -> None:
        raw = settings.qsettings().value("view/column_widths", "")
        if not raw:
            return
        saved: dict[str, int] = {}
        for part in str(raw).split("|"):
            label, _, value = part.partition("=")
            if value.isdigit():
                saved[label] = int(value)
        for col, label in self._resizable_columns():
            width = saved.get(label)
            # Zero and negative values are ignored: such a width hides a column for good,
            # and hiding them is the business of «View → Columns», where it is reversible.
            if width and width > 0:
                self.setColumnWidth(col, width)

    def selected_unit_ids(self) -> list[int]:
        model = self.model()
        return [model.unit_id_at(i.row()) for i in self.selectionModel().selectedRows()]
