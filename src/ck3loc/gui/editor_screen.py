"""Экран редактора: дерево файлов | фильтры + таблица + детальная панель."""
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QSplitter, QVBoxLayout, QWidget,
)

from ck3loc.core import unit_ops
from ck3loc.core.stats import file_stats
from ck3loc.core.statuses import STATUS_LABELS, Status
from ck3loc.gui.detail_pane import DetailPane
from ck3loc.gui.file_tree import FileTreePanel
from ck3loc.gui.units_model import (
    COL_QS_FIRST, COL_RU, QUICK_COLS, UnitFilters, UnitsTableModel, UnitsTableView,
)


class FilterBar(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Статус:"))
        self.status_combo = QComboBox()
        self.status_combo.addItem("Все", None)
        for s in Status:
            self.status_combo.addItem(STATUS_LABELS[s], s.value)
        layout.addWidget(self.status_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск: ключ / EN / RU…  (Ctrl+F)")
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit, 1)

        self.issues_check = QCheckBox("с замечаниями")
        self.issues_check.setToolTip("Показать только строки, к которым есть вопросы у проверки")
        layout.addWidget(self.issues_check)

        self.deleted_check = QCheckBox("удалённые")
        layout.addWidget(self.deleted_check)

        self.status_combo.currentIndexChanged.connect(self.changed)
        self.deleted_check.toggled.connect(self.changed)
        self.issues_check.toggled.connect(self.changed)
        # поиск — с дебаунсом, чтобы не дёргать SQL на каждый символ
        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self.changed)
        self.search_edit.textChanged.connect(lambda _: self._debounce.start())

    def filters(self) -> UnitFilters:
        return UnitFilters(
            status=self.status_combo.currentData(),
            search=self.search_edit.text().strip(),
            show_deleted=self.deleted_check.isChecked(),
            only_issues=self.issues_check.isChecked(),
        )

    def set_status(self, status_value: str | None) -> None:
        i = self.status_combo.findData(status_value)
        self.status_combo.setCurrentIndex(max(i, 0))

    def reset(self) -> None:
        self.blockSignals(True)
        self.status_combo.setCurrentIndex(0)
        self.search_edit.clear()
        self.deleted_check.setChecked(False)
        self.issues_check.setChecked(False)
        self.blockSignals(False)
        self.changed.emit()


class EditorScreen(QWidget):
    statsChanged = Signal()      # после сохранений — обновить статус-бар/чипы
    manageTmRequested = Signal() # открыть менеджер памяти переводов
    selectionChanged = Signal(int)   # сколько строк выделено — для статус-бара

    def __init__(self, conn: sqlite3.Connection | None = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id: int | None = None
        self._file_filter: tuple[str | None, str | None] = (None, None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.file_tree = FileTreePanel()
        self.file_tree.setMinimumWidth(180)

        self.filter_bar = FilterBar()

        self.model = UnitsTableModel(conn)
        self.table = UnitsTableView()
        self.table.setModel(self.model)
        self.table.configure_columns()

        self.detail = DetailPane(conn)

        right = QWidget()
        rlayout = QVBoxLayout(right)
        rlayout.setContentsMargins(0, 0, 0, 0)
        rlayout.addWidget(self.filter_bar)
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(self.table)
        vsplit.addWidget(self.detail)
        vsplit.setStretchFactor(0, 3)
        vsplit.setStretchFactor(1, 2)
        rlayout.addWidget(vsplit, 1)

        hsplit = QSplitter(Qt.Horizontal)
        hsplit.addWidget(self.file_tree)
        hsplit.addWidget(right)
        hsplit.setStretchFactor(0, 0)
        hsplit.setStretchFactor(1, 1)
        hsplit.setSizes([230, 1000])
        layout.addWidget(hsplit, 1)

        self.filter_bar.changed.connect(self._reload)
        self.file_tree.filterSelected.connect(self._on_tree_filter)
        self.table.selectionModel().currentChanged.connect(self._on_current_changed)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.selectionChanged.emit(len(self.table.selected_unit_ids())))
        self.table.clicked.connect(self._on_table_clicked)
        self.model.unitSaved.connect(self._on_unit_saved)
        self.detail.saved.connect(self._on_detail_saved)
        self.detail.requestNext.connect(self._goto_next_untranslated)
        self.detail.tm_list.manageRequested.connect(self.manageTmRequested)

        self._build_actions()
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self._shortcuts()

    # --- публичное ---

    def set_session(self, conn: sqlite3.Connection) -> None:
        """Переключиться на другой файл проекта без пересоздания виджетов."""
        self.conn = conn
        self.model.conn = conn
        self.detail.conn = conn
        self.detail.clear()
        self.project_id = None

    def close_session(self) -> None:
        """Отпустить проект: соединение закрывается, держаться за него нельзя.

        Без этого панель редактора при следующей перерисовке (например, при
        смене темы) лезла в закрытую базу и роняла окно.
        """
        self.project_id = None
        self.detail.clear()
        self.model.clear()
        self.file_tree.populate([])

    def open_project(self, project_id: int) -> None:
        self.project_id = project_id
        self._file_filter = (None, None)
        self.file_tree.populate(file_stats(self.conn, project_id))
        self._reload()

    def refresh_issues(self) -> None:
        """Перечитать замечания — например, после пометок «не ошибка» в отчёте."""
        if self.project_id is not None:
            self._reload()

    def refresh_current(self) -> None:
        """Перечитать текущую строку — например, после смены набора баз."""
        if self.detail.unit_id is not None:
            self.detail.load_unit(self.detail.unit_id)

    def focus_search(self) -> None:
        """Курсор в поле поиска — то же, что Ctrl+F, но из меню и панели."""
        self.filter_bar.search_edit.setFocus()
        self.filter_bar.search_edit.selectAll()

    def goto_next_untranslated(self) -> None:
        self._goto_next_untranslated()

    def set_status_of_selection(self, status: Status) -> None:
        self._bulk_status(status)

    def jump_to_unit(self, unit_id: int) -> None:
        row = self.model.row_of_unit(unit_id)
        if row is None:
            self.file_tree.clear_selection()
            self._file_filter = (None, None)
            self.filter_bar.reset()   # сбросить фильтры и попробовать снова
            row = self.model.row_of_unit(unit_id)
        if row is not None:
            self._select_row(row)

    def set_status_filter(self, status_value: str | None) -> None:
        self.filter_bar.set_status(status_value)

    # --- фильтры/загрузка ---

    def _current_filters(self) -> UnitFilters:
        f = self.filter_bar.filters()
        f.file_rel, f.file_prefix = self._file_filter
        return f

    def _reload(self) -> None:
        if self.project_id is None:
            return
        selected = self.detail.unit_id
        self.model.reload(self.project_id, self._current_filters())
        if selected is not None:
            row = self.model.row_of_unit(selected)
            if row is not None:
                self._select_row(row)
                return
        if self.model.rowCount():
            self._select_row(0)
        else:
            self.detail.clear()

    def _on_tree_filter(self, file_rel, file_prefix) -> None:
        self._file_filter = (file_rel, file_prefix)
        self._reload()

    def _refresh_tree(self) -> None:
        if self.project_id is not None:
            self.file_tree.update_counts(file_stats(self.conn, self.project_id))

    # --- выделение/клики ---

    def _select_row(self, row: int) -> None:
        index = self.model.index(row, 0)
        self.table.selectionModel().setCurrentIndex(
            index,
            self.table.selectionModel().SelectionFlag.ClearAndSelect
            | self.table.selectionModel().SelectionFlag.Rows,
        )
        self.table.scrollTo(index)

    def _on_current_changed(self, current, _previous) -> None:
        if current.isValid():
            unit_id = self.model.unit_id_at(current.row())
            if unit_id is not None and unit_id != self.detail.unit_id:
                self.detail.load_unit(unit_id)   # detail сам сохранит несохранённое

    def _on_table_clicked(self, index) -> None:
        if index.column() < COL_QS_FIRST:
            return
        r = self.model.row_data(index.row())
        if r is None:
            return
        _, target, _, _ = QUICK_COLS[index.column()]
        if not self.model._quick_applicable(r, target):
            return
        unit_ops.set_status(self.conn, [r["id"]], target)
        self._after_change([r["id"]])

    # --- сохранения ---

    def _on_unit_saved(self, unit_id: int) -> None:
        """Правка в ячейке: синхронизировать детальную панель (иначе её автосейв
        со старым текстом перезапишет свежую правку)."""
        if self.detail.unit_id == unit_id:
            self.detail.load_unit(unit_id)
        self.statsChanged.emit()
        self._refresh_tree()

    def _on_detail_saved(self, unit_id: int) -> None:
        self.model.refresh_row(unit_id)
        self.statsChanged.emit()
        self._refresh_tree()

    def _after_change(self, unit_ids: list[int]) -> None:
        """После bulk-операции: обновить строки/панель/статистику."""
        if self.filter_bar.filters().status:
            # активен фильтр по статусу — состав строк мог измениться
            self._reload()
        else:
            for uid in unit_ids:
                self.model.refresh_row(uid)
        if self.detail.unit_id in unit_ids:
            self.detail.load_unit(self.detail.unit_id)
        self.statsChanged.emit()
        self._refresh_tree()

    # --- контекстное меню и действия ---

    def _build_actions(self) -> None:
        def act(text: str, shortcut: str | None, slot) -> QAction:
            a = QAction(text, self.table)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
                a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            a.triggered.connect(slot)
            self.table.addAction(a)   # хоткей работает и без открытого меню
            return a

        self.act_copy_cell = act("Копировать ячейку", "Ctrl+C", self._copy_cell)
        self.act_paste_ru = act("Вставить в перевод", "Ctrl+V", self._paste_ru)
        self.act_ru_eq_en = act("Перевод = Оригинал", "F8", self._ru_eq_en)
        self.act_apply_same = act("Применить ко всем с таким же EN", "Ctrl+F6", self._apply_same)
        self.act_from_tm = act("Подставить из памяти переводов", "F7", self._from_tm)
        self.act_validate = act("Подтвердить", "F10",
                                lambda: self._bulk_status(Status.REVIEWED))
        self.act_unvalidate = act("Снять подтверждение", "Shift+F10",
                                  lambda: self._bulk_status(Status.TRANSLATED))
        self.act_custom = act("Кастомный статус", "Ctrl+F10",
                              lambda: self._bulk_status(Status.CUSTOM))
        self.act_ignore = act("Игнорировать", "Ctrl+Shift+F10",
                              lambda: self._bulk_status(Status.IGNORED))
        self.act_reset = act("Сбросить перевод", None, self._bulk_reset)
        self.act_copy_key = act("Копировать ключ", None, self._copy_key)
        self.act_concordance = act("Как переводили это раньше…", "Ctrl+Shift+F",
                                   self._show_concordance)
        self.act_open_file = act("Открыть оригинал в проводнике", None, self._open_in_explorer)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self.table)
        menu.addAction(self.act_copy_cell)
        menu.addAction(self.act_paste_ru)
        menu.addSeparator()
        menu.addAction(self.act_ru_eq_en)
        menu.addAction(self.act_apply_same)
        menu.addAction(self.act_from_tm)
        menu.addSeparator()
        menu.addAction(self.act_validate)
        menu.addAction(self.act_unvalidate)
        menu.addAction(self.act_custom)
        menu.addAction(self.act_ignore)
        menu.addSeparator()
        menu.addAction(self.act_reset)
        menu.addSeparator()
        menu.addAction(self.act_copy_key)
        menu.addAction(self.act_concordance)
        menu.addAction(self.act_open_file)
        n = len(self.table.selected_unit_ids())
        if n > 1:
            for a in (self.act_validate, self.act_unvalidate, self.act_custom,
                      self.act_ignore, self.act_reset):
                a.setText(a.text().split(" (")[0] + f" ({n} строк)")
        menu.exec(self.table.viewport().mapToGlobal(pos))
        # вернуть тексты без счётчика
        for a, t in ((self.act_validate, "Подтвердить"),
                     (self.act_unvalidate, "Снять подтверждение"),
                     (self.act_custom, "Кастомный статус"),
                     (self.act_ignore, "Игнорировать"),
                     (self.act_reset, "Сбросить перевод")):
            a.setText(t)

    def _current_unit_id(self) -> int | None:
        index = self.table.selectionModel().currentIndex()
        return self.model.unit_id_at(index.row()) if index.isValid() else None

    def _copy_cell(self) -> None:
        index = self.table.selectionModel().currentIndex()
        if index.isValid():
            QGuiApplication.clipboard().setText(
                self.model.raw_cell(index.row(), index.column()))

    def _copy_key(self) -> None:
        index = self.table.selectionModel().currentIndex()
        if index.isValid():
            QGuiApplication.clipboard().setText(self.model.raw_cell(index.row(), 0))

    def _paste_ru(self) -> None:
        uid = self._current_unit_id()
        text = QGuiApplication.clipboard().text()
        if uid is not None and text:
            unit_ops.save_ru_text(self.conn, uid, text)
            self.model.refresh_row(uid)
            self._after_change([uid])

    def _ru_eq_en(self) -> None:
        uid = self._current_unit_id()
        if uid is None:
            return
        row = self.conn.execute("SELECT en_text FROM units WHERE id = ?", (uid,)).fetchone()
        if row and row["en_text"]:
            unit_ops.save_ru_text(self.conn, uid, row["en_text"])
            self.model.refresh_row(uid)
            self._after_change([uid])

    def _apply_same(self) -> None:
        uid = self._current_unit_id()
        if uid is None:
            return
        n = unit_ops.count_same_en(self.conn, uid)
        if n == 0:
            QMessageBox.information(self, "Применить ко всем",
                                    "Непереведённых строк с таким же EN-текстом нет.")
            return
        answer = QMessageBox.question(
            self, "Применить ко всем",
            f"Применить этот перевод к {n} строкам с таким же английским текстом?")
        if answer == QMessageBox.Yes:
            targets = unit_ops.apply_to_same_en(self.conn, uid)
            self._after_change(targets)

    def _from_tm(self) -> None:
        uid = self._current_unit_id()
        if uid is not None and unit_ops.apply_best_tm(self.conn, uid):
            self.model.refresh_row(uid)
            self._after_change([uid])

    def _bulk_status(self, status: Status) -> None:
        ids = self.table.selected_unit_ids()
        ids = [i for i in ids if i is not None]
        if not ids:
            return
        changed = unit_ops.set_status(self.conn, ids, status)
        if changed < len(ids) and status in (Status.REVIEWED, Status.CUSTOM, Status.TRANSLATED):
            self.window().statusBar().showMessage(
                f"Изменено {changed} из {len(ids)} (без перевода статус не ставится)", 4000)
        self._after_change(ids)

    def _bulk_reset(self) -> None:
        ids = [i for i in self.table.selected_unit_ids() if i is not None]
        if not ids:
            return
        if len(ids) > 1:
            answer = QMessageBox.question(
                self, "Сбросить перевод", f"Сбросить перевод {len(ids)} строк?")
            if answer != QMessageBox.Yes:
                return
        unit_ops.reset_translation(self.conn, ids)
        self._after_change(ids)

    def _show_concordance(self) -> None:
        """Поиск по памяти для выделенного куска оригинала.

        Выделение в поле оригинала важнее строки целиком: искать обычно нужно
        одно имя или оборот, а не всю фразу.
        """
        from ck3loc.gui.concordance_dialog import ConcordanceDialog

        if self.conn is None:
            return
        fragment = self.detail.en_view.textCursor().selectedText().strip()
        if not fragment:
            index = self.table.selectionModel().currentIndex()
            r = self.model.row_data(index.row()) if index.isValid() else None
            fragment = (r["en_text"] or "")[:80] if r is not None else ""
        ConcordanceDialog(self.conn, fragment, self).exec()

    def _open_in_explorer(self) -> None:
        index = self.table.selectionModel().currentIndex()
        r = self.model.row_data(index.row()) if index.isValid() else None
        if r is None or self.project_id is None:
            return
        proj = self.conn.execute(
            "SELECT en_root FROM projects WHERE id = ?", (self.project_id,)).fetchone()
        path = Path(proj["en_root"]) / r["rel_path"]
        if path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])

    # --- навигация ---

    def _shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._save_and_next)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._save_and_next)
        QShortcut(QKeySequence("Ctrl+Down"), self, activated=lambda: self._move(1))
        QShortcut(QKeySequence("Ctrl+Up"), self, activated=lambda: self._move(-1))
        QShortcut(QKeySequence("Ctrl+F"), self,
                  activated=lambda: self.filter_bar.search_edit.setFocus())

    def _save_and_next(self) -> None:
        self.detail.save()
        self._goto_next_untranslated()

    def _goto_next_untranslated(self) -> None:
        index = self.table.selectionModel().currentIndex()
        current = index.row() if index.isValid() else -1
        nxt = self.model.next_row_with_status(
            current, {Status.UNTRANSLATED.value, Status.AUTO.value, Status.STALE.value})
        if nxt is not None:
            self._select_row(nxt)

    def _move(self, delta: int) -> None:
        index = self.table.selectionModel().currentIndex()
        current = index.row() if index.isValid() else 0
        target = max(0, min(self.model.rowCount() - 1, current + delta))
        self._select_row(target)
