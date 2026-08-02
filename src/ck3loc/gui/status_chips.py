"""Цветные чипы-счётчики статусов в статус-баре (как в ESP-ESM Translator).

Клик по чипу фильтрует таблицу по статусу; повторный клик — сброс фильтра.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ck3loc.core.stats import ProjectStats
from ck3loc.core.statuses import STATUS_LABELS, Status
from ck3loc.gui import theme

# порядок чипов слева направо
_CHIP_ORDER = (
    Status.UNTRANSLATED, Status.AUTO, Status.TRANSLATED, Status.REVIEWED,
    Status.STALE, Status.CUSTOM, Status.IGNORED,
)


class _Chip(QLabel):
    clicked = Signal(str)

    def __init__(self, status: Status, parent=None):
        super().__init__(parent)
        self.status = status
        self.active = False
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(34)
        self.setToolTip(STATUS_LABELS[status] + " — клик для фильтра")
        self.setCursor(Qt.PointingHandCursor)
        self.set_count(0)
        theme.on_change(self._restyle)

    def _restyle(self) -> None:
        width = "2px" if self.active else "1px"
        edge = theme.color("chip.border.active" if self.active else "chip.border")
        self.setStyleSheet(
            f"QLabel {{ background: {theme.status_color(self.status)}; "
            f"color: {theme.color('chip.text')}; "
            f"border: {width} solid {edge}; border-radius: 3px; padding: 1px 6px; }}"
        )

    def set_count(self, n: int) -> None:
        self.setText(str(n))
        self._restyle()

    def set_active(self, active: bool) -> None:
        self.active = active
        self.set_count(int(self.text()))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.status.value)
        super().mousePressEvent(event)


class StatusChipsBar(QWidget):
    chipClicked = Signal(str)   # значение Status или '' при сбросе

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(3)
        self._chips: dict[str, _Chip] = {}
        self._active: str | None = None
        for status in _CHIP_ORDER:
            chip = _Chip(status)
            chip.clicked.connect(self._on_chip)
            layout.addWidget(chip)
            self._chips[status.value] = chip

    def set_stats(self, stats: ProjectStats) -> None:
        for status_value, chip in self._chips.items():
            chip.set_count(stats.counts.get(status_value, 0))

    def _on_chip(self, status_value: str) -> None:
        if self._active == status_value:
            self.set_active_filter(None)
            self.chipClicked.emit("")
        else:
            self.set_active_filter(status_value)
            self.chipClicked.emit(status_value)

    def set_active_filter(self, status_value: str | None) -> None:
        self._active = status_value
        for value, chip in self._chips.items():
            chip.set_active(value == status_value)
