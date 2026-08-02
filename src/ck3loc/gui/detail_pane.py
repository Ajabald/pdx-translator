"""Детальная панель: EN-оригинал, дифф для stale, RU-редактор, TM-подсказки."""
from __future__ import annotations

import html
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QKeySequence, QShortcut, QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from ck3loc import settings
from ck3loc.core import fuzzy, textdiff, tm, unit_ops
from ck3loc.core.statuses import STATUS_LABELS, Status
from ck3loc.gui import theme
from ck3loc.gui.highlighter import Ck3Highlighter

_MONO = QFont("Consolas", 10)


def editor_text(edit) -> str:
    """Текст поля без потерь.

    `toPlainText()` подменяет неразрывный пробел обычным — а он в русской
    типографике стоит осмысленно (перед тире, в «5 000»), и в ванильной
    локализации CK3 таких строк полно. Из-за подмены строка, которую даже не
    трогали, считалась изменённой и перезаписывалась при уходе с неё.
    """
    return edit.document().toRawText().replace(chr(0x2029), chr(10))


def _diff_html(old: str, new: str) -> str:
    """HTML-дифф прежней и новой редакции оригинала — пословный, чтобы читался."""
    insert, delete = theme.color("diff.insert"), theme.color("diff.delete")
    out: list[str] = []
    for op, text in textdiff.word_diff(old, new):
        escaped = html.escape(text)
        if op == "equal":
            out.append(escaped)
        elif op == "insert":
            out.append(f'<span style="background:{insert}">{escaped}</span>')
        else:
            out.append(f'<s style="background:{delete}">{escaped}</s>')
    return "".join(out)


SOURCE_LABELS = {
    "user": "мои переводы",
    "import": "импорт",
    "game": "база игры",
    "project-export": "экспорт проекта",
}


class TmSuggestionsList(QListWidget):
    """Варианты перевода из памяти. Двойной клик подставляет вариант,
    правая кнопка открывает действия над самой записью памяти."""

    suggestionPicked = Signal(str)
    memoryChanged = Signal()          # запись изменена или удалена
    manageRequested = Signal()        # открыть менеджер памяти

    def __init__(self, conn=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.itemDoubleClicked.connect(self._pick)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def show_hits(self, hits: list, query: str = "") -> None:
        self.clear()
        for h in hits:
            src = SOURCE_LABELS.get(h.source, h.source)
            where = f" · {h.origin}" if h.origin else ""
            exact = h.score >= 1.0
            # процент показываем только у неточных: у точного совпадения он
            # только отвлекал бы, а вот перепутать неточное с точным — опасно
            mark = "" if exact else f"{h.score:.0%} · "
            item = QListWidgetItem(f"{mark}{h.ru_text}    [{h.uses}× · {src}{where}]")
            item.setData(Qt.UserRole, h)
            tip = [html.escape(h.ru_text)]
            if not exact and h.en_text:
                tip.append(f"<br><br>Оригинал записи ({h.score:.0%} сходства):<br>"
                           f'<span style="font-family:Consolas">{_diff_html(query, h.en_text)}</span>')
            tip.append(f"<br><br>Источник: {html.escape(h.origin or src)}")
            if not h.editable:
                tip.append("<br>Только для чтения (подключённая база)")
            item.setToolTip("".join(tip))
            self.addItem(item)

    def _current_hit(self):
        item = self.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _pick(self, item) -> None:
        hit = item.data(Qt.UserRole)
        if hit is not None:
            self.suggestionPicked.emit(hit.ru_text)

    def _show_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None:
            menu = QMenu(self)
            menu.addAction("Открыть память переводов…", self.manageRequested.emit)
            menu.exec(self.viewport().mapToGlobal(pos))
            return
        self.setCurrentItem(item)
        hit = item.data(Qt.UserRole)

        menu = QMenu(self)
        menu.addAction("Подставить в перевод",
                       lambda: self.suggestionPicked.emit(hit.ru_text))
        menu.addAction("Копировать текст",
                       lambda: QGuiApplication.clipboard().setText(hit.ru_text))
        menu.addSeparator()
        act_edit = menu.addAction("Изменить запись в памяти…", lambda: self._edit(hit))
        act_delete = menu.addAction("Удалить из памяти", lambda: self._delete(hit))
        if not hit.editable:
            for act in (act_edit, act_delete):
                act.setEnabled(False)
                act.setToolTip("Запись из подключённой базы — только для чтения")
        menu.addSeparator()
        menu.addAction("Открыть память переводов…", self.manageRequested.emit)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _edit(self, hit) -> None:
        if self.conn is None or not hit.editable:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Изменить запись памяти",
            "Перевод в памяти (подсказки для одинаковых строк):", hit.ru_text)
        if ok and text.strip() and text != hit.ru_text:
            tm.update_entry(self.conn, hit.id, text)
            self.memoryChanged.emit()

    def _delete(self, hit) -> None:
        if self.conn is None or not hit.editable:
            return
        answer = QMessageBox.question(
            self, "Удалить из памяти",
            f"Убрать этот вариант из памяти переводов?\n\n{hit.ru_text[:200]}\n\n"
            "Перевод текущей строки останется на месте.")
        if answer == QMessageBox.Yes:
            tm.delete_entries(self.conn, [hit.id])
            self.memoryChanged.emit()


class DetailPane(QWidget):
    saved = Signal(int)        # unit_id — после любого сохранения статуса/текста
    requestNext = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.unit_id: int | None = None
        self._loaded_ru = ""       # для детекции несохранённых правок

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.header = QLabel("—")
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.header)

        splitter = QSplitter(Qt.Horizontal)

        # левая колонка: EN + блок изменений оригинала
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        en_head = QHBoxLayout()
        en_head.addWidget(QLabel("Оригинал (EN):"))
        en_head.addStretch(1)
        self.highlight_check = QCheckBox("подсвечивать изменения")
        self.highlight_check.setToolTip(
            "Закрашивать в оригинале то, чего не было в прежней редакции")
        self.highlight_check.setChecked(
            settings.qsettings().value("detail/highlight_changes", True, type=bool))
        self.highlight_check.toggled.connect(self._on_highlight_toggled)
        en_head.addWidget(self.highlight_check)
        lv.addLayout(en_head)
        self.en_view = QPlainTextEdit()
        self.en_view.setReadOnly(True)
        self.en_view.setFont(_MONO)
        Ck3Highlighter(self.en_view.document())
        lv.addWidget(self.en_view, 1)

        # блок изменений: заголовок, кнопка «Актуализировать» и сам дифф.
        # Кнопка живёт здесь, а не в общем ряду внизу: она осмысленна только
        # для устаревших строк, и рядом видно, что именно изменилось.
        self.change_box = QWidget()
        cv = QVBoxLayout(self.change_box)
        cv.setContentsMargins(0, 0, 0, 0)
        change_head = QHBoxLayout()
        self.diff_label = QLabel("Изменение оригинала (было → стало):")
        change_head.addWidget(self.diff_label)
        change_head.addStretch(1)
        self.actualize_btn = QPushButton("Актуализировать")
        self.actualize_btn.setToolTip(
            "Подтвердить, что перевод соответствует новому оригиналу")
        self.actualize_btn.clicked.connect(self._actualize)
        change_head.addWidget(self.actualize_btn)
        cv.addLayout(change_head)
        self.diff_view = QTextBrowser()
        self.diff_view.setFont(_MONO)
        self.diff_view.setMaximumHeight(110)
        cv.addWidget(self.diff_view)
        lv.addWidget(self.change_box)
        splitter.addWidget(left)

        # правая колонка: RU + TM
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        ru_head = QHBoxLayout()
        ru_head.addWidget(QLabel("Перевод (RU):"))
        ru_head.addStretch(1)
        # состояние вместо кнопки «Сохранить»: правки сохраняются сами при
        # уходе со строки, но видеть, сохранены ли они, всё равно нужно
        self.save_state = QLabel()
        ru_head.addWidget(self.save_state)
        rv.addLayout(ru_head)
        self.ru_edit = QPlainTextEdit()
        self.ru_edit.setFont(_MONO)
        Ck3Highlighter(self.ru_edit.document())
        rv.addWidget(self.ru_edit, 1)
        rv.addWidget(QLabel(
            "Память переводов (двойной клик — подставить, правая кнопка — действия):"))
        self.tm_list = TmSuggestionsList(conn)
        self.tm_list.setMaximumHeight(90)
        self.tm_list.suggestionPicked.connect(self._apply_suggestion)
        self.tm_list.memoryChanged.connect(self._reload_suggestions)
        rv.addWidget(self.tm_list)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # Нижнего ряда кнопок больше нет: «Переведено»/«Проверено» дублировали
        # колонки ✓/✗ другим хоткеем, «EN → RU» — F8, а «Сохранить» не нужна
        # при автосохранении. Явное сохранение осталось на Ctrl+S.
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)

        self.ru_edit.textChanged.connect(self._update_save_state)
        theme.on_change(self._on_theme_changed)

        self.clear()

    # --- загрузка/очистка ---

    def clear(self) -> None:
        self.unit_id = None
        self._loaded_ru = ""
        self.header.setText("—")
        self.en_view.clear()
        self.ru_edit.clear()
        self.tm_list.clear()
        self.change_box.hide()
        self.save_state.clear()
        self.setEnabled(False)

    def _update_save_state(self) -> None:
        if self.unit_id is None:
            self.save_state.clear()
            return
        dirty = editor_text(self.ru_edit) != self._loaded_ru
        self.save_state.setText(
            "есть несохранённые правки (Ctrl+S)" if dirty else "сохранено")
        self.save_state.setStyleSheet(
            f"color: {theme.color('issue.warning' if dirty else 'hint')};")

    def _on_highlight_toggled(self, checked: bool) -> None:
        settings.qsettings().setValue("detail/highlight_changes", checked)
        if self.unit_id is not None:
            self.load_unit(self.unit_id)

    def _on_theme_changed(self) -> None:
        self._update_save_state()
        if self.unit_id is None:
            return
        try:
            self.load_unit(self.unit_id)
        except sqlite3.ProgrammingError:
            # панель пережила своё соединение (проект закрыт) — перерисовка
            # не повод ронять окно, показывать всё равно уже нечего
            self.clear()

    def load_unit(self, unit_id: int) -> None:
        self._autosave()
        row = self.conn.execute(
            """SELECT u.*, f.rel_path FROM units u
               JOIN files f ON f.id = u.file_id WHERE u.id = ?""",
            (unit_id,),
        ).fetchone()
        if row is None:
            self.clear()
            return
        self.setEnabled(True)
        self.unit_id = unit_id
        status = Status(row["status"])
        label = STATUS_LABELS[status]
        self.header.setText(
            f"<b>{html.escape(row['key'])}</b> — {html.escape(row['rel_path'])} — {label}")
        self.en_view.setPlainText(row["en_text"] or "(нет оригинала — ключ только в RU)")
        self._loaded_ru = row["ru_text"] or ""
        self.ru_edit.setPlainText(self._loaded_ru)
        self.ru_edit.document().clearUndoRedoStacks()

        stale = status == Status.STALE and row["prev_en_text"]
        self.change_box.setVisible(bool(stale))
        if stale:
            self.diff_view.setHtml(
                f'<div style="font-family:Consolas">{_diff_html(row["prev_en_text"], row["en_text"])}</div>')
            kind = row["change_kind"] or ""
            self.diff_label.setText(
                "Оригинал изменился"
                + (" (косметическая правка)" if kind == textdiff.COSMETIC else "")
                + " — было → стало:")
        highlight = stale and self.highlight_check.isChecked()
        self._highlight_changes(row["prev_en_text"] if highlight else None,
                                row["en_text"] or "")

        self.tm_list.conn = self.conn
        self._reload_suggestions()
        self._update_save_state()

    def _highlight_changes(self, prev_text: str | None, current_text: str) -> None:
        """Подсветить в поле оригинала куски, которых не было в прежней редакции.

        Делается через ExtraSelections: они ложатся поверх подсветки разметки
        CK3 и не мешают ей (второй QSyntaxHighlighter на том же документе
        затирал бы форматы первого).
        """
        if not prev_text or not current_text:
            self.en_view.setExtraSelections([])
            return
        fmt = QTextCharFormat()
        fmt.setBackground(theme.qcolor("diff.insert"))
        selections = []
        for start, end in textdiff.changed_ranges(prev_text, current_text):
            selection = QTextEdit.ExtraSelection()   # класс общий для текстовых полей
            selection.format = fmt
            cursor = QTextCursor(self.en_view.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            selection.cursor = cursor
            selections.append(selection)
        self.en_view.setExtraSelections(selections)

    def _reload_suggestions(self) -> None:
        """Перечитать подсказки — после правки памяти или смены строки.

        Сначала точные совпадения, затем похожие строки: при переводе сабмода
        поверх мода точных почти нет, а похожих — сколько угодно.
        """
        self.tm_list.clear()
        if self.unit_id is None:
            return
        row = self.conn.execute(
            "SELECT en_text FROM units WHERE id = ?", (self.unit_id,)).fetchone()
        if not row or not row["en_text"]:
            return
        en_text = row["en_text"]
        hits = tm.lookup(self.conn, en_text)
        known = {h.ru_text for h in hits}
        hits += [h for h in fuzzy.lookup_similar(self.conn, en_text)
                 if h.ru_text not in known]
        self.tm_list.show_hits(hits, en_text)

    # --- сохранение ---

    def _autosave(self) -> None:
        """Автосохранение при уходе со строки, если текст менялся."""
        if self.unit_id is not None and editor_text(self.ru_edit) != self._loaded_ru:
            self.save()

    def save(self) -> None:
        if self.unit_id is None:
            return
        text = editor_text(self.ru_edit)
        unit_ops.save_ru_text(self.conn, self.unit_id, text)
        self._loaded_ru = text
        self.saved.emit(self.unit_id)
        self.load_unit(self.unit_id)

    def set_status(self, new_status: Status) -> None:
        if self.unit_id is None:
            return
        self._autosave()
        unit_ops.set_status(self.conn, [self.unit_id], new_status)
        self.saved.emit(self.unit_id)
        self.load_unit(self.unit_id)

    def _actualize(self) -> None:
        self.set_status(Status.TRANSLATED)

    def _apply_suggestion(self, text: str) -> None:
        self.ru_edit.setPlainText(text)
