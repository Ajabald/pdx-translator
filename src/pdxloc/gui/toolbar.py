"""The toolbar and the project context strip.

The icons come from the standard Qt style set: a set of our own would have to be
drawn and shipped, while these the theme repaints by itself.

The context — the project languages and the attached memory databases — sits on
the right of the header, the way ESP/ESM Translator always shows the game, the
encoding and the active database. This used to be information you had to go
hunting for through dialogs.
"""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QSizePolicy, QStyle, QToolBar, QToolButton,
    QWidget,
)

from pdxloc import project as project_mod
from pdxloc.core import games
from pdxloc.core.i18n import translate
from pdxloc.gui import actions as actions_mod
from pdxloc.gui.icons import icon as action_icon

CTX = "Toolbar"


def icon(widget: QWidget, name: str):
    """A standard Qt style icon, for the places that have none of their own yet."""
    return widget.style().standardIcon(getattr(QStyle, name))


class ContextBar(QWidget):
    """The project languages and the attached memory databases, always in sight."""

    tmSourcesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn: sqlite3.Connection | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(10)

        self.langs = QLabel()
        layout.addWidget(self.langs)

        self.tm_button = QToolButton()
        self.tm_button.setPopupMode(QToolButton.InstantPopup)
        self.tm_menu = QMenu(self.tm_button)
        self.tm_button.setMenu(self.tm_menu)
        layout.addWidget(self.tm_button)

        self.retranslate()
        self.set_project(None)

    def retranslate(self) -> None:
        """The context strip is rebuilt: everything written on it is dynamic."""
        self.langs.setToolTip(translate("Toolbar", "Project languages: original → translation"))
        self.tm_button.setToolTip(translate(
            "Toolbar", "Attached translation memory databases — they can be "
                       "switched on and off right here"))
        self.refresh()

    def set_project(self, conn: sqlite3.Connection | None) -> None:
        self.conn = conn
        self.refresh()

    def refresh(self) -> None:
        self.tm_menu.clear()
        if self.conn is None:
            self.langs.setText("")
            self.tm_button.setText(translate("Toolbar", "Memory databases"))
            self.tm_button.setEnabled(False)
            return
        self.tm_button.setEnabled(True)
        langs = project_mod.languages(self.conn)
        pair = f"{langs.src_lang} → {langs.tgt_lang}"
        if langs.split:
            # the text locales differ from the folders: show both, or the
            # header would lie about the language being translated into
            pair += f"  ({langs.src_locale} → {langs.tgt_locale})"
        # The game comes before the languages, as in EET where it is always in
        # sight: with projects for two games open there is otherwise no way to
        # notice you are editing the wrong one.
        self.langs.setText(f"{games.title(project_mod.game(self.conn))} · {pair}")

        enabled = set(project_mod.get_tm_sources(self.conn))
        entries_word = translate("Toolbar", "entries")
        total = 0
        for path, meta in project_mod.list_tm_databases(
                game=project_mod.game(self.conn)):
            entries = int(meta.get("entries", 0) or 0)
            act = QAction(f"{meta.get('name') or path.stem}  "
                          f"({entries} {entries_word})",
                          self.tm_menu)
            act.setCheckable(True)
            act.setChecked(path.name in enabled)
            act.toggled.connect(
                lambda checked, name=path.name: self._toggle(name, checked))
            self.tm_menu.addAction(act)
            if path.name in enabled:
                total += entries
        if self.tm_menu.isEmpty():
            empty = self.tm_menu.addAction(translate("Toolbar", "No databases yet"))
            empty.setEnabled(False)
        suffix = f" · {total} {entries_word}" if total else ""
        label = translate("Toolbar", "Memory databases")
        self.tm_button.setText(f"{label}: {len(enabled)}{suffix}")

    def _toggle(self, name: str, checked: bool) -> None:
        if self.conn is None:
            return
        names = project_mod.get_tm_sources(self.conn)
        if checked and name not in names:
            names.append(name)
        elif not checked and name in names:
            names.remove(name)
        else:
            return
        project_mod.set_tm_sources(self.conn, names)
        project_mod.attach_tm_sources(self.conn, project_mod.project_tm_paths(self.conn))
        self.refresh()
        self.tmSourcesChanged.emit()


def build_toolbar(window, registry) -> QToolBar:
    """Build the toolbar out of the action registry.

    The toolbar is a shop window, not a separate set of commands: every button
    must have a main-menu entry (see `actions.TOOLBAR` and the test that guards
    it). Four buttons used to have no menu entry at all, and two of those were
    standalone QAction duplicates of the table's own actions.
    """
    bar = QToolBar(translate("Toolbar", "Toolbar"), window)
    bar.setObjectName("main_toolbar")     # without a name Qt will not save its state

    for spec in actions_mod.ACTIONS:
        if spec.icon:
            glyph = action_icon(bar, spec.icon)
            if glyph is not None:
                registry[spec.id].setIcon(glyph)

    registry.fill_toolbar(bar, actions_mod.TOOLBAR)

    spacer = QWidget()
    spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    bar.addWidget(spacer)
    bar.addWidget(window.context_bar)
    return bar
