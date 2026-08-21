"""The colour themes of the interface.

Every colour in the application is gathered here, in two sets. They used to be
scattered across modules (`core/statuses.py`, `gui/highlighter.py`, the table
model) and were meant for a light background only: on a dark one the markup
highlighting and the status fills turned unreadable.

The light set holds exactly the values that existed before the themes, so the
familiar look did not shift. A change of theme applies on the fly: subscribers
get the `notifier.changed` signal and repaint.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette

from pdxloc.core.i18n import QT_TRANSLATE_NOOP
from pdxloc.core.statuses import Status

LIGHT = "light"
DARK = "dark"
THEME_LABELS = {LIGHT: QT_TRANSLATE_NOOP("Theme", "Light"),
                DARK: QT_TRANSLATE_NOOP("Theme", "Dark")}

_LIGHT: dict[str, str] = {
    "text": "#202020",
    "hint": "#555555",
    "text.disabled": "#999999",   # the entry exists but is unavailable (file not found)
    "text.placeholder": "#767676",  # the hint in an empty field: quieter than typed text
    # the fill of table rows by status
    f"status.{Status.UNTRANSLATED}": "#f8d0d0",
    # a muted warm tone, next to the yellow of «Auto» but noticeably paler: the
    # row is filled in, but nobody has looked at it
    f"status.{Status.MACHINE}": "#f0e4cd",
    f"status.{Status.AUTO}": "#fff3c4",
    f"status.{Status.TRANSLATED}": "#d6f0d6",
    f"status.{Status.REVIEWED}": "#b2e0c8",
    f"status.{Status.STALE}": "#ffdcae",
    f"status.{Status.IGNORED}": "#dde3e8",
    f"status.{Status.CUSTOM}": "#e2d5f1",
    "chip.text": "#202020",
    "chip.border": "#909090",
    "chip.border.active": "#303030",
    # the glyphs of the quick columns
    "quick.reviewed": "#2e7d32",
    "quick.translated": "#c62828",
    "quick.custom": "#7b1fa2",
    "quick.ignored": "#546e7a",
    "quick.disabled": "#c8c8c8",
    # the nature of an edit to the original
    "change.cosmetic": "#8d6e63",
    "change.meaningful": "#e65100",
    # the issues of the check
    "issue.error": "#c62828",
    "issue.warning": "#ef6c00",
    "issue.info": "#4a6f8a",      # a signal rather than an error: a reason to go and look
    "issue.row": "#f8d0d0",       # the fill of an error row in the check report
    "warning.text": "#a04000",    # the warning under a field in dialogs
    # the file tree
    "tree.complete": "#1d7a1d",   # the file is translated in full
    "tree.partial": "#404040",
    # translation memory
    "tm.readonly": "#6f6f6f",     # entries of attached databases: read-only
    # CK3 markup highlighting
    "markup.bracket": "#1857c3",
    "markup.dollar": "#8017c9",
    "markup.icon": "#9a7a00",
    "markup.format": "#3e7d47",
    "markup.escape": "#c86a1f",
    # changes to the original
    "diff.insert": "#c8f0c8",
    "diff.delete": "#f6c8c8",
    # a glossary term in the original field. It lands on the same field as
    # diff.insert and has to be told apart from it: on an outdated row both
    # highlights are visible at once.
    "glossary.term": "#ffe9a8",
}

_DARK: dict[str, str] = {
    "text": "#e8e8e8",
    "hint": "#a0a0a0",
    "text.disabled": "#6f6f6f",
    "text.placeholder": "#8a8a8a",
    f"status.{Status.UNTRANSLATED}": "#4d2b2b",
    f"status.{Status.MACHINE}": "#453a2a",
    f"status.{Status.AUTO}": "#4a4222",
    f"status.{Status.TRANSLATED}": "#28402b",
    f"status.{Status.REVIEWED}": "#1f4739",
    f"status.{Status.STALE}": "#4d3b1f",
    f"status.{Status.IGNORED}": "#343b41",
    f"status.{Status.CUSTOM}": "#3b3050",
    "chip.text": "#e8e8e8",
    "chip.border": "#6a6a6a",
    "chip.border.active": "#d0d0d0",
    "quick.reviewed": "#71c476",
    "quick.translated": "#ef7070",
    "quick.custom": "#c48ee0",
    "quick.ignored": "#9fb3bf",
    "quick.disabled": "#5a5a5a",
    "change.cosmetic": "#c0a89f",
    "change.meaningful": "#ffa347",
    "issue.error": "#ff8080",
    "issue.warning": "#ffb14d",
    "issue.info": "#8fb8d0",
    "issue.row": "#4d2b2b",
    "warning.text": "#ffa347",
    "tree.complete": "#71c476",
    "tree.partial": "#c0c0c0",
    "tm.readonly": "#9a9a9a",
    "markup.bracket": "#7dabf5",
    "markup.dollar": "#c791f2",
    "markup.icon": "#dcbb52",
    "markup.format": "#83cd91",
    "markup.escape": "#f2a56c",
    "diff.insert": "#2d5633",
    "diff.delete": "#5d2f2f",
    "glossary.term": "#5a4a1e",
}

_PALETTES = {LIGHT: _LIGHT, DARK: _DARK}


class _Notifier(QObject):
    changed = Signal()


notifier = _Notifier()

_current = LIGHT


def current() -> str:
    return _current


def is_dark() -> bool:
    return _current == DARK


def colors() -> dict[str, str]:
    return _PALETTES[_current]


def color(key: str) -> str:
    """A colour by name. A missing name is a developer's mistake, not a user's."""
    return _PALETTES[_current][key]


def qcolor(key: str) -> QColor:
    return QColor(color(key))


def status_color(status: Status | str) -> str:
    return color(f"status.{Status(status)}")


def _dark_palette() -> QPalette:
    """The dark Qt palette: without it the menus and the fields would stay light."""
    bg = QColor("#2b2b2b")
    base = QColor("#232323")
    text = QColor(_DARK["text"])
    p = QPalette()
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, bg)
    p.setColor(QPalette.ToolTipBase, QColor("#3a3a3a"))
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, bg)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor("#ff6b6b"))
    p.setColor(QPalette.Link, QColor("#7dabf5"))
    p.setColor(QPalette.Highlight, QColor("#3d6ea5"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    # without this line the role would keep the light style's value — dark text
    # with transparency, legible on Base #232323 only under a magnifying glass
    p.setColor(QPalette.PlaceholderText, QColor(_DARK["text.placeholder"]))
    disabled = QColor("#7a7a7a")
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, role, disabled)
    return p


def apply_theme(app, name: str, *, save: bool = True) -> None:
    """Switch the application theme and tell the subscribers about it."""
    global _current
    if name not in _PALETTES:
        name = LIGHT
    _current = name
    if app is not None:
        app.setPalette(_dark_palette() if name == DARK
                       else app.style().standardPalette())
    if save:
        from pdxloc import settings

        settings.qsettings().setValue("theme", name)
    notifier.changed.emit()


def saved_theme() -> str:
    from pdxloc import settings

    value = settings.qsettings().value("theme", LIGHT)
    return value if value in _PALETTES else LIGHT


def apply_saved(app) -> None:
    """Restore the theme chosen last time."""
    apply_theme(app, saved_theme(), save=False)


def on_change(slot) -> None:
    """Subscribe to a change of theme.

    The slot must be a bound method of a QObject: such a connection breaks itself
    when the widget is deleted. A lambda would outlive it and reach into a dead
    C++ object.
    """
    notifier.changed.connect(slot)
