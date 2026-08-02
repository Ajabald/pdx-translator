"""Тесты автопометки строк, где переводить нечего."""
from __future__ import annotations

from ck3loc.core import unit_ops
from ck3loc.core.scanner import scan_project
from ck3loc.core.statuses import Status

from test_scanner import get_unit, make_project

TAG = "[GetPlayer.GetDynasty.GetNameNoTooltip]"


def seed(db, rows):
    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1,1,'f_l_english.yml')")
    for key, en, ru, status in rows:
        db.execute(
            "INSERT INTO units (file_id, key, en_text, ru_text, status) VALUES (1,?,?,?,?)",
            (key, en, ru, status))
    db.commit()


def test_marks_only_untranslated_markup(db):
    seed(db, [
        ("tag1", TAG, None, "untranslated"),
        ("tag2", "$VALUE$ £gold£", None, "untranslated"),
        ("text", "Real text", None, "untranslated"),
        ("tag_translated", TAG, "[GetOther]", "translated"),   # человек что-то вписал
        ("tag_custom", TAG, None, "custom"),                   # статус выставлен вручную
    ])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 2
    assert get_unit(db, "tag1")["status"] == Status.IGNORED.value
    assert get_unit(db, "tag2")["status"] == Status.IGNORED.value
    assert get_unit(db, "text")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "tag_translated")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "tag_custom")["status"] == Status.CUSTOM.value


def test_idempotent(db):
    seed(db, [("tag1", TAG, None, "untranslated")])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 1
    assert unit_ops.auto_ignore_untranslated(db, 1) == 0


def test_deleted_units_untouched(db):
    seed(db, [("tag1", TAG, None, "untranslated")])
    db.execute("UPDATE units SET is_deleted = 1")
    db.commit()
    assert unit_ops.auto_ignore_untranslated(db, 1) == 0


def test_scan_reports_migrated_rows(db, make_tree):
    """Проект из прежней версии: строки-теги уходят в «игнорировано» при скане."""
    en = make_tree({"m_l_english.yml": f'l_english:\n tag:0 "{TAG}"\n a:0 "Text"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    # искусственно возвращаем старое состояние
    db.execute("UPDATE units SET status = 'untranslated' WHERE key = 'tag'")
    db.commit()
    stats = scan_project(db, pid)
    assert stats.auto_ignored == 1
    assert get_unit(db, "tag")["status"] == Status.IGNORED.value


def test_open_project_applies_rule(tmp_path, make_tree, qtbot):
    """Открытие проекта само приводит статусы в порядок (без сканирования)."""
    from ck3loc import project

    en = make_tree({"m_l_english.yml": f'l_english:\n tag:0 "{TAG}"\n'}, "en")
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=tmp_path / "ru")
    scan_project(conn, 1)
    conn.execute("UPDATE units SET status = 'untranslated' WHERE key = 'tag'")
    conn.commit()
    conn.close()

    conn = project.open_project(path)
    assert unit_ops.auto_ignore_untranslated(conn, 1) == 1
    assert conn.execute(
        "SELECT status FROM units WHERE key='tag'").fetchone()[0] == Status.IGNORED.value
    conn.close()
