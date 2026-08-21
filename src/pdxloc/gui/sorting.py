"""Three-state sorting driven by a column header.

One click sorts ascending, the second descending, the third returns to the
natural order. Exactly one column is active: clicking another header clears the
previous one, or «sorted by three columns at once» becomes a state nobody can
see or explain.

The logic is deliberately kept out of the widget: it is tested without a window,
and the same little machine serves both the row table and the translation memory
table.

Qt's own sorting (`setSortingEnabled`) is not used: it knows two states only —
there is no third, «as it was» — and it calls `model.sort()` again after every
`endResetModel`.
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
            self.column, self.step = column, FIRST   # another column clears the previous one
        elif self.step == FIRST:
            self.step = SECOND
        else:
            self.column, self.step = None, OFF       # the third click

    def set(self, column: int | None, step: int = FIRST) -> None:
        self.column, self.step = (column, step) if column is not None else (None, OFF)

    def reset(self) -> None:
        self.column, self.step = None, OFF

    @property
    def active(self) -> bool:
        return self.column is not None
