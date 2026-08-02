"""GUI-тесты v2 (offscreen): in-cell правка, quick-колонки, дерево, чипы."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from ck3loc.core.scanner import scan_project  # noqa: E402
from ck3loc.core.stats import ProjectStats, file_stats  # noqa: E402
from ck3loc.core.statuses import Status  # noqa: E402
from ck3loc.gui.units_model import (  # noqa: E402
    COL_RU, QUICK_COLS, UnitFilters, UnitsTableModel,
)

from test_scanner import EN, RU, make_project  # noqa: E402


@pytest.fixture
def scanned(db, make_tree):
    en = make_tree({
        "mod_l_english.yml": EN,
        "sub/extra_l_english.yml": 'l_english:\n deep_key:0 "Deep text"\n',
    }, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    return db, pid


def loaded_model(conn, pid, **kw):
    model = UnitsTableModel(conn)
    model.reload(pid, UnitFilters(**kw))
    return model


def test_edit_role_returns_raw_text(scanned, qtbot):
    conn, pid = scanned
    conn.execute("UPDATE units SET ru_text = ? WHERE key = 'greet'", ("д" * 500,))
    conn.commit()
    model = loaded_model(conn, pid, search="greet")
    idx = model.index(0, COL_RU)
    display = model.data(idx, Qt.DisplayRole)
    edit = model.data(idx, Qt.EditRole)
    assert len(edit) == 500          # сырой полный
    assert len(display) < 200        # обрезанный


def test_flags_editable_only_ru(scanned, qtbot):
    conn, pid = scanned
    model = loaded_model(conn, pid, search="greet")
    assert model.flags(model.index(0, COL_RU)) & Qt.ItemIsEditable
    assert not (model.flags(model.index(0, 0)) & Qt.ItemIsEditable)


def test_setdata_saves_and_transitions(scanned, qtbot):
    conn, pid = scanned
    model = loaded_model(conn, pid, search="bye")
    saved = []
    model.unitSaved.connect(saved.append)
    assert model.setData(model.index(0, COL_RU), "Пока", Qt.EditRole)
    row = conn.execute("SELECT * FROM units WHERE key = 'bye'").fetchone()
    assert row["ru_text"] == "Пока"
    assert row["status"] == Status.TRANSLATED.value
    assert saved == [row["id"]]
    # одинаковый текст -> False, повторного сохранения нет
    assert not model.setData(model.index(0, COL_RU), "Пока", Qt.EditRole)


def test_quick_cols_glyphs_and_applicability(scanned, qtbot):
    conn, pid = scanned
    model = loaded_model(conn, pid, search="greet")   # переведённая строка
    r = model.row_data(0)
    # ✓ применим (translated -> reviewed), ✗ нет (не reviewed)
    assert model._quick_applicable(r, Status.REVIEWED)
    assert not model._quick_applicable(r, Status.TRANSLATED)
    model2 = loaded_model(conn, pid, search="bye")    # непереведённая
    r2 = model2.row_data(0)
    assert not model2._quick_applicable(r2, Status.REVIEWED)   # нет RU
    assert model2._quick_applicable(r2, Status.IGNORED)
    for col, (glyph, _, _, _) in QUICK_COLS.items():
        assert model.data(model.index(0, col), Qt.DisplayRole) == glyph


def test_file_prefix_filter(scanned, qtbot):
    conn, pid = scanned
    model = loaded_model(conn, pid, file_prefix="sub")
    assert model.rowCount() == 1
    assert model.row_data(0)["key"] == "deep_key"


def test_file_tree_populate_and_signal(scanned, qtbot):
    from ck3loc.gui.file_tree import FileTreePanel

    conn, pid = scanned
    panel = FileTreePanel()
    qtbot.addWidget(panel)
    panel.populate(file_stats(conn, pid))
    assert "mod_l_english.yml" in panel._file_items
    assert "sub" in panel._dir_items
    got = []
    panel.filterSelected.connect(lambda f, p: got.append((f, p)))
    panel._file_items["mod_l_english.yml"].setSelected(True)
    assert got == [("mod_l_english.yml", None)]
    got.clear()
    panel.tree.clearSelection()
    panel._dir_items["sub"].setSelected(True)
    assert got == [(None, "sub")]


def test_status_chips(qtbot):
    from ck3loc.gui.status_chips import StatusChipsBar

    bar = StatusChipsBar()
    qtbot.addWidget(bar)
    stats = ProjectStats(total=10, done=4,
                         counts={"translated": 4, "untranslated": 6, "ignored": 2})
    bar.set_stats(stats)
    assert bar._chips["translated"].text() == "4"
    assert bar._chips["ignored"].text() == "2"
    clicks = []
    bar.chipClicked.connect(clicks.append)
    bar._on_chip("translated")
    bar._on_chip("translated")    # повторный клик = сброс
    assert clicks == ["translated", ""]
