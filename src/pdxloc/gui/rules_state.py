"""The rule set in force — one for the whole application.

The check is called from three places (the «!» column of the table, the recheck
of one row after an edit, the F6 report), and each of them used to call
`qa.check_unit` with no rule set, that is, always with the built-in values. A
setting has to reach all three at once, or the table and the report disagree in
their numbers on one and the same project.

Built after the pattern of `gui/prefs.py`: a value and a signal that it changed.
There are two layers — the global file next to the application and the overlay
inside the project file; their order and the merge rules are described in
`core/qa_rules.py`.
"""
from __future__ import annotations

import json
import sqlite3

from PySide6.QtCore import QObject, Signal

from pdxloc import project as project_module
from pdxloc import settings
from pdxloc.core import qa_rules
from pdxloc.core.qa_rules import RuleSet


class _Notifier(QObject):
    changed = Signal()


notifier = _Notifier()

_global: dict = {}
_project: dict = {}
_locale: str = ""          # the translation language of the open project
_game: str = ""            # and its game: together they pick the recommended preset
_ruleset: RuleSet = qa_rules.default_ruleset()


# --- reading ---

def ruleset() -> RuleSet:
    """The set the rows are being checked with right now."""
    return _ruleset


def global_overlay() -> dict:
    return dict(_global)


def project_overlay() -> dict:
    return dict(_project)


def preset() -> str:
    """The preset in force.

    The project's one overrides the global one, but only when it is set: «Own» in
    a project means «no preset of its own», and the global one stays in force —
    exactly the way `qa_rules.resolve` applies it.
    """
    chosen = _project.get("preset")
    if chosen in qa_rules.PRESETS and chosen != qa_rules.CUSTOM:
        return chosen
    return qa_rules.preset_of(_global)


def locale() -> str:
    """The translation language of the open project; language rules are silenced
    by it."""
    return _locale


def game() -> str:
    """The game of the open project. Empty means there is no project.

    The preset showcases need it: the recommended set is the one named after the
    game, and asking the connection for it on every repaint of the menu would be
    pointless — here it has already been read.
    """
    return _game


def _rebuild() -> None:
    global _ruleset
    _ruleset = qa_rules.resolve(_global, _project, locale=_locale)
    notifier.changed.emit()


# --- the global layer ---

def load_global() -> None:
    """Read the global settings file. A broken file is no reason to crash."""
    global _global
    path = settings.qa_rules_path()
    data: dict = {}
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, ValueError):
        data = {}
    _global = data
    _rebuild()


def save_global(overlay: dict) -> None:
    global _global
    path = settings.qa_rules_path()
    _global = dict(overlay)
    try:
        if qa_rules.is_empty_overlay(_global):
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_global, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except OSError:
        pass        # the setting is in force until the end of the session anyway
    _rebuild()


# --- the project layer ---

def open_project(conn: sqlite3.Connection) -> None:
    global _project, _locale, _game
    try:
        _project = project_module.get_qa_overlay(conn)
        _locale = project_module.languages(conn).tgt_locale
        _game = project_module.game(conn)
    except sqlite3.Error:
        _project, _locale, _game = {}, "", ""
    _rebuild()


def close_project() -> None:
    global _project, _locale, _game
    _project = {}
    _locale = ""
    _game = ""
    _rebuild()


def save_project(conn: sqlite3.Connection, overlay: dict) -> None:
    global _project
    _project = {} if qa_rules.is_empty_overlay(overlay) else dict(overlay)
    project_module.set_qa_overlay(conn, _project or None)
    _rebuild()


def on_change(slot) -> None:
    """Subscribe to a change of the rule set.

    The slot must be a bound method of a QObject: such a connection breaks itself
    when the widget is deleted, while a lambda would outlive it and reach into a
    dead C++ object.
    """
    notifier.changed.connect(slot)
