"""Трёхпозиционная сортировка по заголовку колонки.

Клик — по возрастанию, второй — по убыванию, третий — назад к естественному
порядку. Активна ровно одна колонка: клик по чужому заголовку сбрасывает
прежнюю, иначе «сортировка по трём колонкам сразу» превращается в состояние,
которое нельзя ни увидеть, ни объяснить.

Логика вынесена из виджета намеренно: её проверяют без окна, и одна и та же
машинка обслуживает таблицу строк и таблицу памяти переводов.

Встроенную сортировку Qt (`setSortingEnabled`) не используем: она знает только
два состояния, третьего — «как было» — в ней нет, а после каждого
`endResetModel` она заново дёргает `model.sort()`.
"""
from __future__ import annotations

from dataclasses import dataclass

OFF, FIRST, SECOND = 0, 1, 2


@dataclass
class SortState:
    column: int | None = None
    step: int = OFF

    def click(self, column: int) -> None:
        if self.column != column:
            self.column, self.step = column, FIRST   # чужая колонка — сброс прежней
        elif self.step == FIRST:
            self.step = SECOND
        else:
            self.column, self.step = None, OFF       # третий клик

    def set(self, column: int | None, step: int = FIRST) -> None:
        self.column, self.step = (column, step) if column is not None else (None, OFF)

    def reset(self) -> None:
        self.column, self.step = None, OFF

    @property
    def active(self) -> bool:
        return self.column is not None
