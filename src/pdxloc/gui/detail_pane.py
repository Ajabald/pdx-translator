"""The detail panel: the original, a diff for outdated rows, the translation
editor and the memory suggestions.
"""
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
    """The font of the original and translation fields, set in «Preferences»."""
    return QFont(prefs.get("editor/font_family"), prefs.get("editor/font_size"))


def editor_text(edit) -> str:
    """The text of a field without losses.

    `toPlainText()` swaps a non-breaking space for an ordinary one — and in
    Russian typography that space is there on purpose (before a dash, inside
    «5 000»), and the vanilla CK3 localisation is full of such rows. Because of
    the swap a row nobody had even touched counted as edited and was rewritten on
    leaving it.
    """
    return edit.document().toRawText().replace(chr(0x2029), chr(10))


def _diff_html(old: str, new: str) -> str:
    """An HTML diff of the previous and the new revision of the original, word by
    word so it can be read."""
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
    """Translation variants from the memory.

    A double click fills the variant in, a right click opens the actions over the
    memory entry itself.
    """

    suggestionPicked = Signal(str)
    memoryChanged = Signal()          # the entry was edited or deleted
    manageRequested = Signal()        # open the memory manager

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
            # the percentage is shown for inexact matches only: on an exact one it would
            # merely distract, while mistaking an inexact match for an exact one is
            # dangerous
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
            # origin is the database name, except for the project's own memory: that
            # arrives from SQL as the string «Project» and is translated like any label
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
    saved = Signal(int)        # unit_id — after any save of a status or of text
    requestNext = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.unit_id: int | None = None
        self._loaded_ru = ""       # to detect unsaved edits
        # both highlights of the original field: what to show is decided by
        # _refresh_extra_selections, the sole owner of setExtraSelections
        self._diff_prev: str | None = None
        self._terms: dict[str, str] = {}
        self._term_index = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.header = QLabel("—")
        self.header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.header)

        splitter = QSplitter(Qt.Horizontal)

        # the left column: the original plus the block of changes to it
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

        # the changes block: a header, the «Actualize» button and the diff itself.
        # The button lives here rather than in the common row below: it is meaningful
        # only for outdated rows, and next to it you can see what actually changed.
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

        # the right column: the translation plus the memory
        right = QWidget()
        rv = QVBoxLayout(right)
        # a margin on the right, or «saved» butts against the window edge
        rv.setContentsMargins(0, 0, 6, 0)
        ru_head_bar = QWidget()
        ru_head = QHBoxLayout(ru_head_bar)
        ru_head.setContentsMargins(0, 0, 0, 0)
        self.ru_label = QLabel()
        ru_head.addWidget(self.ru_label)
        ru_head.addStretch(1)
        # a state indicator instead of a «Save» button: edits save themselves when you
        # leave a row, but seeing whether they are saved is still needed
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
        # The height is a multiple of a list row and stretches with the panel. There
        # used to be a setMaximumHeight(90) here: 90 is not a multiple of the row
        # height, and the last visible suggestion was cut in half — which looked like a
        # truncation.
        self._tm_min_rows = 3
        self.tm_list.setMinimumHeight(self._tm_rows_height(self._tm_min_rows))
        rv.addWidget(self.tm_list, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # The bottom row of buttons is gone: «Translated»/«Reviewed» duplicated the ✓/✗
        # columns under another shortcut, «EN → RU» duplicated F8, and «Save» is not
        # needed with autosave. An explicit save stayed on Ctrl+S — and it is now the
        # «Edit → Save row translation» action from the common registry rather than a
        # QShortcut of its own: Qt treats two handlers of one key as a conflict and
        # calls neither.

        self.ru_edit.textChanged.connect(self._update_save_state)
        theme.on_change(self._on_theme_changed)
        prefs.on_change(self._on_pref_changed)

        self._head_bars = (en_head_bar, ru_head_bar)
        self.retranslate()      # it also aligns the headers: their height depends on the text
        self.clear()

    def retranslate(self) -> None:
        """The panel labels. The panel lives for the whole session, so they are
        replaced in place."""
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
        # The length of the labels changed, so the headers may drift apart in height
        # again
        self._equalise_heads()
        self._update_save_state()
        if self.unit_id is not None:
            self.load_unit(self.unit_id)        # the status in the header is translated too

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
        """The list height fits exactly N rows, with no half a row cut off below."""
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
        """The headers of both columns get the same height.

        The left row holds a checkbox, which is taller than a label, and the
        original field ended up a few pixels below the translation field.
        Recomputing is mandatory after a change of font or of language —
        otherwise the tests are green and the window is crooked.
        """
        for bar in self._head_bars:
            bar.setFixedHeight(0)
            bar.setMinimumHeight(0)
            bar.setMaximumHeight(16777215)
        height = max(bar.sizeHint().height() for bar in self._head_bars)
        for bar in self._head_bars:
            bar.setFixedHeight(height)

    # --- loading and clearing ---

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
        """The checkbox in the panel and the one in «Preferences» are one setting."""
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
            # the panel outlived its connection — the project was closed — and a repaint is
            # no reason to bring the window down; there is nothing left to show anyway
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

    # --- highlighting the original field ---
    #
    # ExtraSelections lie on top of the CK3 markup highlighting and do not
    # disturb it (a second QSyntaxHighlighter on the same document would wipe the
    # formats of the first). But a field has **one** such list, and
    # `setExtraSelections` replaces it whole. So only `_refresh_extra_selections`
    # has the right to call it: while the change highlighting called it itself,
    # adding the term highlighting through a second call silently erased the diff
    # on an outdated row.

    def _refresh_extra_selections(self, current_text: str) -> None:
        """Collect both highlights of the original field and set them in one go."""
        selections = self._change_selections(self._diff_prev, current_text)
        selections += self._term_selections(current_text)
        self.en_view.setExtraSelections(selections)

    def _selection(self, start: int, end: int, fmt: QTextCharFormat):
        selection = QTextEdit.ExtraSelection()   # the class is shared by the text fields
        selection.format = fmt
        cursor = QTextCursor(self.en_view.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        selection.cursor = cursor
        return selection

    def _change_selections(self, prev_text: str | None, current_text: str) -> list:
        """The pieces the previous revision of the original did not have."""
        if not prev_text or not current_text:
            return []
        fmt = QTextCharFormat()
        fmt.setBackground(theme.qcolor("diff.insert"))
        return [self._selection(start, end, fmt)
                for start, end in textdiff.changed_ranges(prev_text, current_text)]

    def _term_selections(self, current_text: str) -> list:
        """The glossary terms the translator has accepted.

        The translation of a term hangs as a tooltip on the format itself: a
        translator will hover over a word anyway, whereas going to the glossary
        window for it they will not.
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
        """Re-read the accepted terms, after the glossary was edited.

        The index is kept ready rather than built per row: there is one of it per
        project, while a translator walks thousands of rows.
        """
        try:
            self._terms = glossary.approved_terms(self.conn)
        except sqlite3.Error:
            self._terms = {}        # the project is closing: there is nothing left to highlight
        self._term_index = glossary.build_index(self._terms)
        if self.unit_id is not None:
            self.load_unit(self.unit_id)

    def _reload_suggestions(self) -> None:
        """Re-read the suggestions, after the memory changed or the row did.

        Exact matches first, then similar rows: when translating a submod on top
        of a mod there are almost no exact ones and any number of similar ones.
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

    # --- saving ---

    def _autosave(self) -> None:
        """Autosave on leaving a row, when the text was changed."""
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
