"""Coloured status counters in the status bar, as in ESP-ESM Translator.

Clicking a chip filters the table by that status; clicking it again clears the
filter.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from pdxloc.core import statuses as statuses_mod
from pdxloc.core.i18n import translate
from pdxloc.core.stats import ProjectStats
from pdxloc.core.statuses import STATUS_ORDER, Status
from pdxloc.gui import theme

CTX = "StatusChips"

# the left-to-right order is shared with the filters and with the sorting of
# the «Status» column
_CHIP_ORDER = STATUS_ORDER

# The issues chip stands apart: an issue is not a status, and a row carrying one
# still has a status of its own. Hence both the separate value and the label with
# a mark on it.
ISSUES = "!"


class _Chip(QLabel):
    clicked = Signal(str)

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        self.value = value          # a Status value, or ISSUES
        self.active = False
        self.count = 0
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(34)
        self.setCursor(Qt.PointingHandCursor)
        self.retranslate()
        self.set_count(0)
        theme.on_change(self._restyle)

    def retranslate(self) -> None:
        if self.value == ISSUES:
            self.setToolTip(translate(
                "StatusChips",
                "Rows with issues among those loaded — click to keep only them"))
            return
        self.setToolTip(
            translate("StatusChips", "%1 — click to filter").replace(
                "%1", statuses_mod.label(Status(self.value))))

    def _color(self) -> str:
        if self.value == ISSUES:
            return theme.color("issue.error")
        return theme.status_color(Status(self.value))

    def _restyle(self) -> None:
        width = "2px" if self.active else "1px"
        edge = theme.color("chip.border.active" if self.active else "chip.border")
        self.setStyleSheet(
            f"QLabel {{ background: {self._color()}; "
            f"color: {theme.color('chip.text')}; "
            f"border: {width} solid {edge}; border-radius: 3px; padding: 1px 6px; }}"
        )

    def set_count(self, n: int) -> None:
        # The count is kept apart from the label: on the issues chip the label
        # also carries a mark, and parsing it back would mean breaking the chip
        # on its own text.
        self.count = n
        self.setText(f"! {n}" if self.value == ISSUES else str(n))
        self._restyle()

    def set_active(self, active: bool) -> None:
        self.active = active
        self.set_count(self.count)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.value)
        super().mousePressEvent(event)


class StatusChipsBar(QWidget):
    chipClicked = Signal(str)     # a Status value, or '' when cleared
    issuesClicked = Signal()      # the «!» chip toggles the issues filter

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(3)
        self._chips: dict[str, _Chip] = {}
        self._active: str | None = None
        for status in _CHIP_ORDER:
            chip = _Chip(status.value)
            chip.clicked.connect(self._on_chip)
            layout.addWidget(chip)
            self._chips[status.value] = chip

        layout.addSpacing(6)      # an issue is not a status, and stands apart
        self.issues_chip = _Chip(ISSUES)
        self.issues_chip.clicked.connect(lambda _: self.issuesClicked.emit())
        layout.addWidget(self.issues_chip)

    def set_stats(self, stats: ProjectStats) -> None:
        for status_value, chip in self._chips.items():
            chip.set_count(stats.counts.get(status_value, 0))

    def set_issues(self, count: int, active: bool) -> None:
        """That many issues **among the loaded rows**, not across the project.

        The check is not stored in the database: the «!» column is computed over
        the rows the filters have already selected. Recomputing it across the
        whole project on every save costs seconds on a large mod, which is far
        too much for a number in the status bar. With no filters the whole
        project is loaded and the two numbers agree.
        """
        self.issues_chip.set_count(count)
        self.issues_chip.set_active(active)

    def retranslate(self) -> None:
        for chip in self._chips.values():
            chip.retranslate()
        self.issues_chip.retranslate()

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
