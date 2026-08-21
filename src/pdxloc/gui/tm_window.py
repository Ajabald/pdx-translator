"""The translation memory window — a single way in (F9).

There used to be three separate windows: «Translation memory», «Translation
memory databases» and «Create a database from folders», plus the project export
which opened nothing but a file dialog. All four are about the same thing and
kept referring to one another («a database can be switched off under Tools → …»).
Now they are tabs, and the state of the active tab lives in a shared strip along
the bottom — the counter moved away from buttons it had nothing to do with.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QTabWidget,
    QVBoxLayout,
)

from pdxloc.core.i18n import translate
from pdxloc.gui.tm_build_tab import TmBuildTab
from pdxloc.gui.tm_entries_tab import TmEntriesTab
from pdxloc.gui.tm_sources_tab import TmSourcesTab


class TmWindow(QDialog):
    """The translation memory tabs. Not all of them need a project.

    The first-run wizard opens this window **before** a single project exists:
    the first memory database is built ahead of the first translation. The window
    used not to survive that — `languages(None)` fell over right inside the
    button's slot, and a built application has no console (`console=False` in the
    spec), so the traceback went nowhere and the button looked dead.
    """

    def __init__(self, conn: sqlite3.Connection | None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle(translate("TmWindow", "Translation memory"))
        self.setMinimumSize(1000, 620)

        from pdxloc import project as project_mod

        # Without a project there is nowhere to take the languages from, so we take the
        # same defaults as the build tab itself: its folders are typed in by hand
        # anyway.
        src_lang, tgt_lang = "english", "russian"
        if conn is not None:
            langs = project_mod.languages(conn)
            src_lang, tgt_lang = langs.src_lang, langs.tgt_lang

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        # «Entries» is the project's own memory, «Databases» are the ones attached to
        # it. Without a project both would show an emptiness there is no way to
        # explain, so they are simply not there rather than «present but disabled».
        self.entries = TmEntriesTab(conn) if conn is not None else None
        self.sources = TmSourcesTab(conn) if conn is not None else None
        self.build = TmBuildTab(src_lang=src_lang, tgt_lang=tgt_lang, conn=conn)
        if self.entries is not None:
            self.tabs.addTab(self.entries, translate("TmWindow", "Entries"))
        if self.sources is not None:
            self.tabs.addTab(self.sources, translate("TmWindow", "Databases"))
        self.tabs.addTab(self.build, translate("TmWindow", "Build a database"))
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
        self.tabs.currentChanged.connect(lambda _: self._show_status())
        # a freshly built database must appear in the attachable list at once
        if self.sources is not None:
            self.build.databasesChanged.connect(self.sources.reload)
        self._show_status()

    def show_build_tab(self) -> None:
        """Open straight on the build tab, from the wizard and from the reminder."""
        self.tabs.setCurrentWidget(self.build)

    def _tabs(self):
        """Only the tabs that exist: without a project there is one.

        The `statusChanged` subscription and the timer shutdown both walk this
        same list, so a missing tab need only be left out here.
        """
        return tuple(tab for tab in (self.entries, self.sources, self.build)
                     if tab is not None)

    # --- the bottom strip ---

    def _on_tab_status(self, text: str) -> None:
        if self.sender() is self.tabs.currentWidget():
            self.status_label.setText(text)

    def _show_status(self) -> None:
        self.status_label.setText(self.tabs.currentWidget().status_text())

    # --- closing ---

    def _stop_timers(self) -> None:
        """Pending queries must not outlive the window.

        By then the project connection is sometimes already closed, and the timer
        fell over on a dead database. With several tabs about, they are put out
        centrally.
        """
        for tab in self._tabs():
            tab.shutdown()

    def _confirm_close_while_building(self) -> bool:
        """Do not close in silence in the middle of a build.

        In a window of its own modality saved us from this: there was nowhere to
        go. Among tabs a user easily switches to «Entries» and presses «Close»
        without remembering that a build is still running.
        """
        if not self.build.is_busy():
            return True
        answer = QMessageBox.question(
            self, translate("TmWindow", "Building a database"),
            translate("TmWindow",
                      "The database is still being built. Interrupt it and close "
                      "the window?\n\nAn unfinished database file will not be "
                      "created."))
        if answer != QMessageBox.Yes:
            return False
        self.build.cancel_build()
        return True

    def closeEvent(self, event) -> None:
        if not self._confirm_close_while_building():
            event.ignore()
            return
        self._stop_timers()
        super().closeEvent(event)

    def done(self, result: int) -> None:
        if not self._confirm_close_while_building():
            return
        self._stop_timers()
        super().done(result)
