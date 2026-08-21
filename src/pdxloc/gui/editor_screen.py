"""The editor screen: the file tree, the filters, the table and the detail panel."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QSplitter, QVBoxLayout, QWidget,
)

from pdxloc import project
from pdxloc.core import statuses as statuses_mod
from pdxloc.core import unit_ops
from pdxloc.core.i18n import fill, translate
from pdxloc.core.stats import file_stats
from pdxloc.core.statuses import STATUS_ORDER, Status
from pdxloc.gui import actions as act_spec
from pdxloc.gui import shell
from pdxloc.gui.detail_pane import DetailPane
from pdxloc.gui.file_tree import FileTreePanel
from pdxloc.gui.units_model import (
    COL_QS_FIRST, QUICK_COLS, UnitsTableModel, UnitsTableView,
)
from pdxloc.gui.view_state import ViewState

CTX = "Editor"


class FilterBar(QWidget):
    """The filter bar is a shop window onto ViewState and holds no state of its own."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state: ViewState | None = None
        self._syncing = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.status_combo = QComboBox()
        self.status_combo.addItem("", None)
        # the order is shared with the status-bar chips and the «Filters» menu entries
        for s in STATUS_ORDER:
            self.status_combo.addItem("", s.value)
        layout.addWidget(self.status_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit, 1)

        self.issues_check = QCheckBox()
        layout.addWidget(self.issues_check)

        self.deleted_check = QCheckBox()
        layout.addWidget(self.deleted_check)

        self.retranslate()

        self.status_combo.currentIndexChanged.connect(self._push_status)
        self.deleted_check.toggled.connect(self._push_deleted)
        self.issues_check.toggled.connect(self._push_issues)
        # the search is debounced, so SQL is not poked on every character
        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self._push_search)
        self.search_edit.textChanged.connect(lambda _: self._debounce.start())

    def retranslate(self) -> None:
        """The filter labels. The item values are left alone: the selection goes by them."""
        self.status_label.setText(translate("Editor", "Status:"))
        self.status_combo.setItemText(0, translate("Editor", "All"))
        for i, s in enumerate(STATUS_ORDER, start=1):
            self.status_combo.setItemText(i, statuses_mod.label(s))
        self.search_edit.setPlaceholderText(
            translate("Editor", "Search: key / EN / RU…  (Ctrl+F)"))
        self.issues_check.setText(translate("Editor", "with issues"))
        self.issues_check.setToolTip(translate(
            "Editor", "Show only rows the check has questions about"))
        self.deleted_check.setText(translate("Editor", "deleted"))

    def bind(self, state: ViewState) -> None:
        self._state = state
        state.changed.connect(self.sync)
        self.sync()

    def sync(self) -> None:
        """Show the state, whoever changed it — a chip, a menu or a header."""
        if self._state is None:
            return
        self._syncing = True
        try:
            self.status_combo.setCurrentIndex(
                max(self.status_combo.findData(self._state.status), 0))
            self.issues_check.setChecked(self._state.only_issues)
            self.deleted_check.setChecked(self._state.show_deleted)
            if self.search_edit.text().strip() != self._state.search:
                self.search_edit.setText(self._state.search)
        finally:
            self._syncing = False

    def _push_status(self) -> None:
        if not self._syncing and self._state is not None:
            self._state.set_status(self.status_combo.currentData())

    def _push_deleted(self, checked: bool) -> None:
        if not self._syncing and self._state is not None:
            self._state.set_show_deleted(checked)

    def _push_issues(self, checked: bool) -> None:
        if not self._syncing and self._state is not None:
            self._state.set_only_issues(checked)

    def _push_search(self) -> None:
        if not self._syncing and self._state is not None:
            self._state.set_search(self.search_edit.text())

    def status(self) -> str | None:
        return self.status_combo.currentData()


class EditorScreen(QWidget):
    statsChanged = Signal()      # после сохранений — обновить статус-бар/чипы
    manageTmRequested = Signal() # открыть менеджер памяти переводов
    selectionChanged = Signal(int)   # сколько строк выделено — для статус-бара
    filtersChanged = Signal()    # фильтр сменили — подсветить все его витрины

    def __init__(self, conn: sqlite3.Connection | None = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id: int | None = None
        self.actions: act_spec.ActionRegistry | None = None
        self._syncing = False    # a guard against the «widget → action → widget» loop
        self.state = ViewState(self)

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

        self.filter_bar.bind(self.state)
        self.table.enable_header_sorting(self._on_header_clicked)
        self.state.changed.connect(self._reload)
        self.state.sortChanged.connect(self._resort)
        self.file_tree.filterSelected.connect(self.state.set_file)
        self.table.selectionModel().currentChanged.connect(self._on_current_changed)
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.selectionChanged.emit(len(self.table.selected_unit_ids())))
        self.table.clicked.connect(self._on_table_clicked)
        self.model.unitSaved.connect(self._on_unit_saved)
        self.detail.saved.connect(self._on_detail_saved)
        self.detail.requestNext.connect(self._goto_next_untranslated)
        self.detail.tm_list.manageRequested.connect(self.manageTmRequested)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

    # --- public ---

    def set_session(self, conn: sqlite3.Connection) -> None:
        """Switch to another project file without rebuilding the widgets."""
        self.conn = conn
        self.model.conn = conn
        self.detail.conn = conn
        self.detail.clear()
        # the glossary lives in the project file, so a new project has its own
        self.detail.reload_glossary()
        self.project_id = None

    def close_session(self) -> None:
        """Let the project go: the connection closes and must not be held on to.

        Without this the editor panel reached into a closed database on its next
        repaint — on a change of theme, for instance — and brought the window
        down.
        """
        self.project_id = None
        self.detail.clear()
        # the terms of a closed project must not be highlighted in the next one: the
        # connection is already gone, and reload_glossary honestly leaves an empty
        # dictionary
        self.detail.reload_glossary()
        self.model.clear()
        self.file_tree.populate([])

    def open_project(self, project_id: int) -> None:
        self.project_id = project_id
        self.state.file_rel = self.state.file_prefix = None
        self.file_tree.populate(file_stats(self.conn, project_id))
        self._reload()

    def refresh_issues(self) -> None:
        """Re-read the issues, for instance after «not an error» marks in the report."""
        if self.project_id is not None:
            self._reload()

    def retranslate(self) -> None:
        """The screen lives for the whole session, so its labels are replaced in place."""
        self.filter_bar.retranslate()
        self.model.retranslate()
        self.detail.retranslate()
        self.file_tree.retranslate()

    def current_pair(self) -> tuple[str, str] | None:
        """The original and the translation of the selected row, for «Check on a pair».

        Taken from the already loaded model rather than from the database: the
        rules window is opened precisely to look at the row currently in front of
        you, not at its state on disk.
        """
        if self.detail.unit_id is None:
            return None
        row_index = self.model.row_of_unit(self.detail.unit_id)
        if row_index is None:
            return None
        row = self.model.row_data(row_index)
        return (row["en_text"] or "", row["ru_text"] or "") if row else None

    def refresh_current(self) -> None:
        """Re-read the current row, for instance after the set of databases changed."""
        if self.detail.unit_id is not None:
            self.detail.load_unit(self.detail.unit_id)

    def focus_search(self) -> None:
        """Put the cursor in the search box: the same as Ctrl+F, from the menu and the
        toolbar."""
        self.filter_bar.search_edit.setFocus()
        self.filter_bar.search_edit.selectAll()

    def goto_next_untranslated(self) -> None:
        self._goto_next_untranslated()

    def set_status_of_selection(self, status: Status) -> None:
        self._bulk_status(status)

    def jump_to_unit(self, unit_id: int) -> None:
        row = self.model.row_of_unit(unit_id)
        if row is None:
            self.reset_filters()      # clear the filters and try again
            row = self.model.row_of_unit(unit_id)
        if row is not None:
            self._select_row(row)

    def set_status_filter(self, status_value: str | None) -> None:
        """Set a status filter, from a chip, a menu or the scan summary."""
        self.state.set_status(status_value)

    # --- filters and loading ---

    def _on_header_clicked(self, column: int) -> None:
        """A click on a header sorts — except on the button columns ✓ ✗ C I.

        Those are controls rather than data: the «value» of such a cell is derived
        from the status, that is, a strictly worse version of the neighbouring
        «Status» column. And more to the point, while ticking ✓ down a list, a
        miss of 26 pixels upwards would reshuffle the rows right under the cursor
        and the next click would land on the wrong one. The price of that mistake
        is corrupted statuses.
        """
        if column >= COL_QS_FIRST:
            return
        self.state.click_column(column)

    def _reload(self) -> None:
        self._sync_filter_actions()
        self.filtersChanged.emit()
        if self.project_id is None:
            return
        selected = self.detail.unit_id
        self.model.set_sort(self.state.sort_spec)
        self.model.reload(self.project_id, self.state.filters())
        self.table.show_sort_indicator(self.state.sort_spec)
        if selected is not None:
            row = self.model.row_of_unit(selected)
            if row is not None:
                self._select_row(row)
                return
        if self.model.rowCount():
            self._select_row(0)
        else:
            self.detail.clear()

    def _resort(self) -> None:
        """Сменился только порядок — перезапрашивать базу незачем.

        Полная перезагрузка стоит SQL-запроса и пересчёта всех проверок
        качества; на клик по заголовку это непозволительно дорого.
        """
        self._sync_filter_actions()
        self.filtersChanged.emit()
        self.model.set_sort(self.state.sort_spec)
        self.table.show_sort_indicator(self.state.sort_spec)
        if self.detail.unit_id is not None:
            row = self.model.row_of_unit(self.detail.unit_id)
            if row is not None:
                self.table.scrollTo(self.model.index(row, 0))

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
        if self.state.status or self.state.only_issues:
            # активен фильтр по статусу или замечаниям — состав строк мог
            # измениться, точечным обновлением строк не обойтись
            self._reload()
        else:
            for uid in unit_ids:
                self.model.refresh_row(uid)
        if self.detail.unit_id in unit_ids:
            self.detail.load_unit(self.detail.unit_id)
        self.statsChanged.emit()
        self._refresh_tree()

    # --- контекстное меню и действия ---

    def bind_actions(self, registry: act_spec.ActionRegistry) -> None:
        """Подключить команды экрана к общему реестру.

        Свои QAction экран больше не заводит: раньше «Подтвердить» жило и здесь,
        и в тулбаре главного окна двумя разными объектами — с разным текстом и
        разными клавишами.
        """
        self.actions = registry
        c = registry.connect
        c("copy_cell", self._copy_cell)
        c("paste_ru", self._paste_ru)
        c("copy_key", self._copy_key)
        c("reset", self._bulk_reset)
        c("save_row", self.detail.save)
        c("ru_eq_en", self._ru_eq_en)
        c("from_tm", self._from_tm)
        c("mt", self._machine_translate)
        c("apply_same", self._apply_same)
        c("validate", lambda: self._bulk_status(Status.REVIEWED))
        c("unvalidate", lambda: self._bulk_status(Status.TRANSLATED))
        c("custom", lambda: self._bulk_status(Status.CUSTOM))
        c("ignore", lambda: self._bulk_status(Status.IGNORED))
        c("next_untranslated", self._goto_next_untranslated)
        c("prev_row", lambda: self._move(-1))
        c("next_row", lambda: self._move(1))
        c("save_and_next", self._save_and_next)
        c("find", self.focus_search)
        c("only_issues", self._on_only_issues_action)
        c("show_deleted", self._on_show_deleted_action)
        c("reset_filters", self.reset_filters)
        c("open_file", self._open_in_explorer)
        c("concordance", self._show_concordance)
        self._sync_filter_actions()

    # --- фильтры: витрины одного состояния ---

    def _on_only_issues_action(self, checked: bool) -> None:
        if not self._syncing:
            self.state.set_only_issues(checked)

    def _on_show_deleted_action(self, checked: bool) -> None:
        if not self._syncing:
            self.state.set_show_deleted(checked)

    def reset_filters(self) -> None:
        """Clear the status, file and search filters; the sort order stays."""
        self.file_tree.clear_selection()
        self.state.reset_filters()

    def _sync_filter_actions(self) -> None:
        """The menu entries mirror the state, whoever changed it.

        Without this the «Only with issues» tick lied every time the filter was
        set through the checkbox, a column header or the «Show» button in the scan
        summary.
        """
        if self.actions is None:
            return
        self._syncing = True
        try:
            self.actions["only_issues"].setChecked(self.state.only_issues)
            self.actions["show_deleted"].setChecked(self.state.show_deleted)
        finally:
            self._syncing = False

    def context_menu(self) -> QMenu | None:
        """Build the table context menu; showing it is separate, so it can be tested."""
        if self.actions is None:
            return None
        menu = QMenu(self.table)
        n = len(self.table.selected_unit_ids())
        if n > 1:
            # The reach of a bulk operation is shown as the menu title. The counter used to
            # be appended to the text of the actions themselves and stripped by a hard-coded
            # list of strings — rename an entry and it kept the «(12 rows)» tail forever.
            head = menu.addAction(
                fill(translate("Editor", "Rows selected: %1"), n))
            head.setEnabled(False)
            menu.addSeparator()
        self.actions.fill_menu(menu, act_spec.CONTEXT)
        return menu

    def _show_context_menu(self, pos) -> None:
        menu = self.context_menu()
        if menu is not None:
            menu.exec(self.table.viewport().mapToGlobal(pos))

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
            QMessageBox.information(
                self, translate("Editor", "Apply to all"),
                translate("Editor",
                          "There are no untranslated rows with the same EN text."))
            return
        answer = QMessageBox.question(
            self, translate("Editor", "Apply to all"),
            fill(translate("Editor",
                           "Apply this translation to %1 rows with the same "
                           "English text?"), n))
        if answer == QMessageBox.Yes:
            # as a batch rather than one by one: the edit touches hundreds of rows, and
            # undoing it must take one Ctrl+Z
            batch = unit_ops.new_batch_id()
            targets = unit_ops.apply_to_same_en(self.conn, uid, batch_id=batch)
            self._after_change(targets)

    def _from_tm(self) -> None:
        uid = self._current_unit_id()
        if uid is not None and unit_ops.apply_best_tm(self.conn, uid):
            self.model.refresh_row(uid)
            self._after_change([uid])

    def _machine_translate(self) -> None:
        """Translate the current row through a service. The result is «Machine»."""
        from pdxloc.gui import mt_worker, prefs

        uid = self._current_unit_id()
        if uid is None or getattr(self, "_mt_thread", None) is not None:
            return
        provider = prefs.get("mt/provider")
        if provider == "none":
            self.window().statusBar().showMessage(translate(
                "Editor", "No translation service is set up — «File → "
                          "Preferences → Machine translation»"), 6000)
            return
        row = self.conn.execute(
            "SELECT en_text FROM units WHERE id = ?", (uid,)).fetchone()
        if row is None or not (row["en_text"] or "").strip():
            return

        langs = project.languages(self.conn, self.project_id)
        self._mt_worker = mt_worker.RowWorker(
            uid, row["en_text"], provider, mt_worker.config_from_prefs(provider),
            langs.src_locale, langs.tgt_locale)
        self._mt_worker.finished.connect(self._on_machine_translated)
        self._mt_worker.failed.connect(self._on_machine_failed)
        self._mt_thread = mt_worker.start(self._mt_worker, self)
        self._mt_worker.finished.connect(self._mt_thread.quit)
        self._mt_worker.failed.connect(self._mt_thread.quit)
        self._mt_thread.finished.connect(self._on_machine_thread_done)
        self.window().statusBar().showMessage(
            translate("Editor", "Translating…"), 0)
        self._mt_thread.start()

    def _on_machine_translated(self, unit_id: int, text: str, lost: list) -> None:
        # We write here rather than on the thread: the connection belongs to this object
        # and must not be dragged between threads.
        batch = unit_ops.new_batch_id()
        unit_ops.save_machine_text(self.conn, unit_id, text, batch_id=batch)
        self.model.refresh_row(unit_id)
        self._after_change([unit_id])
        self.window().statusBar().showMessage(
            translate("Editor", "The translation lost a placeholder — check the row")
            if lost else
            translate("Editor", "Translated by the service — Ctrl+Z undoes it"),
            6000)

    def _on_machine_failed(self, message: str) -> None:
        self.window().statusBar().showMessage(message, 8000)

    def _on_machine_thread_done(self) -> None:
        self._mt_thread = None
        self._mt_worker = None

    def _bulk_status(self, status: Status) -> None:
        ids = self.table.selected_unit_ids()
        ids = [i for i in ids if i is not None]
        if not ids:
            return
        changed = unit_ops.set_status(self.conn, ids, status)
        if changed < len(ids) and status in (Status.REVIEWED, Status.CUSTOM, Status.TRANSLATED):
            self.window().statusBar().showMessage(
                fill(translate("Editor",
                               "Changed %1 of %2 (a status is not set without a "
                               "translation)"), changed, len(ids)), 4000)
        self._after_change(ids)

    def _bulk_reset(self) -> None:
        ids = [i for i in self.table.selected_unit_ids() if i is not None]
        if not ids:
            return
        if len(ids) > 1:
            answer = QMessageBox.question(
                self, translate("Editor", "Reset translation"),
            fill(translate("Editor", "Reset the translation of %1 rows?"), len(ids)))
            if answer != QMessageBox.Yes:
                return
        unit_ops.reset_translation(self.conn, ids)
        self._after_change(ids)

    def _show_concordance(self) -> None:
        """A memory search for the selected piece of the original.

        A selection in the original field outweighs the whole row: what usually
        needs looking up is one name or one turn of phrase, not the entire
        sentence.
        """
        from pdxloc.gui.concordance_dialog import ConcordanceDialog

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
        shell.reveal(Path(proj["en_root"]) / r["rel_path"])

    # --- navigation ---

    def _save_and_next(self) -> None:
        self.detail.save()
        self._goto_next_untranslated()

    def _goto_next_untranslated(self) -> None:
        index = self.table.selectionModel().currentIndex()
        current = index.row() if index.isValid() else -1
        # machine translation is unfinished work as well: without it the rows filled in
        # by the machine would be unreachable by the main traversal key
        nxt = self.model.next_row_with_status(
            current, {Status.UNTRANSLATED.value, Status.MACHINE.value,
                      Status.AUTO.value, Status.STALE.value})
        if nxt is not None:
            self._select_row(nxt)

    def _move(self, delta: int) -> None:
        index = self.table.selectionModel().currentIndex()
        current = index.row() if index.isValid() else 0
        target = max(0, min(self.model.rowCount() - 1, current + delta))
        self._select_row(target)
