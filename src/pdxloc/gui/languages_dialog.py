"""The project languages of a project that already exists.

The pair used to be set at creation time and never changed after: get it wrong
and the project had to be created from scratch.

The preview is mandatory for the same reason as when the original folder is
changed. The scanner finds files by the `_l_<language>` marker in the name, so
changing the folder language is as quiet a catastrophe as a wrong path: every row
turns deleted and the translations move to the archive. The difference is that
nothing here looks suspicious — the folder is in place, the button presses.

The text locale, by contrast, is safe: it does not touch files at all, only
machine translation, the naming of memory databases and the language rules of the
check. That is why the window honestly says «rows are not affected» when only the
locale changes.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget,
)

from pdxloc import project as project_mod
from pdxloc.core import games, languages as lang_mod
from pdxloc.core import relocate
from pdxloc.core.i18n import fill, translate
from pdxloc.gui.widgets import HintLabel


class LanguagesDialog(QDialog):
    # True when the language folder changed and the project needs a scan
    languagesChanged = Signal(bool)

    def __init__(self, conn: sqlite3.Connection, project_id: int = 1, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.project_id = project_id
        self.preview: relocate.LanguagePreview | None = None
        self.setWindowTitle(translate("LanguagesDialog", "Project languages"))
        self.setMinimumWidth(660)

        current = project_mod.languages(conn, project_id)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        intro = QLabel(translate(
            "LanguagesDialog",
            "The game folder decides the file names (*_l_english.yml) and the "
            "header inside them. The text language says what the text actually "
            "is — machine translation, memory database naming and "
            "language-specific checks go by it."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(10)
        layout.addLayout(form)

        # The game stands above the language folders because it decides which folders
        # are offered: EU4 has no Russian, Victoria 3 has Turkish.
        self.game_combo = QComboBox()
        self.game_combo.setEditable(True)
        for game_id in games.ORDER:
            self.game_combo.addItem(games.title(game_id), game_id)
        self.game_combo.setCurrentText(
            games.title(project_mod.game(conn, project_id)))
        self.game_combo.currentTextChanged.connect(self._on_game_changed)
        form.addRow(translate("LanguagesDialog", "Game:"), self.game_combo)

        self.src_lang = self._language_box(current.src_lang)
        self.tgt_lang = self._language_box(current.tgt_lang)
        pair = QHBoxLayout()
        pair.addWidget(self.src_lang)
        pair.addWidget(QLabel("→"))
        pair.addWidget(self.tgt_lang)
        pair.addStretch(1)
        form.addRow(translate("LanguagesDialog", "Game folders:"), pair)

        self.split = QCheckBox(translate(
            "LanguagesDialog", "The text is in another language"))
        self.split.setToolTip(translate(
            "LanguagesDialog",
            "Turn on when translating into a language the game does not know: "
            "Portuguese in CK3, say, lives in l_english files"))
        form.addRow(self.split)

        self.locales = QWidget()
        locales_row = QHBoxLayout(self.locales)
        locales_row.setContentsMargins(0, 0, 0, 0)
        self.src_locale = self._locale_box(current.src_locale)
        self.tgt_locale = self._locale_box(current.tgt_locale)
        locales_row.addWidget(self.src_locale)
        locales_row.addWidget(QLabel("→"))
        locales_row.addWidget(self.tgt_locale)
        locales_row.addStretch(1)
        form.addRow(translate("LanguagesDialog", "Text languages:"), self.locales)

        self.split.setChecked(current.split)
        self.locales.setVisible(current.split)
        self.split.toggled.connect(self._on_split_toggled)

        self.report_box = QPlainTextEdit()
        self.report_box.setReadOnly(True)
        layout.addWidget(self.report_box, 1)
        layout.addWidget(HintLabel(translate(
            "LanguagesDialog",
            "The folder of the original itself is changed in "
            "«Project → Change original folder…».")))

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.ok_button = self.buttons.button(QDialogButtonBox.Ok)
        self.ok_button.setText(translate("LanguagesDialog", "Apply"))
        self.buttons.accepted.connect(self._apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        for box in (self.src_lang, self.tgt_lang):
            box.currentTextChanged.connect(self._refresh)
        self._refresh()

    # --- fields ---

    @staticmethod
    def _language_box(value: str) -> QComboBox:
        """The language folder. The field is editable: mods invent names of their own."""
        box = QComboBox()
        box.setEditable(True)
        for code in lang_mod.PARADOX_LANGUAGES:
            box.addItem(lang_mod.language_name(code), code)
        box.setCurrentText(value)
        return box

    @staticmethod
    def _locale_box(value: str) -> QComboBox:
        box = QComboBox()
        box.setEditable(True)
        for code in lang_mod.TEXT_LOCALES:
            box.addItem(lang_mod.locale_name(code), code)
        box.setCurrentText(value)
        return box

    @staticmethod
    def _code(box: QComboBox) -> str:
        """The code from the field: a chosen item carries it in data, a typed one in
        its text."""
        text = box.currentText().strip()
        index = box.findText(text)
        if index >= 0 and box.itemData(index):
            return str(box.itemData(index))
        return text

    def values(self) -> project_mod.ProjectLanguages:
        src_lang = self._code(self.src_lang) or "english"
        tgt_lang = self._code(self.tgt_lang) or "russian"
        if self.split.isChecked():
            src_locale = self._code(self.src_locale)
            tgt_locale = self._code(self.tgt_locale)
        else:
            src_locale = tgt_locale = ""
        return project_mod.ProjectLanguages(
            src_lang=src_lang, tgt_lang=tgt_lang,
            src_locale=lang_mod.resolve_locale(src_lang, src_locale),
            tgt_locale=lang_mod.resolve_locale(tgt_lang, tgt_locale))

    # --- preview ---

    def game_id(self) -> str:
        text = self.game_combo.currentText().strip()
        index = self.game_combo.findText(text)
        if index >= 0 and self.game_combo.itemData(index):
            return str(self.game_combo.itemData(index))
        return games.slug(text) if text else games.CK3

    def _on_game_changed(self) -> None:
        """Changing the game changes which language folders are offered.

        The chosen value is left alone: a mod is free to create a folder the game
        does not have, and substituting it for the person is not ours to do.
        """
        for box in (self.src_lang, self.tgt_lang):
            current = box.currentText()
            box.blockSignals(True)
            box.clear()
            box.addItems(games.languages(self.game_id()))
            box.setCurrentText(current)
            box.blockSignals(False)
        self._refresh()

    def _on_split_toggled(self, shown: bool) -> None:
        self.locales.setVisible(shown)
        if shown:
            # fill in what is implied anyway, so the field is not left empty
            values = self.values()
            self.src_locale.setCurrentText(values.src_locale)
            self.tgt_locale.setCurrentText(values.tgt_locale)
        self._refresh()

    def _refresh(self) -> None:
        values = self.values()
        try:
            self.preview = relocate.preview_language_change(
                self.conn, self.project_id, values.src_lang, values.tgt_lang)
        except (sqlite3.Error, OSError) as e:
            self.preview = None
            self.report_box.setPlainText(str(e))
            self.ok_button.setEnabled(False)
            return
        self.report_box.setPlainText(self.preview.summary())
        self.ok_button.setEnabled(True)

    def _apply(self) -> None:
        values = self.values()
        if self.preview is not None and self.preview.risky:
            answer = QMessageBox.question(
                self, translate("LanguagesDialog", "Project languages"),
                fill(translate(
                    "LanguagesDialog",
                    "Only %1 files out of %2 carry the label _l_%3.\n\n"
                    "Translations are not deleted: they stay in the archive and "
                    "in the translation memory. Change the languages?"),
                    self.preview.found, self.preview.known_files,
                    values.src_lang))
            if answer != QMessageBox.Yes:
                return
        game_id = self.game_id()
        moved = game_id != project_mod.game(self.conn, self.project_id)
        project_mod.set_game(self.conn, game_id, self.project_id)
        project_mod.set_languages(self.conn, values, self.project_id)
        if moved:
            # The file is open right now, and moving it from here would mean closing the
            # project in the middle of a dialog. Sorting it into the right pen is the job
            # of the guard at the next open; one action should not have two mechanisms.
            QMessageBox.information(
                self, translate("LanguagesDialog", "Project languages"),
                fill(translate(
                    "LanguagesDialog",
                    "The game is now %1. The project file stays where it lies; "
                    "moving it to the pen of the new game will be offered the "
                    "next time the project is opened."),
                    games.title(game_id)))
        self.languagesChanged.emit(bool(self.preview and self.preview.scan_needed))
        self.accept()
