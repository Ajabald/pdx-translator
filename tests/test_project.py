"""Тесты файлов проектов и переноса базы прежних версий."""
from __future__ import annotations

import sqlite3

import pytest

from ck3loc import project, settings
from ck3loc.core.scanner import scan_project

from test_migration import V1_DDL


def test_create_and_open(tmp_path):
    path = tmp_path / "мой проект.ck3proj"
    conn = project.create_project(
        path, name="Тест", src_root=tmp_path / "en", tgt_root=tmp_path / "ru")
    assert project.project_name(conn) == "Тест"
    assert conn.execute("SELECT src_lang, tgt_lang FROM projects").fetchone()[0] == "english"
    assert conn.execute(
        "SELECT value FROM schema_meta WHERE key='format'").fetchone()[0] == "ck3proj"
    conn.close()
    assert path.is_file()

    reopened = project.open_project(path)
    assert project.project_name(reopened) == "Тест"
    reopened.close()


def test_create_refuses_existing(tmp_path):
    path = tmp_path / "p.ck3proj"
    project.create_project(path, name="A", src_root="e", tgt_root="r").close()
    with pytest.raises(FileExistsError):
        project.create_project(path, name="B", src_root="e", tgt_root="r")


def test_export_root_survives_reopen(tmp_path):
    """Папка вывода — часть проекта, а не настройка приложения."""
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="A", src_root="e", tgt_root="r")
    assert project.get_export_root(conn) is None
    assert project.get_last_export_at(conn) is None
    project.set_export_root(conn, tmp_path / "мод" / "localization")
    project.set_last_export_at(conn, "2026-08-02 01:47")
    conn.close()

    reopened = project.open_project(path)
    assert project.get_export_root(reopened) == str(tmp_path / "мод" / "localization")
    assert project.get_last_export_at(reopened) == "2026-08-02 01:47"
    project.set_export_root(reopened, tmp_path / "другая")
    assert project.get_export_root(reopened) == str(tmp_path / "другая")
    reopened.close()


def test_path_with_spaces_and_hash(tmp_path):
    path = tmp_path / "проект #1 (копия).ck3proj"
    conn = project.create_project(path, name="X", src_root="e", tgt_root="r")
    conn.execute("SELECT 1")
    conn.close()
    assert path.is_file()


def test_save_as(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    path = tmp_path / "a.ck3proj"
    conn = project.create_project(path, name="A", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    copy_path = tmp_path / "sub" / "b.ck3proj"
    project.save_project_as(conn, copy_path)
    conn.close()

    copy = project.open_project(copy_path)
    assert copy.execute("SELECT ru_text FROM units WHERE key='a'").fetchone()[0] == "Привет"
    copy.close()


def make_legacy(path, projects=(("BLA", 3, 2),)):
    """База прежней версии: (имя, всего строк, из них переведённых)."""
    conn = sqlite3.connect(path)
    conn.executescript(V1_DDL)
    for pid, (name, total, done) in enumerate(projects, start=1):
        conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (?,?,?,?)",
                     (pid, name, f"en{pid}", f"ru{pid}"))
        conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (?,?,?)",
                     (pid, pid, f"f{pid}_l_english.yml"))
        for i in range(total):
            translated = i < done
            conn.execute(
                "INSERT INTO units (file_id, key, en_text, en_hash, ru_text, status) "
                "VALUES (?,?,?,?,?,?)",
                (pid, f"k{i}", f"text{i}", f"h{pid}{i}",
                 f"перевод{i}" if translated else None,
                 "translated" if translated else "untranslated"))
        # осиротевшая строка — уедет в архив, в счёт строк не идёт
        conn.execute(
            "INSERT INTO units (file_id, key, en_text, en_hash, ru_text, status) "
            "VALUES (?,?,NULL,NULL,?, 'orphaned')", (pid, "gone", "старый перевод"))
    conn.commit()
    conn.close()


def test_convert_legacy_single(tmp_path):
    legacy = tmp_path / "ck3loc.sqlite3"
    make_legacy(legacy)
    created = project.convert_legacy_db(legacy, tmp_path / "Projects")
    assert len(created) == 1
    assert created[0].name == "BLA.ck3proj"
    assert not legacy.exists()                       # переименован
    assert (tmp_path / "ck3loc.sqlite3.migrated").exists()

    conn = project.open_project(created[0])
    assert project.project_name(conn) == "BLA"
    assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM units WHERE status='translated'").fetchone()[0] == 2
    assert conn.execute(
        "SELECT ru_text FROM legacy_translations").fetchone()[0] == "старый перевод"
    assert conn.execute("SELECT id FROM projects").fetchone()[0] == 1
    conn.close()


def test_convert_legacy_multiple(tmp_path):
    legacy = tmp_path / "ck3loc.sqlite3"
    make_legacy(legacy, (("Первый", 3, 1), ("Второй", 5, 4)))
    created = project.convert_legacy_db(legacy, tmp_path / "Projects")
    assert {p.stem for p in created} == {"Первый", "Второй"}
    for path, expected_units in ((created[0], 3), (created[1], 5)):
        conn = project.open_project(path)
        assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == expected_units
        assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
        conn.close()


def test_convert_legacy_bad_name(tmp_path):
    legacy = tmp_path / "ck3loc.sqlite3"
    make_legacy(legacy, (("Mod: AGOT/BLA?", 2, 1),))
    created = project.convert_legacy_db(legacy, tmp_path / "Projects")
    assert created[0].name == "Mod_ AGOT_BLA_.ck3proj"
    conn = project.open_project(created[0])
    assert project.project_name(conn) == "Mod: AGOT/BLA?"     # имя внутри не искажено
    conn.close()
