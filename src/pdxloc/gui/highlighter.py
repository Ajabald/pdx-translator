"""Подсветка CK3-разметки в текстах локализации."""
from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from pdxloc.core import markup
from pdxloc.gui import theme

# Что и каким цветом подсвечивать — в core/markup.py. Порядок значим: позднее
# правило перекрывает раннее на пересекающихся кусках.
RULE_SPECS: tuple[tuple[re.Pattern, str, bool], ...] = markup.highlight_rules()

_cache: dict[str, list[tuple[re.Pattern, QTextCharFormat]]] = {}


def _rules() -> list[tuple[re.Pattern, QTextCharFormat]]:
    """Форматы текущей темы. Кэш по теме — их пересоздание на каждый блок дорого."""
    name = theme.current()
    if name not in _cache:
        rules = []
        for pattern, key, bold in RULE_SPECS:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(theme.color(key)))
            if bold:
                fmt.setFontWeight(QFont.Bold)
            rules.append((pattern, fmt))
        _cache[name] = rules
    return _cache[name]


class Ck3Highlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        theme.on_change(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in _rules():
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
