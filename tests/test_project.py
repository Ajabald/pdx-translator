"""Тесты файлов проектов: создание, открытие, сохранение копии."""
from __future__ import annotations

import pytest

from pdxloc import project
from pdxloc.core.scanner import scan_project


def test_create_and_open(tmp_path):
    path = tmp_path / "мой проект.pdxproj"
    conn = project.create_project(
        path, name="Тест", src_root=tmp_path / "en", tgt_root=tmp_path / "ru")
    assert project.project_name(conn) == "Тест"
    assert conn.execute("SELECT src_lang, tgt_lang FROM projects").fetchone()[0] == "english"
    assert conn.execute(
        "SELECT value FROM schema_meta WHERE key='format'").fetchone()[0] == "pdxproj"
    conn.close()
    assert path.is_file()

    reopened = project.open_project(path)
    assert project.project_name(reopened) == "Тест"
    reopened.close()


def test_create_refuses_existing(tmp_path):
    path = tmp_path / "p.pdxproj"
    project.create_project(path, name="A", src_root="e", tgt_root="r").close()
    with pytest.raises(FileExistsError):
        project.create_project(path, name="B", src_root="e", tgt_root="r")


def test_export_root_survives_reopen(tmp_path):
    """Папка вывода — часть проекта, а не настройка приложения."""
    path = tmp_path / "p.pdxproj"
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
    path = tmp_path / "проект #1 (копия).pdxproj"
    conn = project.create_project(path, name="X", src_root="e", tgt_root="r")
    conn.execute("SELECT 1")
    conn.close()
    assert path.is_file()


def test_save_as(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    path = tmp_path / "a.pdxproj"
    conn = project.create_project(path, name="A", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    copy_path = tmp_path / "sub" / "b.pdxproj"
    project.save_project_as(conn, copy_path)
    conn.close()

    copy = project.open_project(copy_path)
    assert copy.execute("SELECT ru_text FROM units WHERE key='a'").fetchone()[0] == "Привет"
    copy.close()


def test_checkpoint_empties_the_journal(tmp_path, make_tree):
    """Журнал не должен доживать до следующего открытия.

    Скан пишет проект одной транзакцией, и рядом с файлом остаётся `-wal`
    размером со всё записанное: у ванильной HOI4 это 182 МБ при базе в 181 МБ,
    и каждое открытие начиналось с чтения этих мегабайт.
    """
    en = make_tree({"m_l_english.yml": 'l_english:\n k:0 "Hello"\n'}, "en")
    ru = make_tree({}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)

    wal = tmp_path / "p.pdxproj-wal"
    assert not wal.exists() or wal.stat().st_size == 0

    conn.execute("UPDATE units SET ru_text = 'Привет', status = 'translated'")
    conn.commit()
    project.checkpoint(conn)
    assert not wal.exists() or wal.stat().st_size == 0
    conn.close()


def test_the_similarity_index_is_built_on_first_use(tmp_path, make_tree):
    """Индекс похожих строк ждёт первого запроса, а не открытия проекта.

    У ванильной HOI4 своя память проекта — 106 268 записей, и индекс по ней
    стоит 0,2 с; нужен он ровно тогда, когда переводчик встал на строку.
    """
    from pdxloc.core import fuzzy, tm
    from pdxloc.db import OWN_TM_FTS

    en = make_tree({"m_l_english.yml": 'l_english:\n k:0 "Hello"\n'}, "en")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en,
                                  tgt_root=make_tree({}, "ru"))
    tm.upsert(conn, "Hello there", "Привет там", key="k")
    conn.commit()

    def index_exists() -> bool:
        return bool(conn.execute(
            "SELECT 1 FROM temp.sqlite_master WHERE type='table' AND name=?",
            (OWN_TM_FTS,)).fetchone())

    assert not index_exists()
    hits = fuzzy.lookup_similar(conn, "Hello there", limit=5)
    assert index_exists()
    assert any(h.ru_text == "Привет там" for h in hits)
    conn.close()
