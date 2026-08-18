"""Мелкие виджеты, общие для окон.

Заведены ради одного: цвет здесь берётся из `theme.py` и меняется вместе с
темой. Раньше подписи красились литералом цвета в `setStyleSheet` прямо в
диалогах — на тёмной теме такой текст становился нечитаемым, а найти все места
можно было только грепом.
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from pdxloc.gui import theme


class _ThemedLabel(QLabel):
    """Подпись, знающая своё имя цвета в палитре."""

    COLOR_KEY = "text"

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self._restyle()
        theme.on_change(self._restyle)

    def _restyle(self) -> None:
        self.setStyleSheet(f"color: {theme.color(self.COLOR_KEY)};")


class HintLabel(_ThemedLabel):
    """Приглушённая поясняющая подпись."""

    COLOR_KEY = "hint"


class WarningLabel(_ThemedLabel):
    """Предупреждение: заметно, но не паникёрски."""

    COLOR_KEY = "warning.text"
