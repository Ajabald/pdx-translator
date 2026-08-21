"""The first-run wizard: language, memory databases, the first project.

A new user used to get an empty project list and not one hint. Two defaults were
quietly decided for them, and both wrongly: the interface came up in the system
language (while the translation might well be into another), and work began
without a single translation memory database — that is, without half the point of
the tool.

Three steps and not one more. The theme and the folders stayed in «Preferences»:
they change rarely and look sensible by default, and a wizard that asks about
everything gets clicked through unread.

The wizard is shown **once**. Everything it offers is available afterwards
through ordinary commands, so «Skip» here is a full answer rather than a trick.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from pdxloc import project as project_mod
from pdxloc.core.i18n import fill, translate
from pdxloc.gui import language, prefs
from pdxloc.gui.widgets import HintLabel

DONE_KEY = "general/first_run_done"


def needed() -> bool:
    """Whether to show the wizard. Once in the lifetime of an installation."""
    return not prefs.get(DONE_KEY)


def mark_done() -> None:
    prefs.set(DONE_KEY, True)


class WelcomeDialog(QDialog):
    """Three steps of introduction. Each of them can do nothing at all."""

    buildDatabaseRequested = Signal()
    createProjectRequested = Signal()
    openProjectRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(translate("Welcome", "Getting started"))
        self.setMinimumSize(600, 380)
        self._step = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self.heading = QLabel()
        font = self.heading.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        self.heading.setFont(font)
        layout.addWidget(self.heading)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._language_page())
        self.pages.addWidget(self._databases_page())
        self.pages.addWidget(self._project_page())
        layout.addWidget(self.pages, 1)

        row = QHBoxLayout()
        self.skip_btn = QPushButton(translate("Welcome", "Skip"))
        self.skip_btn.clicked.connect(self._finish)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        self.back_btn = QPushButton(translate("Welcome", "Back"))
        self.back_btn.clicked.connect(lambda: self._go(self._step - 1))
        row.addWidget(self.back_btn)
        self.next_btn = QPushButton(translate("Welcome", "Next"))
        self.next_btn.clicked.connect(self._on_next)
        self.next_btn.setDefault(True)
        row.addWidget(self.next_btn)
        layout.addLayout(row)

        self._go(0)

    # --- the steps ---

    def _language_page(self) -> QWidget:
        """The first step, so the rest can be read in a language you understand."""
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        text = QLabel(translate(
            "Welcome",
            "Choose the language of the interface. It can be changed at any "
            "time in «File → Preferences»."))
        text.setWordWrap(True)
        box.addWidget(text)

        row = QHBoxLayout()
        self.language_combo = QComboBox()
        for code, label in language.available().items():
            self.language_combo.addItem(label, code)
        # The language in effect, not the system one. The window is already
        # drawn in whatever apply_saved() picked, so offering a different one
        # makes the wizard contradict itself — Chinese headings above a list
        # that says "Russian". Reachable without any trickery: a hive adopted
        # from the previous application name carries a language over, while
        # first_run_done is absent from the new hive by definition.
        self.language_combo.setCurrentIndex(
            max(self.language_combo.findData(language.current()), 0))
        self.language_combo.currentIndexChanged.connect(self._apply_language)
        row.addWidget(self.language_combo)
        row.addStretch(1)
        box.addLayout(row)
        box.addWidget(HintLabel(translate(
            "Welcome",
            "The interface language has nothing to do with the languages you "
            "translate between — those belong to the project.")))
        box.addStretch(1)
        return page

    def _databases_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        self.db_text = QLabel()
        self.db_text.setWordWrap(True)
        box.addWidget(self.db_text)

        row = QHBoxLayout()
        self.db_btn = QPushButton(translate("Welcome", "Build a database…"))
        self.db_btn.clicked.connect(self._on_build_database)
        row.addWidget(self.db_btn)
        row.addStretch(1)
        box.addLayout(row)
        box.addStretch(1)
        return page

    def _on_build_database(self) -> None:
        """Build a database — and re-read the page.

        The build window is modal, so control returns here only after it. Without
        re-reading the text the wizard would leave «there are no translation
        memory databases yet» on the screen right after one was built, and the
        person would walk the next step believing not a word of it.
        """
        self.buildDatabaseRequested.emit()
        self._refresh_databases_page()

    def _project_page(self) -> QWidget:
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        text = QLabel(translate(
            "Welcome",
            "A project holds everything: rows, statuses, translation memory and "
            "the history of the original. It is a single file you can copy or "
            "hand to another person."))
        text.setWordWrap(True)
        box.addWidget(text)

        row = QHBoxLayout()
        create = QPushButton(translate("Welcome", "Create a project…"))
        create.clicked.connect(self.createProjectRequested)
        create.clicked.connect(self.accept)
        row.addWidget(create)
        open_btn = QPushButton(translate("Welcome", "Open a project…"))
        open_btn.clicked.connect(self.openProjectRequested)
        open_btn.clicked.connect(self.accept)
        row.addWidget(open_btn)
        row.addStretch(1)
        box.addLayout(row)
        box.addStretch(1)
        return page

    # --- navigation ---

    def _refresh_databases_page(self) -> None:
        """The text of the step depends on whether databases exist: it must not lie in
        either direction."""
        found = len(project_mod.all_tm_databases())
        if found:
            self.db_text.setText(fill(translate(
                "Welcome",
                "Translation memory databases found: %1. They fill in strings "
                "the mod copied from the game and prompt you with how similar "
                "lines were translated before."), found))
            self.db_btn.setText(translate("Welcome", "Build one more…"))
        else:
            self.db_text.setText(translate(
                "Welcome",
                "There are no translation memory databases yet. A database "
                "built from your copy of the game fills in strings the mod "
                "copied from it — often hundreds of them — and prompts you "
                "with how similar lines were translated before.\n\n"
                "Building takes seconds and needs nothing but the game "
                "localization folders."))
            self.db_btn.setText(translate("Welcome", "Build a database…"))

    def _go(self, step: int) -> None:
        self._step = max(0, min(step, self.pages.count() - 1))
        self.pages.setCurrentIndex(self._step)
        headings = (
            translate("Welcome", "Interface language"),
            translate("Welcome", "Translation memory"),
            translate("Welcome", "First project"),
        )
        self.heading.setText(headings[self._step])
        if self._step == 1:
            self._refresh_databases_page()
        self.back_btn.setEnabled(self._step > 0)
        self.next_btn.setText(
            translate("Welcome", "Done") if self._step == self.pages.count() - 1
            else translate("Welcome", "Next"))

    def _on_next(self) -> None:
        if self._step == self.pages.count() - 1:
            self._finish()
            return
        self._go(self._step + 1)

    def _apply_language(self) -> None:
        from PySide6.QtWidgets import QApplication

        code = self.language_combo.currentData()
        if code:
            language.apply(QApplication.instance(), code)
        self._retranslate()

    def _retranslate(self) -> None:
        """The wizard outlives a language change, so the labels are replaced in place."""
        self.setWindowTitle(translate("Welcome", "Getting started"))
        self.skip_btn.setText(translate("Welcome", "Skip"))
        self.back_btn.setText(translate("Welcome", "Back"))
        self._go(self._step)

    def _finish(self) -> None:
        mark_done()
        self.accept()

    def done(self, result: int) -> None:
        # Closed with the cross — the wizard still counts as shown, and there is
        # nowhere for a second showing to come from: otherwise it would greet every
        # start.
        mark_done()
        super().done(result)
