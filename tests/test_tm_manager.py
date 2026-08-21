"""Tests of managing the translation memory (browsing, editing, deleting)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from pdxloc import project, settings  # noqa: E402
from pdxloc.core import tm  # noqa: E402

from test_tm_import import build_vanilla  # noqa: E402


def seed(db):
    tm.upsert(db, "Hello", "Привет", key="k_hello")
    tm.upsert(db, "World", "Мир", key="k_world")
    tm.upsert(db, "Gold", "ЗОЛОТО", key="k_gold")
    db.commit()


def test_browse_and_search(db):
    seed(db)
    assert len(tm.browse(db)) == 3
    found = tm.browse(db, search="привет")       # the case does not matter
    assert [r.ru_text for r in found] == ["Привет"]
    assert [r.en_text for r in tm.browse(db, search="ЗОЛОТО")] == ["Gold"]
    assert [r.key for r in tm.browse(db, search="k_world")] == ["k_world"]


def test_browse_marks_own_entries_editable(db):
    seed(db)
    assert all(r.editable and r.origin == "Project" for r in tm.browse(db))


def test_update_entry(db):
    seed(db)
    record = tm.browse(db, search="Hello")[0]
    assert tm.update_entry(db, record.id, "Здравствуйте")
    assert [h.ru_text for h in tm.lookup(db, "Hello")] == ["Здравствуйте"]
    # an empty text is not accepted
    assert not tm.update_entry(db, record.id, "   ")


def test_update_to_existing_duplicate_collapses(db):
    """An edit into an already existing variant must not break the uniqueness."""
    tm.upsert(db, "Hello", "Привет")
    tm.upsert(db, "Hello", "Здравствуйте")
    db.commit()
    record = next(r for r in tm.browse(db) if r.ru_text == "Здравствуйте")
    assert tm.update_entry(db, record.id, "Привет")
    assert [h.ru_text for h in tm.lookup(db, "Hello")] == ["Привет"]


def test_delete_entries(db):
    seed(db)
    ids = [r.id for r in tm.browse(db, search="Мир")]
    assert tm.delete_entries(db, ids) == 1
    assert tm.lookup(db, "World") == []
    assert len(tm.browse(db)) == 2
    assert tm.delete_entries(db, []) == 0


def test_clear_own(db):
    seed(db)
    assert tm.clear_own(db) == 3
    assert tm.browse(db) == []


def test_counts(db):
    seed(db)
    assert tm.counts(db) == (3, 3)


def test_attached_entries_are_read_only(tmp_path, make_tree, monkeypatch):
    tm_path, _ = build_vanilla(tmp_path, make_tree)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tm_path.parent)
    conn = project.create_project(tmp_path / "p.pdxproj", name="P",
                                  src_root="e", tgt_root="r")
    project.set_tm_sources(conn, [tm_path.name])
    project.attach_tm_sources(conn, project.project_tm_paths(conn))
    tm.upsert(conn, "Own", "Своё")
    conn.commit()

    records = tm.browse(conn)
    own = [r for r in records if r.editable]
    attached = [r for r in records if not r.editable]
    assert [r.ru_text for r in own] == ["Своё"]
    assert attached and all(r.origin == "Ваниль CK3" for r in attached)

    own_count, total = tm.counts(conn)
    assert own_count == 1 and total == 3
    # the «only mine» filter
    assert len(tm.browse(conn, only_editable=True)) == 1
    # deleting does not touch the attached database
    assert tm.delete_entries(conn, [r.id for r in attached]) == 0
    assert len(tm.browse(conn)) == 3
    conn.close()


def test_dialog_edit_and_delete(db, qtbot):
    from pdxloc.gui.tm_entries_tab import COL_RU, TmEntriesTab
    from PySide6.QtCore import Qt

    seed(db)
    tab = TmEntriesTab(db)
    qtbot.addWidget(tab)
    assert tab.model.rowCount() == 3

    # an edit through the table
    row = next(i for i in range(3) if tab.model.record(i).en_text == "Hello")
    assert tab.model.setData(tab.model.index(row, COL_RU), "Здравствуйте", Qt.EditRole)
    assert [h.ru_text for h in tm.lookup(db, "Hello")] == ["Здравствуйте"]

    # the search
    tab.search.setText("Мир")
    tab.reload()
    assert tab.model.rowCount() == 1
    assert "shown: 1" in tab.status_text()
