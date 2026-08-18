"""Детальная панель: EN-оригинал, дифф для stale, RU-редактор, TM-подсказки."""
from __future__ import annotations

import html
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QFont, QGuiApplication, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTextBrowser,
    QTextEdit, QVBoxLayout, QWidget,
)

from pdxloc.core import fuzzy, glossary, textdiff, tm, unit_ops
from pdxloc.core import statuses as statuses_mod
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.core.statuses import Status
from pdxloc.gui import prefs, theme
from pdxloc.gui.highlighter import Ck3Highlighter

CTX = "DetailPane"


def editor_font() -> QFont:
    """Шрифт полей оригинала и перевода — настраивается в «Параметрах»."""
    return QFont(prefs.get("editor/font_family"), prefs.get("editor/font_size"))


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
    "user": QT_TRANSLATE_NOOP("DetailPane", "my translations"),
    "import": QT_TRANSLATE_NOOP("DetailPane", "import"),
    "game": QT_TRANSLATE_NOOP("DetailPane", "game database"),
    "project-export": QT_TRANSLATE_NOOP("DetailPane", "project export"),
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
            src = translate("DetailPane", SOURCE_LABELS.get(h.source, h.source))
            where = f" · {h.origin}" if h.origin else ""
            exact = h.score >= 1.0
            # процент показываем только у неточных: у точного совпадения он
            # только отвлекал бы, а вот перепутать неточное с точным — опасно
            mark = "" if exact else f"{h.score:.0%} · "
            item = QListWidgetItem(f"{mark}{h.ru_text}    [{h.uses}× · {src}{where}]")
            item.setData(Qt.UserRole, h)
            tip = [html.escape(h.ru_text)]
            if not exact and h.en_text:
                tip.append("<br><br>" + fill(translate(
                    "DetailPane", "Entry original (%1 similarity):"),
                    f"{h.score:.0%}") + "<br>"
                    f'<span style="font-family:Consolas">'
                    f'{_diff_html(query, h.en_text)}</span>')
            # origin — имя базы, кроме собственной памяти проекта: та приходит
            # из SQL строкой «Project» и переводится наравне с подписями
            origin = translate("DetailPane", h.origin) if h.origin else src
            tip.append("<br><br>" + fill(
                translate("DetailPane", "Source: %1"), html.escape(origin)))
            if not h.editable:
                tip.append("<br>" + translate(
                    "DetailPane", "Read only (attached database)"))
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
            menu.addAction(translate("DetailPane", "Open translation memory…"),
                           self.manageRequested.emit)
            menu.exec(self.viewport().mapToGlobal(pos))
            return
        self.setCurrentItem(item)
        hit = item.data(Qt.UserRole)

        menu = QMenu(self)
        menu.addAction(translate("DetailPane", "Insert into translation"),
                       lambda: self.suggestionPicked.emit(hit.ru_text))
        menu.addAction(translate("DetailPane", "Copy text"),
                       lambda: QGuiApplication.clipboard().setText(hit.ru_text))
        menu.addSeparator()
        act_edit = menu.addAction(
            translate("DetailPane", "Edit the memory entry…"), lambda: self._edit(hit))
        act_delete = menu.addAction(
            translate("DetailPane", "Delete from memory"), lambda: self._delete(hit))
        if not hit.editable:
            for act in (act_edit, act_delete):
                act.setEnabled(False)
                act.setToolTip(translate(
                    "DetailPane", "An entry from an attached database — read only"))
        menu.addSeparator()
        menu.addAction(translate("DetailPane", "Open translation memory…"),
                       self.manageRequested.emit)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _edit(self, hit) -> None:
        if self.conn is None or not hit.editable:
            return
        text, ok = QInputDialog.getMultiLineText(
            self, translate("DetailPane", "Edit memory entry"),
            translate("DetailPane",
                      "Translation in memory (suggestions for identical rows):"),
            hit.ru_text)
        if ok and text.strip() and text != hit.ru_text:
            tm.update_entry(self.conn, hit.id, text)
            self.memoryChanged.emit()

    def _delete(self, hit) -> None:
        if self.conn is None or not hit.editable:
            return
        answer = QMessageBox.question(
            self, translate("DetailPane", "Delete from memory"),
            fill(translate("DetailPane",
                           "Remove this variant from the translation memory?\n\n"
                           "%1\n\nThe translation of the current row stays in "
                           "place."), hit.ru_text[:200]))
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
        # обе подсветки поля оригинала: что показывать, решает
        # _refresh_extra_selections, единственный владелец setExtraSelections
        self._diff_prev: str | None = None
        self._terms: dict[str, str] = {}
        self._term_index = None

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
        en_head_bar = QWidget()
        en_head = QHBoxLayout(en_head_bar)
        en_head.setContentsMargins(0, 0, 0, 0)
        self.en_label = QLabel()
        en_head.addWidget(self.en_label)
        en_head.addStretch(1)
        self.highlight_check = QCheckBox()
        self.highlight_check.setChecked(prefs.get("detail/highlight_changes"))
        self.highlight_check.toggled.connect(self._on_highlight_toggled)
        en_head.addWidget(self.highlight_check)
        self.highlight_terms_check = QCheckBox()
        self.highlight_terms_check.setChecked(prefs.get("detail/highlight_terms"))
        self.highlight_terms_check.toggled.connect(self._on_terms_toggled)
        en_head.addWidget(self.highlight_terms_check)
        lv.addWidget(en_head_bar)
        self.en_view = QPlainTextEdit()
        self.en_view.setReadOnly(True)
        self.en_view.setFont(editor_font())
        Ck3Highlighter(self.en_view.document())
        lv.addWidget(self.en_view, 1)

        # блок изменений: заголовок, кнопка «Актуализировать» и сам дифф.
        # Кнопка живёт здесь, а не в общем ряду внизу: она осмысленна только
        # для устаревших строк, и рядом видно, что именно изменилось.
        self.change_box = QWidget()
        cv = QVBoxLayout(self.change_box)
        cv.setContentsMargins(0, 0, 0, 0)
        change_head = QHBoxLayout()
        self.diff_label = QLabel()
        change_head.addWidget(self.diff_label)
        change_head.addStretch(1)
        self.actualize_btn = QPushButton()
        self.actualize_btn.clicked.connect(self._actualize)
        change_head.addWidget(self.actualize_btn)
        cv.addLayout(change_head)
        self.diff_view = QTextBrowser()
        self.diff_view.setFont(editor_font())
        self.diff_view.setMaximumHeight(110)
        cv.addWidget(self.diff_view)
        lv.addWidget(self.change_box)
        splitter.addWidget(left)

        # правая колонка: RU + TM
        right = QWidget()
        rv = QVBoxLayout(right)
        # справа поле есть, иначе «сохранено» упирается прямо в край окна
        rv.setContentsMargins(0, 0, 6, 0)
        ru_head_bar = QWidget()
        ru_head = QHBoxLayout(ru_head_bar)
        ru_head.setContentsMargins(0, 0, 0, 0)
        self.ru_label = QLabel()
        ru_head.addWidget(self.ru_label)
        ru_head.addStretch(1)
        # состояние вместо кнопки «Сохранить»: правки сохраняются сами при
        # уходе со строки, но видеть, сохранены ли они, всё равно нужно
        self.save_state = QLabel()
        ru_head.addWidget(self.save_state)
        rv.addWidget(ru_head_bar)

        self.ru_edit = QPlainTextEdit()
        self.ru_edit.setFont(editor_font())
        Ck3Highlighter(self.ru_edit.document())
        rv.addWidget(self.ru_edit, 3)
        self.tm_label = QLabel()
        rv.addWidget(self.tm_label)
        self.tm_list = TmSuggestionsList(conn)
        self.tm_list.suggestionPicked.connect(self._apply_suggestion)
        self.tm_list.memoryChanged.connect(self._reload_suggestions)
        # Высота кратна строке списка и растягивается вместе с панелью. Раньше
        # тут стоял setMaximumHeight(90): 90 не кратно высоте строки, и
        # последняя видимая подсказка резалась пополам — выглядело как обрыв.
        self._tm_min_rows = 3
        self.tm_list.setMinimumHeight(self._tm_rows_height(self._tm_min_rows))
        rv.addWidget(self.tm_list, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # Нижнего ряда кнопок больше нет: «Переведено»/«Проверено» дублировали
        # колонки ✓/✗ другим хоткеем, «EN → RU» — F8, а «Сохранить» не нужна
        # при автосохранении. Явное сохранение осталось на Ctrl+S — теперь это
        # действие «Правка → Сохранить перевод строки» из общего реестра, а не
        # свой QShortcut: два обработчика одной клавиши Qt считает конфликтом и
        # не вызывает ни одного.

        self.ru_edit.textChanged.connect(self._update_save_state)
        theme.on_change(self._on_theme_changed)
        prefs.on_change(self._on_pref_changed)

        self._head_bars = (en_head_bar, ru_head_bar)
        self.retranslate()      # он же выравнивает шапки: их высота зависит от текста
        self.clear()

    def retranslate(self) -> None:
        """Подписи панели. Панель живёт всю сессию, поэтому меняем на месте."""
        self.en_label.setText(translate("DetailPane", "Original (EN):"))
        self.highlight_check.setText(translate("DetailPane", "highlight changes"))
        self.highlight_check.setToolTip(translate(
            "DetailPane",
            "Highlight in the original what was not in the previous revision"))
        self.highlight_terms_check.setText(translate("DetailPane", "highlight terms"))
        self.highlight_terms_check.setToolTip(translate(
            "DetailPane",
            "Highlight glossary terms in the original; hover shows the "
            "accepted translation"))
        self.diff_label.setText(translate("DetailPane", "Change of the original (was → became):"))
        self.actualize_btn.setText(translate("DetailPane", "Actualize"))
        self.actualize_btn.setToolTip(translate(
            "DetailPane",
            "Confirm that the translation matches the new original"))
        self.ru_label.setText(translate("DetailPane", "Translation (RU):"))
        self.tm_label.setText(translate(
            "DetailPane", "Translation memory (double click — insert, "
                          "right button — actions):"))
        # Длина подписей поменялась — шапки снова могут разъехаться по высоте
        self._equalise_heads()
        self._update_save_state()
        if self.unit_id is not None:
            self.load_unit(self.unit_id)        # статус в заголовке тоже переводится

    def _on_pref_changed(self, key: str) -> None:
        if key.startswith("editor/font"):
            self._apply_font()
        elif key == "detail/highlight_changes":
            self.highlight_check.setChecked(prefs.get(key))
        elif key == "detail/highlight_terms":
            self.highlight_terms_check.setChecked(prefs.get(key))
        elif key in ("tm/min_score", "tm/suggestions"):
            self._reload_suggestions()

    def _tm_rows_height(self, rows: int) -> int:
        """Высота списка ровно под N строк — без обрезанной половинки внизу."""
        row = self.tm_list.sizeHintForRow(0)
        if row <= 0:
            row = self.tm_list.fontMetrics().height() + 4
        frame = 2 * self.tm_list.frameWidth()
        return rows * row + frame

    def _apply_font(self) -> None:
        font = editor_font()
        for widget in (self.en_view, self.diff_view, self.ru_edit):
            widget.setFont(font)
        self._equalise_heads()

    def _equalise_heads(self) -> None:
        """Шапки обеих колонок — одной высоты.

        Слева в ряду чекбокс, он выше подписи, и поле оригинала вставало на
        несколько пикселей ниже поля перевода. Пересчитывать обязательно после
        смены шрифта и языка — иначе тест зелёный, а окно косое.
        """
        for bar in self._head_bars:
            bar.setFixedHeight(0)
            bar.setMinimumHeight(0)
            bar.setMaximumHeight(16777215)
        height = max(bar.sizeHint().height() for bar in self._head_bars)
        for bar in self._head_bars:
            bar.setFixedHeight(height)

    # --- загрузка/очистка ---

    def clear(self) -> None:
        self.unit_id = None
        self._loaded_ru = ""
        self._diff_prev = None
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
            translate("DetailPane", "unsaved edits (Ctrl+S)") if dirty
            else translate("DetailPane", "saved"))
        self.save_state.setStyleSheet(
            f"color: {theme.color('issue.warning' if dirty else 'hint')};")

    def _on_highlight_toggled(self, checked: bool) -> None:
        """Чекбокс в панели и галка в «Параметрах» — одна настройка."""
        prefs.set("detail/highlight_changes", checked)
        if self.unit_id is not None:
            self.load_unit(self.unit_id)

    def _on_terms_toggled(self, checked: bool) -> None:
        prefs.set("detail/highlight_terms", checked)
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
        label = statuses_mod.label(status)
        self.header.setText(
            f"<b>{html.escape(row['key'])}</b> — {html.escape(row['rel_path'])} — {label}")
        self.en_view.setPlainText(row["en_text"] or translate(
            "DetailPane", "(no original — the key exists only in RU)"))
        self._loaded_ru = row["ru_text"] or ""
        self.ru_edit.setPlainText(self._loaded_ru)
        self.ru_edit.document().clearUndoRedoStacks()

        stale = status == Status.STALE and row["prev_en_text"]
        self.change_box.setVisible(bool(stale))
        if stale:
            self.diff_view.setHtml(
                f'<div style="font-family:Consolas">{_diff_html(row["prev_en_text"], row["en_text"])}</div>')
            kind = row["change_kind"] or ""
            mark = (translate("DetailPane", " (cosmetic edit)")
                    if kind == textdiff.COSMETIC else "")
            self.diff_label.setText(fill(translate(
                "DetailPane", "The original changed%1 — was → became:"), mark))
        highlight = stale and self.highlight_check.isChecked()
        self._diff_prev = row["prev_en_text"] if highlight else None
        self._refresh_extra_selections(row["en_text"] or "")

        self.tm_list.conn = self.conn
        self._reload_suggestions()
        self._update_save_state()

    # --- подсветка поля оригинала ---
    #
    # ExtraSelections ложатся поверх подсветки разметки CK3 и не мешают ей
    # (второй QSyntaxHighlighter на том же документе затирал бы форматы
    # первого). Но список у поля **один**, и `setExtraSelections` его заменяет
    # целиком. Поэтому звать его имеет право только `_refresh_extra_selections`:
    # пока подсветка изменений вызывала его сама, добавление подсветки терминов
    # вторым вызовом молча стёрло бы дифф у устаревшей строки.

    def _refresh_extra_selections(self, current_text: str) -> None:
        """Собрать обе подсветки поля оригинала и выставить их разом."""
        selections = self._change_selections(self._diff_prev, current_text)
        selections += self._term_selections(current_text)
        self.en_view.setExtraSelections(selections)

    def _selection(self, start: int, end: int, fmt: QTextCharFormat):
        selection = QTextEdit.ExtraSelection()   # класс общий для текстовых полей
        selection.format = fmt
        cursor = QTextCursor(self.en_view.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        selection.cursor = cursor
        return selection

    def _change_selections(self, prev_text: str | None, current_text: str) -> list:
        """Куски, которых не было в прежней редакции оригинала."""
        if not prev_text or not current_text:
            return []
        fmt = QTextCharFormat()
        fmt.setBackground(theme.qcolor("diff.insert"))
        return [self._selection(start, end, fmt)
                for start, end in textdiff.changed_ranges(prev_text, current_text)]

    def _term_selections(self, current_text: str) -> list:
        """Термины глоссария, принятые переводчиком.

        Перевод термина висит подсказкой на самом формате: наводить мышь на
        слово переводчик и так будет, а лезть за этим в окно глоссария — нет.
        """
        if not current_text or not self.highlight_terms_check.isChecked():
            return []
        found = glossary.find_terms(current_text, self._term_index, self._terms)
        out = []
        for start, end, ru in found:
            fmt = QTextCharFormat()
            fmt.setBackground(theme.qcolor("glossary.term"))
            fmt.setToolTip(ru)
            out.append(self._selection(start, end, fmt))
        return out

    def reload_glossary(self) -> None:
        """Перечитать принятые термины — после правки глоссария.

        Индекс держим готовым, а не собираем на каждую строку: он один на
        проект, а строк переводчик проходит тысячи.
        """
        try:
            self._terms = glossary.approved_terms(self.conn)
        except sqlite3.Error:
            self._terms = {}        # проект закрывается — подсвечивать нечего
        self._term_index = glossary.build_index(self._terms)
        if self.unit_id is not None:
            self.load_unit(self.unit_id)

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
        similar = fuzzy.lookup_similar(
            self.conn, en_text,
            limit=prefs.get("tm/suggestions"),
            min_score=prefs.get("tm/min_score") / 100)
        hits += [h for h in similar if h.ru_text not in known]
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
