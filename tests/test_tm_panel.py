"""Tests of the translation memory hints pane inside the detail pane."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import tm  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui.detail_pane import DetailPane  # noqa: E402

from test_scanner import make_project  # noqa: E402
from test_tm_import import build_vanilla  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "Hello"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def pane(db, make_tree, qtbot):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    p = DetailPane(db)
    qtbot.addWidget(p)
    unit_id = db.execute("SELECT id FROM units WHERE key = 'a'").fetchone()[0]
    p.load_unit(unit_id)
    return p


def test_hits_carry_identity(pane):
    assert pane.tm_list.count() == 1
    hit = pane.tm_list.item(0).data(Qt.UserRole)
    assert hit.ru_text == "Привет"
    assert hit.editable and hit.id > 0
    assert hit.origin == "Project"


def test_edit_entry_updates_memory(pane, db):
    hit = pane.tm_list.item(0).data(Qt.UserRole)
    tm.update_entry(db, hit.id, "Здравствуйте")
    pane._reload_suggestions()
    assert pane.tm_list.item(0).data(Qt.UserRole).ru_text == "Здравствуйте"
    assert [h.ru_text for h in tm.lookup(db, "Hello")] == ["Здравствуйте"]


def test_delete_entry_removes_suggestion(pane, db):
    hit = pane.tm_list.item(0).data(Qt.UserRole)
    tm.delete_entries(db, [hit.id])
    pane._reload_suggestions()
    assert pane.tm_list.count() == 0
    # the translation of the row itself is untouched
    assert db.execute("SELECT ru_text FROM units WHERE key='a'").fetchone()[0] == "Привет"


def test_pick_suggestion_signal(pane, qtbot):
    with qtbot.waitSignal(pane.tm_list.suggestionPicked) as blocker:
        pane.tm_list._pick(pane.tm_list.item(0))
    assert blocker.args == ["Привет"]


def test_attached_entry_is_not_editable(tmp_path, make_tree, monkeypatch, qtbot):
    tm_path, _ = build_vanilla(tmp_path, make_tree)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tm_path.parent)
    en = make_tree({"mod_l_english.yml": 'l_english:\n m:0 "Hello"\n'}, "en2")
    conn = project.create_project(tmp_path / "p.pdxproj", name="P",
                                  src_root=en, tgt_root=tmp_path / "ru2")
    project.set_tm_sources(conn, [tm_path.name])
    project.attach_tm_sources(conn, project.project_tm_paths(conn))
    scan_project(conn, 1)

    pane = DetailPane(conn)
    qtbot.addWidget(pane)
    unit_id = conn.execute("SELECT id FROM units WHERE key='m'").fetchone()[0]
    pane.load_unit(unit_id)
    hit = pane.tm_list.item(0).data(Qt.UserRole)
    assert hit.ru_text == "Привет" and hit.origin == "Ваниль CK3"
    assert not hit.editable and hit.id < 0
    # editing and deleting are unavailable and break nothing
    pane.tm_list._delete(hit)
    pane.tm_list._edit(hit)
    assert tm.lookup(conn, "Hello")[0].ru_text == "Привет"
    conn.close()
