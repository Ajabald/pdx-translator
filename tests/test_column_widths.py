"""The column widths survive a restart.

A small thing noticed daily: a human fits the table to their screen, and the next
start brings everything back to the defaults. In EET that is `ColumnsSizes`, and
we had none.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QHeaderView  # noqa: E402

from pdxloc.gui.units_model import (  # noqa: E402
    COL_EN, COL_FILE, COL_ISSUES, COL_KEY, UnitsTableModel, UnitsTableView,
)


def make_table(conn, qtbot) -> UnitsTableView:
    """A table with a model.

    Without a model the view has no columns at all, and any width reads as zero —
    there would be nothing to check.
    """
    view = UnitsTableView()
    qtbot.addWidget(view)
    view.setModel(UnitsTableModel(conn))
    view.configure_columns()
    return view


@pytest.fixture
def table(db, qtbot):
    return make_table(db, qtbot)


def test_a_dragged_width_comes_back(table, db, qtbot) -> None:
    table.setColumnWidth(COL_KEY, 333)
    table.setColumnWidth(COL_FILE, 111)
    table.save_column_widths()

    fresh = make_table(db, qtbot)   # configure_columns restores them as well

    assert fresh.columnWidth(COL_KEY) == 333
    assert fresh.columnWidth(COL_FILE) == 111


def test_only_resizable_columns_are_remembered(table) -> None:
    """Writing `Stretch` and `Fixed` down will not do.

    The width of a stretched column is computed from the window; save it once —
    and the next start on another screen gets yesterday's number instead of a
    calculation.
    """
    header = table.horizontalHeader()
    assert header.sectionResizeMode(COL_EN) == QHeaderView.Stretch
    assert header.sectionResizeMode(COL_ISSUES) == QHeaderView.Fixed

    saved = dict(table._resizable_columns())
    assert COL_KEY in saved and COL_FILE in saved
    assert COL_EN not in saved and COL_ISSUES not in saved


def test_a_zero_width_is_ignored(table, qtbot) -> None:
    """A zero width hides a column for good — restoring such a thing will not do.

    Hiding columns is the business of «View → Columns», and there it is reversible
    by a tick. A width of zero leaves no way back: there would be nothing to pull by.
    """
    from pdxloc import settings

    settings.qsettings().setValue("view/column_widths", "Key=0|File=-5")
    table.configure_columns()
    assert table.columnWidth(COL_KEY) > 0
    assert table.columnWidth(COL_FILE) > 0


def test_a_broken_setting_does_not_break_the_table(table) -> None:
    """The settings hive gets edited by hand; rubbish out of it is no reason to be left without a table."""
    from pdxloc import settings

    settings.qsettings().setValue("view/column_widths", "мусор|Key=|=7|Key=abc")
    table.configure_columns()
    assert table.columnWidth(COL_KEY) > 0


def test_nothing_saved_means_defaults(table, db, qtbot) -> None:
    from pdxloc import settings

    settings.qsettings().remove("view/column_widths")
    fresh = make_table(db, qtbot)
    assert fresh.columnWidth(COL_KEY) == 260      # the default out of configure_columns
