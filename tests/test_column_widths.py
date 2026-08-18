"""Ширины колонок переживают перезапуск.

Мелочь, которую замечают ежедневно: человек подгоняет таблицу под свой экран, а
следующий запуск возвращает всё к умолчаниям. В EET это `ColumnsSizes`, у нас
не было.
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
    """Таблица с моделью.

    Без модели у представления нет колонок вовсе, и любая ширина читается
    нулём — проверять было бы нечего.
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

    fresh = make_table(db, qtbot)   # configure_columns он же и восстанавливает

    assert fresh.columnWidth(COL_KEY) == 333
    assert fresh.columnWidth(COL_FILE) == 111


def test_only_resizable_columns_are_remembered(table) -> None:
    """Записывать `Stretch` и `Fixed` нельзя.

    У растянутой колонки ширина считается по окну; сохрани её один раз — и
    следующий запуск на другом экране получит вчерашнее число вместо расчёта.
    """
    header = table.horizontalHeader()
    assert header.sectionResizeMode(COL_EN) == QHeaderView.Stretch
    assert header.sectionResizeMode(COL_ISSUES) == QHeaderView.Fixed

    saved = dict(table._resizable_columns())
    assert COL_KEY in saved and COL_FILE in saved
    assert COL_EN not in saved and COL_ISSUES not in saved


def test_a_zero_width_is_ignored(table, qtbot) -> None:
    """Нулевая ширина прячет колонку насовсем — восстанавливать такое нельзя.

    Прятать колонки — дело «Вид → Колонки», и там это обратимо галкой. Ширина
    в ноль обратной дороги не оставляет: тянуть будет не за что.
    """
    from pdxloc import settings

    settings.qsettings().setValue("view/column_widths", "Key=0|File=-5")
    table.configure_columns()
    assert table.columnWidth(COL_KEY) > 0
    assert table.columnWidth(COL_FILE) > 0


def test_a_broken_setting_does_not_break_the_table(table) -> None:
    """Куст настроек правят руками; мусор оттуда не повод остаться без таблицы."""
    from pdxloc import settings

    settings.qsettings().setValue("view/column_widths", "мусор|Key=|=7|Key=abc")
    table.configure_columns()
    assert table.columnWidth(COL_KEY) > 0


def test_nothing_saved_means_defaults(table, db, qtbot) -> None:
    from pdxloc import settings

    settings.qsettings().remove("view/column_widths")
    fresh = make_table(db, qtbot)
    assert fresh.columnWidth(COL_KEY) == 260      # умолчание из configure_columns
