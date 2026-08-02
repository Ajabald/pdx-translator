"""Тесты дифф-автомата сканера: по одному на каждый переход."""
from __future__ import annotations

import pytest

from ck3loc.core.scanner import en_to_ru_relpath, ru_to_en_relpath, scan_project
from ck3loc.core.statuses import Status


def make_project(conn, en_root, ru_root, name="test") -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, en_root, ru_root) VALUES (?, ?, ?)",
        (name, str(en_root), str(ru_root)),
    )
    conn.commit()
    return cur.lastrowid


def get_unit(conn, key):
    return conn.execute("SELECT * FROM units WHERE key = ?", (key,)).fetchone()


EN = 'l_english:\n greet:0 "Hello"\n bye:0 "Goodbye"\n'
RU = 'l_russian:\n greet:0 "Привет"\n bye:0 "Goodbye" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'


def test_path_mapping_middle_suffix():
    assert en_to_ru_relpath("modifiers/agot_modifiers_l_english_BLA.yml") == \
        "modifiers/agot_modifiers_l_russian_BLA.yml"
    assert ru_to_en_relpath("a_l_russian.yml") == "a_l_english.yml"


def test_initial_import(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.new == 2
    assert get_unit(db, "greet")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "greet")["ru_text"] == "Привет"
    # маркер старых скриптов + ru==en -> не переведено
    assert get_unit(db, "bye")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "bye")["ru_text"] is None


def test_rescan_unchanged(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    stats = scan_project(db, pid)
    assert stats.new == 0 and stats.unchanged == 2 and stats.stale == 0


def test_en_modified_translated_becomes_stale(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello there"\n bye:0 "Goodbye"\n'}, "en")
    stats = scan_project(db, pid)
    u = get_unit(db, "greet")
    assert u["status"] == Status.STALE.value
    assert u["prev_en_text"] == "Hello"
    assert u["en_text"] == "Hello there"
    assert u["ru_text"] == "Привет"          # перевод сохранён
    assert stats.stale == 1


def test_en_modified_again_keeps_prev(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello v2"\n bye:0 "Goodbye"\n'}, "en")
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello v3"\n bye:0 "Goodbye"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "greet")
    assert u["status"] == Status.STALE.value
    assert u["prev_en_text"] == "Hello"      # НЕ перезаписан на v2
    assert u["en_text"] == "Hello v3"


def test_en_modified_untranslated_stays(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n greet:0 "Hello"\n bye:0 "Farewell"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "bye")
    assert u["status"] == Status.UNTRANSLATED.value
    assert u["en_text"] == "Farewell"
    assert u["prev_en_text"] is None


def test_key_deleted_and_restored(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n bye:0 "Goodbye"\n'}, "en")
    stats = scan_project(db, pid)
    assert stats.deleted == 1
    assert get_unit(db, "greet")["is_deleted"] == 1
    make_tree({"mod_l_english.yml": EN}, "en")
    stats = scan_project(db, pid)
    assert stats.restored == 1
    u = get_unit(db, "greet")
    assert u["is_deleted"] == 0
    assert u["ru_text"] == "Привет"          # перевод пережил удаление


def test_key_without_source_goes_to_archive(db, make_tree):
    """Ключ есть в переводе, но не в оригинале: перевод в архив, строки нет."""
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree(
        {"mod_l_russian.yml": RU.rstrip() + '\n old_key:0 "Старьё"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.archived == 1
    assert get_unit(db, "old_key") is None
    row = db.execute(
        "SELECT * FROM legacy_translations WHERE key = 'old_key'").fetchone()
    assert row["ru_text"] == "Старьё"


def test_translation_file_without_source_archived(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({
        "mod_l_russian.yml": RU,
        "extra_l_russian.yml": 'l_russian:\n lonely:0 "Одинокий"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.archived == 1
    assert stats.orphan_ru_files == ["extra_l_russian.yml"]
    assert db.execute(
        "SELECT ru_text FROM legacy_translations WHERE key='lonely'").fetchone()[0] == "Одинокий"
    # файла без пары в проекте не заводим
    assert db.execute(
        "SELECT COUNT(*) FROM files WHERE rel_path = 'extra_l_russian.yml'").fetchone()[0] == 0


def test_deleted_key_translation_archived(db, make_tree):
    """Ключ пропал из оригинала при обновлении мода — перевод сохраняется."""
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"mod_l_english.yml": 'l_english:\n bye:0 "Goodbye"\n'}, "en")
    make_tree({"mod_l_russian.yml": 'l_russian:\n bye:0 "Пока"\n'}, "ru")
    stats = scan_project(db, pid)
    assert stats.deleted == 1
    assert db.execute(
        "SELECT ru_text FROM legacy_translations WHERE key='greet'").fetchone()[0] == "Привет"


def test_updated_junk_files_ignored(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({
        "mod_l_russian.yml": RU,
        "mod_l_russian_updated.yml": 'l_russian:\n greet:0 "Мусор"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.archived == 0
    assert get_unit(db, "greet")["ru_text"] == "Привет"


def test_tm_auto_fill_same_text(db, make_tree):
    # два ключа с одинаковым EN: один переведён -> второй заполняется из TM как auto
    en = make_tree({"mod_l_english.yml":
                    'l_english:\n a:0 "Same text"\n b:0 "Same text"\n'}, "en")
    ru = make_tree({"mod_l_russian.yml": 'l_russian:\n a:0 "Одинаковый"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.auto_filled == 1
    u = get_unit(db, "b")
    assert u["status"] == Status.AUTO.value
    assert u["ru_text"] == "Одинаковый"


def test_tm_no_fill_on_ambiguous(db, make_tree):
    # два разных перевода одного EN в TM -> auto-заполнения нет
    en = make_tree({
        "m1_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Same"\n c:0 "Same"\n',
    }, "en")
    ru = make_tree({
        "m1_l_russian.yml": 'l_russian:\n a:0 "Вариант1"\n b:0 "Вариант2"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.auto_filled == 0
    assert get_unit(db, "c")["status"] == Status.UNTRANSLATED.value


def test_en_modified_auto_reset(db, make_tree):
    en = make_tree({"mod_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Same"\n'}, "en")
    ru = make_tree({"mod_l_russian.yml": 'l_russian:\n a:0 "Один"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.AUTO.value
    # EN ключа b изменился -> auto сброшен, нового совпадения в TM нет
    make_tree({"mod_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Different now"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "b")
    assert u["status"] == Status.UNTRANSLATED.value
    assert u["ru_text"] is None


def test_ru_conflict_db_wins(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    # на диске перевод поменяли, в БД уже есть свой -> БД главнее
    make_tree({"mod_l_russian.yml": 'l_russian:\n greet:0 "Другой перевод"\n'}, "ru")
    stats = scan_project(db, pid)
    assert stats.ru_conflicts == 1
    assert get_unit(db, "greet")["ru_text"] == "Привет"


def test_duplicate_key_last_wins(db, make_tree):
    en = make_tree({"mod_l_english.yml":
                    'l_english:\n dup:0 "First"\n dup:0 "Second"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert len(stats.duplicate_keys) == 1
    assert get_unit(db, "dup")["en_text"] == "Second"


def test_untranslated_ru_appears_on_disk(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    # пользователь перевёл bye прямо в файле
    make_tree({"mod_l_russian.yml":
               'l_russian:\n greet:0 "Привет"\n bye:0 "Пока"\n'}, "ru")
    scan_project(db, pid)
    u = get_unit(db, "bye")
    assert u["status"] == Status.TRANSLATED.value
    assert u["ru_text"] == "Пока"
