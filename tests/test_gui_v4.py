"""GUI-тесты v4: колонка Δ и подсветка изменений в поле оригинала."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from ck3loc.core.scanner import scan_project  # noqa: E402
from ck3loc.core.statuses import Status  # noqa: E402
from ck3loc.gui.detail_pane import DetailPane  # noqa: E402
from ck3loc.gui.units_model import (  # noqa: E402
    COL_CHANGE, COL_RU, QUICK_COLS, UnitFilters, UnitsTableModel,
)

from test_scanner import get_unit, make_project  # noqa: E402

EN_V1 = ('l_english:\n'
         ' cosm:0 "The lord of Winterfell."\n'
         ' mean:0 "The old lord of Winterfell"\n')
RU_V1 = ('l_russian:\n'
         ' cosm:0 "Лорд Винтерфелла."\n'
         ' mean:0 "Старый лорд Винтерфелла"\n')


@pytest.fixture
def updated(db, make_tree):
    """Проект после обновления мода: одна косметическая правка, одна смысловая."""
    en = make_tree({"m_l_english.yml": EN_V1}, "en")
    ru = make_tree({"m_l_russian.yml": RU_V1}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"m_l_english.yml": (
        'l_english:\n'
        ' cosm:0 "The lord of Winterfell"\n'          # убрана точка
        ' mean:0 "The young lord of Winterfell"\n')}, "en")
    scan_project(db, pid)
    return db, pid


def test_change_column_marks(updated, qtbot):
    conn, pid = updated
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters())
    marks = {}
    for i in range(model.rowCount()):
        key = model.row_data(i)["key"]
        marks[key] = model.data(model.index(i, COL_CHANGE), Qt.DisplayRole)
    assert marks["cosm"] == "·"        # косметическая
    assert marks["mean"] == "!"        # смысловая


def test_change_column_tooltip_and_color(updated, qtbot):
    conn, pid = updated
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters(search="mean"))
    idx = model.index(0, COL_CHANGE)
    assert "смыслу" in model.data(idx, Qt.ToolTipRole)
    assert model.data(idx, Qt.ForegroundRole) is not None


def test_no_mark_for_untouched_rows(db, make_tree, qtbot):
    en = make_tree({"m_l_english.yml": EN_V1}, "en")
    ru = make_tree({"m_l_russian.yml": RU_V1}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    model = UnitsTableModel(db)
    model.reload(pid, UnitFilters())
    assert model.data(model.index(0, COL_CHANGE), Qt.DisplayRole) == ""


def test_detail_pane_highlights_changes(updated, qtbot):
    """Изменённые куски подсвечены прямо в поле оригинала."""
    conn, pid = updated
    pane = DetailPane(conn)
    qtbot.addWidget(pane)
    pane.load_unit(get_unit(conn, "mean")["id"])

    selections = pane.en_view.extraSelections()
    assert selections, "изменения должны подсвечиваться"
    text = pane.en_view.toPlainText()
    highlighted = [
        text[s.cursor.selectionStart():s.cursor.selectionEnd()] for s in selections]
    assert "young" in " ".join(highlighted)
    # isVisible() в offscreen-режиме всегда False: окно не показано на экране,
    # поэтому спрашиваем видимость относительно родителя
    assert pane.diff_view.isVisibleTo(pane)


def test_no_highlight_for_unchanged_unit(db, make_tree, qtbot):
    en = make_tree({"m_l_english.yml": EN_V1}, "en")
    ru = make_tree({"m_l_russian.yml": RU_V1}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    pane = DetailPane(db)
    qtbot.addWidget(pane)
    pane.load_unit(get_unit(db, "cosm")["id"])
    assert pane.en_view.extraSelections() == []
    assert not pane.diff_view.isVisibleTo(pane)


def test_highlight_cleared_when_switching_rows(updated, qtbot):
    conn, pid = updated
    pane = DetailPane(conn)
    qtbot.addWidget(pane)
    pane.load_unit(get_unit(conn, "mean")["id"])
    assert pane.en_view.extraSelections()
    # актуализируем строку — подсветка должна исчезнуть
    from ck3loc.core import unit_ops
    unit_ops.actualize(conn, [get_unit(conn, "mean")["id"]])
    pane.load_unit(get_unit(conn, "mean")["id"])
    assert pane.en_view.extraSelections() == []


def test_cosmetic_label_in_diff_header(updated, qtbot):
    conn, pid = updated
    pane = DetailPane(conn)
    qtbot.addWidget(pane)
    pane.load_unit(get_unit(conn, "cosm")["id"])
    assert "косметическая" in pane.diff_label.text()


def test_quick_columns_shifted_correctly(updated, qtbot):
    """Колонка Δ вставлена перед quick-колонками — проверяем, что они не разъехались."""
    conn, pid = updated
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters())
    for col, (glyph, _status, _tip, _color) in QUICK_COLS.items():
        assert model.data(model.index(0, col), Qt.DisplayRole) == glyph
    assert model.flags(model.index(0, COL_RU)) & Qt.ItemIsEditable
