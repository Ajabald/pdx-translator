"""Small widgets shared between windows.

They exist for one reason: the colour comes from `theme.py` and follows the
theme. Labels used to hard-code a colour in `setStyleSheet` inside the dialogs
themselves — on the dark theme such text turned unreadable, and the only way to
find every offender was to grep for it.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from pdxloc.gui import theme


class _ThemedLabel(QLabel):
    """A label that knows its own colour name in the palette."""

    COLOR_KEY = "text"

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self._restyle()
        theme.on_change(self._restyle)

    def _restyle(self) -> None:
        self.setStyleSheet(f"color: {theme.color(self.COLOR_KEY)};")


class HintLabel(_ThemedLabel):
    """A muted explanatory label."""

    COLOR_KEY = "hint"


class WarningLabel(_ThemedLabel):
    """A warning: noticeable, but not alarmist."""

    COLOR_KEY = "warning.text"
