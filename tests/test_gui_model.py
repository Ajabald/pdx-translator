"""GUI-тесты (pytest-qt, offscreen): модель таблицы + смоук конструирования окон."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from pdxloc.core import statuses as statuses_mod  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.core.statuses import Status  # noqa: E402
from pdxloc.gui.units_model import COL_EN, COL_STATUS, UnitFilters, UnitsTableModel  # noqa: E402

from test_scanner import EN, RU, make_project  # noqa: E402


@pytest.fixture
def scanned(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    return db, pid


def test_model_load_and_roles(scanned, qtbot):
    conn, pid = scanned
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters())
    assert model.rowCount() == 2
    statuses = {model.data(model.index(i, COL_STATUS), Qt.DisplayRole) for i in range(2)}
    # подписи берутся из statuses.label(): в тестах переводчик не установлен,
    # поэтому виден язык оригинала
    assert statuses == {statuses_mod.label(Status.TRANSLATED),
                        statuses_mod.label(Status.UNTRANSLATED)}
    # цвет фона есть у любых строк
    assert model.data(model.index(0, COL_EN), Qt.BackgroundRole) is not None
    # UserRole отдаёт unit_id
    uid = model.data(model.index(0, 0), Qt.UserRole)
    assert isinstance(uid, int)
    assert model.row_of_unit(uid) == 0


def test_model_filters(scanned, qtbot):
    conn, pid = scanned
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters(status="translated"))
    assert model.rowCount() == 1
    model.reload(pid, UnitFilters(search="Привет"))
    assert model.rowCount() == 1
    model.reload(pid, UnitFilters(search="нет_такого"))
    assert model.rowCount() == 0
    model.reload(pid, UnitFilters(file_rel="mod_l_english.yml"))
    assert model.rowCount() == 2


def test_model_newline_display(scanned, qtbot):
    conn, pid = scanned
    conn.execute("UPDATE units SET en_text = 'a\\nb' WHERE key = 'greet'")
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters(search="a"))
    text = model.data(model.index(0, COL_EN), Qt.DisplayRole)
    assert "⏎" in text


def test_detail_pane_save_flow(scanned, qtbot):
    from pdxloc.gui.detail_pane import DetailPane

    conn, _pid = scanned
    pane = DetailPane(conn)
    qtbot.addWidget(pane)
    uid = conn.execute("SELECT id FROM units WHERE key = 'bye'").fetchone()["id"]
    pane.load_unit(uid)
    pane.ru_edit.setPlainText("Пока")
    pane.save()
    row = conn.execute("SELECT * FROM units WHERE id = ?", (uid,)).fetchone()
    assert row["ru_text"] == "Пока"
    assert row["status"] == "translated"
    # перевод попал в TM
    from pdxloc.core import tm
    assert tm.lookup(conn, "Goodbye")[0].ru_text == "Пока"
