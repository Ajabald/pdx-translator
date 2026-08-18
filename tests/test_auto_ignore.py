"""Тесты автопометки строк, где переводить нечего.

Набор «переводить нечего» задаётся реестром разметки, а он пополняется: добавили
токен — и сотни строк живого проекта меняют статус при следующем открытии.
Поэтому уборка обязана быть откатываемой и происходить один раз на проект;
за этим тут следят отдельно от того, кого именно она помечает.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pdxloc.core import unit_ops                        # noqa: E402
from pdxloc.core.scanner import scan_project            # noqa: E402
from pdxloc.core.statuses import Status                 # noqa: E402

from test_scanner import get_unit, make_project         # noqa: E402

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
        ("tag3", "@warning_icon! [GetName]", None, "untranslated"),
        ("text", "Real text", None, "untranslated"),
        ("icon_text", "@gold! Attack", None, "untranslated"),   # текст есть
        ("tag_translated", TAG, "[GetOther]", "translated"),   # человек что-то вписал
        ("tag_custom", TAG, None, "custom"),                   # статус выставлен вручную
    ])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 3
    assert get_unit(db, "tag1")["status"] == Status.IGNORED.value
    assert get_unit(db, "tag2")["status"] == Status.IGNORED.value
    assert get_unit(db, "tag3")["status"] == Status.IGNORED.value
    assert get_unit(db, "icon_text")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "text")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "tag_translated")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "tag_custom")["status"] == Status.CUSTOM.value


def test_marks_empty_source(db):
    """Пустое значение в оригинале — переводить нечего ровно как в теге.

    В модах такие ключи заводят заглушками под ссылку из скрипта; без правила
    они всплывали бы в непереведённых при каждом переимпорте.
    """
    seed(db, [
        ("empty", "", None, "untranslated"),
        ("spaces", "   ", None, "untranslated"),
        ("text", "Real text", None, "untranslated"),
    ])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 2
    assert get_unit(db, "empty")["status"] == Status.IGNORED.value
    assert get_unit(db, "spaces")["status"] == Status.IGNORED.value
    assert get_unit(db, "text")["status"] == Status.UNTRANSLATED.value


def test_empty_source_with_a_human_translation_is_left_alone(db):
    """Написал человек что-то в пустом ключе — значит смысл был."""
    seed(db, [("empty", "", "Перевод", "translated")])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 0
    assert get_unit(db, "empty")["status"] == Status.TRANSLATED.value


def test_idempotent(db):
    seed(db, [("tag1", TAG, None, "untranslated")])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 1
    assert unit_ops.auto_ignore_untranslated(db, 1) == 0


def test_empty_source_is_idempotent(db):
    seed(db, [("empty", "", None, "untranslated")])
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
    from pdxloc import project

    en = make_tree({"m_l_english.yml": f'l_english:\n tag:0 "{TAG}"\n'}, "en")
    path = tmp_path / "p.pdxproj"
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


# --- пустой ключ мода: игнорируем, но докладываем ---

def unit_in(conn, rel, key):
    """Ключ есть в двух файлах сразу — выбирать приходится по файлу."""
    return conn.execute(
        "SELECT u.* FROM units u JOIN files f ON f.id = u.file_id "
        "WHERE f.rel_path = ? AND u.key = ?", (rel, key)).fetchone()


def test_empty_key_from_the_mod_is_ignored_and_reported(db, make_tree):
    """Случай из «Bloodlines»: заглушка-дубль настоящего ключа в чужом файле.

    `agot_riverlands_bla_broken_knight_arrives_tt:0 ""` лежит в файле про
    раскопки Кастамере, а настоящий текст — в файле Речных земель. Пустая
    половина уходит в игнор молча, но в отчёт скана попадает: пустое значение в
    оригинале — дефект мода, и знать о нём надо.
    """
    en = make_tree({
        "a_l_english.yml": 'l_english:\n k:0 "A scarred, cynical hedge knight."\n',
        "b_l_english.yml": 'l_english:\n k:0 "" # Fixed key reference string container\n',
    }, "en")
    pid = make_project(db, en, make_tree({}, "ru"))

    stats = scan_project(db, pid)
    assert stats.empty_source_keys == ["b_l_english.yml: k"]
    assert stats.duplicate_keys == []          # разные файлы — для CK3 это норма
    assert unit_in(db, "b_l_english.yml", "k")["status"] == Status.IGNORED.value
    assert unit_in(db, "a_l_english.yml", "k")["status"] == Status.UNTRANSLATED.value

    # переимпорт ничего не воскрешает и докладывает то же самое
    stats = scan_project(db, pid)
    assert stats.empty_source_keys == ["b_l_english.yml: k"]
    assert unit_in(db, "b_l_english.yml", "k")["status"] == Status.IGNORED.value


def test_empty_value_in_the_translation_is_not_reported(db, make_tree):
    """Пустое значение в RU — это «ещё не переведено», а не дефект оригинала."""
    en = make_tree({"m_l_english.yml": 'l_english:\n k:0 "Text"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n k:0 ""\n'}, "ru")
    stats = scan_project(db, make_project(db, en, ru))
    assert stats.empty_source_keys == []


# --- уборка как отменяемая операция ---

def test_auto_ignore_is_one_undoable_batch(db):
    seed(db, [
        ("tag1", TAG, None, "untranslated"),
        ("tag2", "$VALUE$ £gold£", None, "untranslated"),
        ("empty", "", None, "untranslated"),
        ("text", "Real text", None, "untranslated"),
    ])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 3

    info = unit_ops.last_batch(db)
    assert info is not None
    batch_id, origin, count = info
    assert (origin, count) == ("auto_ignore", 3)

    assert unit_ops.undo_batch(db, batch_id) == 3
    assert get_unit(db, "tag1")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "tag2")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "empty")["status"] == Status.UNTRANSLATED.value


def test_empty_run_records_no_batch(db):
    """Пачка без строк сделала бы last_batch призрачным, а Ctrl+Z — пустым."""
    seed(db, [("text", "Real text", None, "untranslated")])
    assert unit_ops.auto_ignore_untranslated(db, 1) == 0
    assert unit_ops.last_batch(db) is None


def test_undo_survives_reopening_the_project(tmp_path, make_tree, qtbot, monkeypatch):
    """Отменённая уборка не возвращается при следующем открытии.

    Она гоняется при каждом открытии, и без отметки о прошлом решении Ctrl+Z
    переигрывался бы за спиной у человека. Отмена, которую отменяют, учит не
    доверять отмене вообще.
    """
    from pdxloc import project, settings

    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)

    en = make_tree({"m_l_english.yml": f'l_english:\n tag:0 "{TAG}"\n a:0 "Text"\n'}, "en")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=tmp_path / "ru")
    scan_project(conn, 1)
    conn.execute("UPDATE units SET status = 'untranslated' WHERE key = 'tag'")
    conn.commit()
    conn.close()

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.open_project(path)
    assert win.conn.execute(
        "SELECT status FROM units WHERE key='tag'").fetchone()[0] == Status.IGNORED.value

    info = unit_ops.last_batch(win.conn)
    assert info[1] == "auto_ignore"
    unit_ops.undo_batch(win.conn, info[0])
    win._close_project()

    win.open_project(path)
    assert win.conn.execute(
        "SELECT status FROM units WHERE key='tag'").fetchone()[0] == \
        Status.UNTRANSLATED.value


def test_a_row_without_a_single_letter_has_nothing_to_translate():
    """`_`, `$NAME$: $VAL$`, `£command_power  §Y40§!` — переводить нечего.

    Букв нет — нет и слова; числа с иконками переводу не подлежат. Замер:
    в ванильной CK2 таких 1 422 (1 329 из них — заглушки `_` в `FR.csv`,
    файле французской грамматики, где английской колонки просто не бывает),
    в HOI4 — 854, на живом моде к CK3 — ни одной.
    """
    from pdxloc.core.unit_ops import has_nothing_to_translate

    assert has_nothing_to_translate("_")
    assert has_nothing_to_translate("$NAME$: $VAL|+=0$")
    assert has_nothing_to_translate("£command_power  §Y40§!")
    assert has_nothing_to_translate("—")
    # а слово переводить есть чем, даже рядом с числами и разметкой
    assert not has_nothing_to_translate("§Y40§! ships")
    assert not has_nothing_to_translate("il")
