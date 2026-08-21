"""The single source of truth about what is shown and in what order.

The filter is set from five places: the filter bar above the table, the
status-bar chips, the file tree, the scan summary and the «Filters» menu. Each of
them used to hold state of its own — the chips, for one, lit up only when the
chips themselves were clicked, while the «Show» button in the summary moved the
combo box straight past them. Now the state is here alone, and the controls are
merely its shop windows: they write here and repaint on a signal.

There are two signals, and that matters:

* `changed` — the set of rows changed; a new SQL query and a recount of the
  issues are needed (about 45 ms over 5k rows);
* `sortChanged` — only the order changed; reordering the already loaded rows is
  enough (5–10 ms).

Pushing a click on a column header through a full reload would mean recomputing
every quality check on every press.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from pdxloc.gui.sorting import FIRST, SECOND, SortState
from pdxloc.gui.units_model import COL_ISSUES, UnitFilters


class ViewState(QObject):
    changed = Signal()       # the set of rows changed
    sortChanged = Signal()   # only the order changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status: str | None = None
        self.search = ""
        self.show_deleted = False
        self.file_rel: str | None = None
        self.file_prefix: str | None = None
        self.sort = SortState()

    # --- derived ---

    @property
    def only_issues(self) -> bool:
        """The «only with issues» filter — the second step of the «!» column.

        There is deliberately no field of its own: while there were two of them,
        the checkbox and the column, they drifted apart. The checkbox, the menu
        entry and the toolbar button are three windows onto one value.
        """
        return self.sort.column == COL_ISSUES and self.sort.step == SECOND

    @property
    def sort_spec(self) -> tuple[int, bool] | None:
        """(column, descending) or None for the natural order."""
        if self.sort.column is None:
            return None
        # on the «!» column the second step narrows the selection rather than reversing
        # the order: there is no point showing the troubled rows at the bottom
        descending = self.sort.step == SECOND and self.sort.column != COL_ISSUES
        return self.sort.column, descending

    def filters(self) -> UnitFilters:
        return UnitFilters(
            status=self.status,
            file_rel=self.file_rel,
            file_prefix=self.file_prefix,
            search=self.search,
            show_deleted=self.show_deleted,
            only_issues=self.only_issues,
        )

    # --- changing ---

    def set_status(self, value: str | None) -> None:
        if value != self.status:
            self.status = value
            self.changed.emit()

    def set_search(self, value: str) -> None:
        value = value.strip()
        if value != self.search:
            self.search = value
            self.changed.emit()

    def set_show_deleted(self, value: bool) -> None:
        if value != self.show_deleted:
            self.show_deleted = value
            self.changed.emit()

    def set_only_issues(self, value: bool) -> None:
        if value == self.only_issues:
            return
        if value:
            self.sort.set(COL_ISSUES, SECOND)
        else:
            # The box was cleared, so the filter goes, but the «troubled first» order
            # stays: rows do not jump about when the selection widens, and it stays visible
            # where the troubled ones lie among the rest.
            self.sort.step = FIRST
        self.changed.emit()

    def set_file(self, file_rel: str | None, file_prefix: str | None) -> None:
        if (file_rel, file_prefix) != (self.file_rel, self.file_prefix):
            self.file_rel, self.file_prefix = file_rel, file_prefix
            self.changed.emit()

    def click_column(self, column: int) -> None:
        was_filtered = self.only_issues
        self.sort.click(column)
        # only the «!» column changes the set of rows; the rest need a reorder
        if was_filtered != self.only_issues:
            self.changed.emit()
        else:
            self.sortChanged.emit()

    def set_sort(self, column: int | None, descending: bool = False) -> None:
        """Set the sorting explicitly, from the «View → Sort» submenu."""
        was_filtered = self.only_issues
        self.sort.set(column, SECOND if descending else FIRST)
        if was_filtered != self.only_issues:
            self.changed.emit()
        else:
            self.sortChanged.emit()

    def reset_filters(self) -> None:
        """Clear the filters but not the sorting.

        The order of the rows hides nothing, and `jump_to_unit` calls the reset
        precisely in order to show a row a filter was hiding.
        """
        self.status = None
        self.search = ""
        self.show_deleted = False
        self.file_rel = self.file_prefix = None
        if self.only_issues:
            self.sort.step = FIRST      # the filter is gone, the order is kept
        self.changed.emit()
