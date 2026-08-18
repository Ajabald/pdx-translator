"""Окно глоссария (Shift+F9): термины и кандидаты в них.

Форма повторяет окно памяти переводов: вкладки плюс общая нижняя полоса, а
состояние активной вкладки живёт в ней, а не рядом с кнопками, к которым не
относится. Контракт вкладки тот же — `statusChanged`, `status_text`,
`shutdown`.

Разделение на две вкладки не косметическое. «Термины» — это то, что уже решено
и что подсвечивается в поле оригинала; «Кандидаты» — очередь на разбор, где
работают сверху вниз и где счёт с охватом говорят, чему верить. Смешать их в
одну таблицу значило бы показывать переводчику предположение и решение одним
цветом.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QObject, Qt, QTimer, Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView,
    QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTableView,
    QTabWidget, QVBoxLayout, QWidget,
)

from pdxloc.core import glossary
from pdxloc.core.glossary import APPROVED, CANDIDATE, REJECTED
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.gui import mt_worker
from pdxloc.gui.sorting import SortState
from pdxloc.gui.widgets import HintLabel

TERM_COLUMNS = (
    QT_TRANSLATE_NOOP("Glossary", "Original"),
    QT_TRANSLATE_NOOP("Glossary", "Translation"),
    QT_TRANSLATE_NOOP("Glossary", "Note"),
)
T_EN, T_RU, T_NOTE = range(3)

CANDIDATE_COLUMNS = (
    QT_TRANSLATE_NOOP("Glossary", "Original"),
    QT_TRANSLATE_NOOP("Glossary", "Translation"),
    QT_TRANSLATE_NOOP("Glossary", "Confidence"),
    QT_TRANSLATE_NOOP("Glossary", "Pairs"),
)
C_EN, C_RU, C_SCORE, C_PAIRS = range(4)


class _ExtractWorker(QObject):
    """Прогон статистики в своём потоке и со своим соединением.

    Соединение только на чтение и своё: правило потоков в этом приложении —
    одно соединение на поток, а корпус бывает в четверть миллиона записей, и
    держать на нём главный поток нельзя.
    """
    done = Signal(list)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, path, tm_paths, min_pairs: int, min_score: float,
                 proper_only: bool):
        super().__init__()
        self._path = path
        self._tm_paths = tm_paths
        self._min_pairs = min_pairs
        self._min_score = min_score
        self._proper_only = proper_only
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from pdxloc import db as db_module
        from pdxloc import project as project_mod

        conn = None
        try:
            conn = project_mod.read_only_connection(self._path)
            db_module.register_functions(conn)
            # `tm_all` — временное представление, живущее в соединении, и в
            # свежем его нет вовсе. Без этой строки прогон падал бы на «no such
            # table: tm_all», то есть не работал бы никогда.
            project_mod.attach_tm_sources(conn, self._tm_paths)
            found = glossary.extract(
                conn, min_pairs=self._min_pairs, min_score=self._min_score,
                proper_only=self._proper_only,
                progress=lambda done, total: self.progress.emit(done, total),
                cancelled=lambda: self._cancelled)
            self.done.emit(found)
        except sqlite3.Error as exc:      # noqa: BLE001 — показываем любую ошибку базы
            self.failed.emit(str(exc))
        finally:
            if conn is not None:
                conn.close()


class _Model(QAbstractTableModel):
    """Общая модель обеих таблиц: колонки задаёт вкладка."""
    edited = Signal()

    def __init__(self, conn: sqlite3.Connection, columns, status: str, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.columns = columns
        self.status = status
        self._rows: list[glossary.Entry] = []
        self._sort: tuple[int, bool] | None = None

    def reload(self, *, search: str = "") -> None:
        self.beginResetModel()
        self._rows = glossary.rows(self.conn, status=self.status, search=search)
        self.endResetModel()

    def set_sort(self, spec: tuple[int, bool] | None) -> None:
        self.beginResetModel()
        self._sort = spec
        self.endResetModel()

    def _sorted(self) -> list[glossary.Entry]:
        if self._sort is None:
            return self._rows
        column, descending = self._sort
        keys = {
            C_EN: lambda e: e.en_term.casefold(),
            C_RU: lambda e: e.ru_term.casefold(),
            C_SCORE: lambda e: e.score or 0.0,
            C_PAIRS: lambda e: e.pairs or 0,
        }
        return sorted(self._rows, key=keys.get(column, keys[C_EN]), reverse=descending)

    def entry(self, row: int) -> glossary.Entry | None:
        rows = self._sorted()
        return rows[row] if 0 <= row < len(rows) else None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return translate("Glossary", self.columns[section])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        entry = self.entry(index.row())
        if entry is None:
            return None
        column = index.column()
        if column == C_EN:
            return entry.en_term
        if column == C_RU:
            return entry.ru_term
        if self.columns is TERM_COLUMNS:
            return entry.note
        if column == C_SCORE:
            # два знака: разница между 0.63 и 0.634 переводчику ничего не говорит
            return "" if entry.score is None else f"{entry.score:.2f}"
        return "" if entry.pairs is None else str(entry.pairs)

    def flags(self, index):
        base = super().flags(index)
        if self.columns is TERM_COLUMNS and index.column() in (T_EN, T_RU, T_NOTE):
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or self.columns is not TERM_COLUMNS:
            return False
        entry = self.entry(index.row())
        if entry is None:
            return False
        field = {T_EN: "en_term", T_RU: "ru_term", T_NOTE: "note"}[index.column()]
        text = str(value).strip()
        if field != "note" and not text:
            return False        # пустой термин подсвечивать нечем
        glossary.update_entry(self.conn, entry.id, **{field: text})
        self.reload()
        self.edited.emit()
        return True


class _Tab(QWidget):
    """Общее у обеих вкладок: таблица, сортировка, поиск, нижняя полоса."""
    statusChanged = Signal(str)
    glossaryChanged = Signal()

    def __init__(self, conn: sqlite3.Connection, columns, status: str, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._status = ""

        self.layout_ = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(translate("Glossary", "Search:")))
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        self.layout_.addLayout(row)

        self.model = _Model(conn, columns, status, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(C_EN, QHeaderView.Stretch)
        header.setSectionResizeMode(C_RU, QHeaderView.Stretch)
        for col in range(2, len(columns)):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._on_header_clicked)
        self.sort = SortState()
        self.layout_.addWidget(self.table, 1)

        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self.model.edited.connect(self._on_edited)

    def shutdown(self) -> None:
        self._debounce.stop()

    def status_text(self) -> str:
        return self._status

    def reload(self) -> None:
        self._debounce.stop()
        self.model.reload(search=self.search.text().strip())
        self._update_status()

    def _on_edited(self) -> None:
        self.glossaryChanged.emit()
        self._update_status()

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

    def _selected(self) -> list[glossary.Entry]:
        found = [self.model.entry(i.row())
                 for i in self.table.selectionModel().selectedRows()]
        return [e for e in found if e is not None]

    def _update_status(self) -> None:
        raise NotImplementedError


class TermsTab(_Tab):
    """Принятые термины: их и подсвечивает панель редактора."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(conn, TERM_COLUMNS, APPROVED, parent)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        self.layout_.addWidget(HintLabel(translate(
            "Glossary", "Double click to edit. Accepted terms are highlighted in the "
                 "original; hovering one shows its translation.")))

        add = QHBoxLayout()
        self.en_input = QLineEdit()
        self.en_input.setPlaceholderText(translate("Glossary", "original"))
        add.addWidget(self.en_input, 1)
        self.ru_input = QLineEdit()
        self.ru_input.setPlaceholderText(translate("Glossary", "translation"))
        add.addWidget(self.ru_input, 1)
        self.add_btn = QPushButton(translate("Glossary", "Add"))
        self.add_btn.clicked.connect(self._add)
        add.addWidget(self.add_btn)
        self.delete_btn = QPushButton(translate("Glossary", "Delete selected"))
        self.delete_btn.clicked.connect(self._delete)
        add.addWidget(self.delete_btn)
        self.layout_.addLayout(add)

        self.en_input.returnPressed.connect(self._add)
        self.ru_input.returnPressed.connect(self._add)
        self.reload()

    def _add(self) -> None:
        en, ru = self.en_input.text().strip(), self.ru_input.text().strip()
        if not en or not ru:
            return
        glossary.upsert_manual(self.conn, en, ru)
        self.en_input.clear()
        self.ru_input.clear()
        self.reload()
        self.glossaryChanged.emit()

    def _delete(self) -> None:
        selected = self._selected()
        if not selected:
            return
        glossary.delete(self.conn, [e.id for e in selected])
        self.reload()
        self.glossaryChanged.emit()

    def _update_status(self) -> None:
        counts = glossary.counts(self.conn)
        self._status = fill(
            translate("Glossary", "terms: %1 · waiting to be reviewed: %2"),
            counts[APPROVED], counts[CANDIDATE])
        self.statusChanged.emit(self._status)


class CandidatesTab(_Tab):
    """Очередь на разбор: что предложила статистика."""

    # Прогон кончился — успехом, ошибкой или отменой. Наружу нужен затем же,
    # зачем и всякий сигнал о конце фоновой работы: дождаться его со стороны
    # нельзя иначе как опросом, а опрос в тесте — это гонка.
    runFinished = Signal()

    def __init__(self, conn: sqlite3.Connection, path, parent=None):
        super().__init__(conn, CANDIDATE_COLUMNS, CANDIDATE, parent)
        self._path = path
        self._thread = None
        self._worker = None

        self.layout_.addWidget(HintLabel(translate(
            "Glossary", "Candidates are counted over the translation memory: the "
                 "project's own plus every attached database. Statistics only "
                 "suggests — nothing reaches the original until you accept it.")))

        controls = QHBoxLayout()
        self.run_btn = QPushButton(translate("Glossary", "Find terms"))
        self.run_btn.clicked.connect(self._run)
        controls.addWidget(self.run_btn)
        self.accept_btn = QPushButton(translate("Glossary", "Accept"))
        self.accept_btn.clicked.connect(lambda: self._decide(APPROVED))
        controls.addWidget(self.accept_btn)
        self.reject_btn = QPushButton(translate("Glossary", "Reject"))
        self.reject_btn.setToolTip(translate(
            "Glossary", "A rejected term is not offered again on the next run"))
        self.reject_btn.clicked.connect(lambda: self._decide(REJECTED))
        controls.addWidget(self.reject_btn)
        controls.addStretch(1)
        self.proper_only = QCheckBox(translate("Glossary", "proper nouns only"))
        self.proper_only.setChecked(True)
        self.proper_only.setToolTip(translate(
            "Glossary",
            "Offer only words written with a capital in the middle of a phrase "
            "— that is what tells a name apart from an ordinary word. Without "
            "it the list fills with correct but useless pairs like «Now → "
            "теперь»."))
        controls.addWidget(self.proper_only)
        self.layout_.addLayout(controls)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.layout_.addWidget(self.progress)

        self.reload()

    # --- прогон ---

    def is_busy(self) -> bool:
        return self._thread is not None

    def _run(self) -> None:
        if self.is_busy():
            self._worker.cancel()
            return
        from pdxloc import project as project_mod

        self._worker = _ExtractWorker(
            self._path, project_mod.attached_tm_paths(self.conn),
            glossary.MIN_PAIRS, glossary.MIN_SCORE,
            self.proper_only.isChecked())
        self._thread = mt_worker.start(self._worker, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        for signal in (self._worker.done, self._worker.failed):
            signal.connect(self._thread.quit)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)        # пока не знаем объём — бегущая полоса
        self.run_btn.setText(translate("Glossary", "Stop"))
        self._thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _finish(self) -> None:
        """Вернуть кнопку и полосу в покой. Сигнал — последним действием.

        Порядок важен всем, кто ждёт конца прогона: к моменту `runFinished`
        кандидаты обязаны быть уже записаны и показаны, иначе «дождался конца»
        означало бы «дождался чего-то посередине».
        """
        self._thread = self._worker = None
        self.progress.setVisible(False)
        self.run_btn.setText(translate("Glossary", "Find terms"))

    def _on_done(self, found: list) -> None:
        added = glossary.save_candidates(self.conn, found)
        self._finish()
        self.reload()
        self._status = fill(
            translate("Glossary", "found: %1 · new: %2"), len(found), added)
        self.statusChanged.emit(self._status)
        self.runFinished.emit()

    def _on_failed(self, message: str) -> None:
        """Ошибку показываем в нижней полосе, а не окном.

        Модальное окно из слота, завершающего фоновую работу, блокирует всё,
        что этого завершения ждёт, — включая обработку событий самого прогона.
        А переводчику здесь и нечего решать: счёт не удался, кнопка на месте,
        повторить можно тут же.
        """
        self._finish()
        self._status = fill(
            translate("Glossary", "counting failed: %1"), message)
        self.statusChanged.emit(self._status)
        self.runFinished.emit()

    def cancel_run(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def shutdown(self) -> None:
        super().shutdown()
        self.cancel_run()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = self._worker = None

    # --- разбор ---

    def _decide(self, status: str) -> None:
        selected = self._selected()
        if not selected:
            return
        glossary.set_status(self.conn, [e.id for e in selected], status)
        self.reload()
        self.glossaryChanged.emit()

    def _update_status(self) -> None:
        counts = glossary.counts(self.conn)
        self._status = fill(
            translate("Glossary", "candidates: %1 · accepted: %2 · rejected: %3"),
            counts[CANDIDATE], counts[APPROVED], counts[REJECTED])
        self.statusChanged.emit(self._status)


class GlossaryWindow(QDialog):
    glossaryChanged = Signal()

    def __init__(self, conn: sqlite3.Connection, path, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("Glossary", "Glossary"))
        self.setMinimumSize(900, 560)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.terms = TermsTab(conn)
        self.candidates = CandidatesTab(conn, path)
        self.tabs.addTab(self.terms, translate("Glossary", "Terms"))
        self.tabs.addTab(self.candidates, translate("Glossary", "Candidates"))
        layout.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        bottom.addWidget(self.status_label, 1)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.accept)
        bottom.addWidget(box)
        layout.addLayout(bottom)

        for tab in self._tabs():
            tab.statusChanged.connect(self._on_tab_status)
            # принятый термин обязан сразу подсветиться в панели редактора, а
            # счётчики соседней вкладки — сойтись с новым решением
            tab.glossaryChanged.connect(self.glossaryChanged)
            tab.glossaryChanged.connect(self._reload_others)
        self.tabs.currentChanged.connect(lambda _: self._show_status())
        self._show_status()

    def _tabs(self):
        return (self.terms, self.candidates)

    def _reload_others(self) -> None:
        for tab in self._tabs():
            if tab is not self.sender():
                tab.reload()

    def _on_tab_status(self, text: str) -> None:
        if self.sender() is self.tabs.currentWidget():
            self.status_label.setText(text)

    def _show_status(self) -> None:
        self.tabs.currentWidget().reload()
        self.status_label.setText(self.tabs.currentWidget().status_text())

    # --- закрытие ---

    def _confirm_close_while_running(self) -> bool:
        """Не закрываться молча посреди прогона.

        В отдельном окне от этого спасала бы модальность: уйти было бы некуда.
        Во вкладках переводчик легко переключится на «Термины» и нажмёт
        «Закрыть», не вспомнив, что счёт ещё идёт.
        """
        if not self.candidates.is_busy():
            return True
        answer = QMessageBox.question(
            self, translate("Glossary", "Glossary"),
            translate("Glossary", "Terms are still being counted. Interrupt and close "
                           "the window?\n\nCandidates found so far will not be "
                           "saved."))
        if answer != QMessageBox.Yes:
            return False
        self.candidates.cancel_run()
        return True

    def _stop(self) -> None:
        for tab in self._tabs():
            tab.shutdown()

    def closeEvent(self, event) -> None:
        if not self._confirm_close_while_running():
            event.ignore()
            return
        self._stop()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        if not self._confirm_close_while_running():
            return
        self._stop()
        super().done(result)
