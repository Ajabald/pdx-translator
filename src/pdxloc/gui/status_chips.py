"""Цветные чипы-счётчики статусов в статус-баре (как в ESP-ESM Translator).

Клик по чипу фильтрует таблицу по статусу; повторный клик — сброс фильтра.
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

# порядок чипов слева направо — общий с фильтрами и сортировкой колонки «Статус»
_CHIP_ORDER = STATUS_ORDER

# Чип замечаний стоит особняком: замечание — не статус, строка с ним имеет свой
# собственный. Отсюда и отдельное значение, и подпись со знаком.
ISSUES = "!"


class _Chip(QLabel):
    clicked = Signal(str)

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        self.value = value          # значение Status или ISSUES
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
        # Число хранится отдельно от подписи: у чипа замечаний в ней ещё и знак,
        # и разбирать её обратно значило бы ронять чип на собственном тексте.
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
    chipClicked = Signal(str)     # значение Status или '' при сбросе
    issuesClicked = Signal()      # чип «!» — переключить фильтр по замечаниям

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

        layout.addSpacing(6)      # замечание не статус — и стоит отдельно
        self.issues_chip = _Chip(ISSUES)
        self.issues_chip.clicked.connect(lambda _: self.issuesClicked.emit())
        layout.addWidget(self.issues_chip)

    def set_stats(self, stats: ProjectStats) -> None:
        for status_value, chip in self._chips.items():
            chip.set_count(stats.counts.get(status_value, 0))

    def set_issues(self, count: int, active: bool) -> None:
        """Замечаний столько **среди загруженных строк**, а не по проекту.

        Проверка не хранится в базе: колонка «!» считается по строкам, которые
        уже отобраны фильтрами. Пересчитывать её по всему проекту на каждое
        сохранение — секунды на большом моде, и ради числа в статус-баре это
        слишком дорого. Без фильтров загружен весь проект, и число совпадает.
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
