"""Тест миграции схемы v1 -> v2."""
from __future__ import annotations

import sqlite3

from pdxloc.db import SCHEMA_VERSION, get_connection

# DDL версии 1 — литералом, чтобы тест не зависел от текущего db.py
V1_DDL = """
CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    en_root TEXT NOT NULL, ru_root TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), last_opened_at TEXT
);
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rel_path TEXT NOT NULL, is_orphan_ru INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0, UNIQUE(project_id, rel_path)
);
CREATE TABLE units (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    key TEXT NOT NULL, en_version TEXT NOT NULL DEFAULT '',
    en_text TEXT, en_hash TEXT, prev_en_text TEXT, ru_text TEXT,
    status TEXT NOT NULL DEFAULT 'untranslated'
        CHECK (status IN ('untranslated','auto','translated','reviewed','stale','orphaned')),
    line_no INTEGER, comment_before TEXT NOT NULL DEFAULT '',
    comment_inline TEXT NOT NULL DEFAULT '', is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT,
    UNIQUE(file_id, key)
);
CREATE INDEX idx_units_file ON units(file_id);
CREATE INDEX idx_units_status ON units(status) WHERE is_deleted = 0;
CREATE INDEX idx_units_hash ON units(en_hash);
CREATE TABLE tm_entries (
    id INTEGER PRIMARY KEY, en_hash TEXT NOT NULL, en_text TEXT NOT NULL,
    ru_text TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'user',
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL, key TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(en_hash, ru_text, source)
);
CREATE INDEX idx_tm_hash ON tm_entries(en_hash);
CREATE TABLE scan_history (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL, finished_at TEXT, stats_json TEXT
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO schema_meta VALUES ('schema_version', '1');
"""

V1_STATUSES = ("untranslated", "auto", "translated", "reviewed", "stale", "orphaned")


def make_v1_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(V1_DDL)
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'p', 'e', 'r')")
    conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'a_l_english.yml')")
    for i, st in enumerate(V1_STATUSES):
        if st == "orphaned":
            # у осиротевших нет исходного текста, но есть перевод — он должен уцелеть
            conn.execute(
                "INSERT INTO units (file_id, key, en_text, en_hash, ru_text, status) "
                "VALUES (1, ?, NULL, NULL, 'сирота', 'orphaned')", (f"key{i}",))
            continue
        conn.execute(
            "INSERT INTO units (file_id, key, en_text, en_hash, ru_text, status) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (f"key{i}", f"text{i}", f"hash{i}",
             f"перевод{i}" if st in ("translated", "reviewed", "stale") else None, st),
        )
    conn.execute("INSERT INTO tm_entries (en_hash, en_text, ru_text) VALUES ('h', 'e', 'r')")
    conn.commit()
    conn.close()


def test_migration_v1_to_current(tmp_path):
    """Цепочка v1 -> v2 -> v3 за одно открытие базы."""
    db_path = tmp_path / "old.sqlite3"
    make_v1_db(db_path)

    conn = get_connection(db_path)
    assert conn.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == str(SCHEMA_VERSION)
    # осиротевшая строка ушла в архив, остальные данные на месте
    assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == len(V1_STATUSES) - 1
    assert conn.execute("SELECT ru_text FROM units WHERE key='key2'").fetchone()[0] == "перевод2"
    assert conn.execute(
        "SELECT COUNT(*) FROM units WHERE status='orphaned'").fetchone()[0] == 0
    archived = conn.execute("SELECT * FROM legacy_translations").fetchone()
    assert archived["key"] == "key5" and archived["ru_text"] == "сирота"
    # новые статусы пишутся, старый — нет
    conn.execute("UPDATE units SET status='ignored' WHERE key='key0'")
    conn.execute("UPDATE units SET status='custom' WHERE key='key2'")
    conn.commit()
    import pytest as _pytest
    with _pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE units SET status='orphaned' WHERE key='key1'")
    with _pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO units (file_id, key) VALUES (1, 'key1')")
    # схема v3: языки проекта, project_meta, files.trailing, tm без project_id
    proj_cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
    assert {"src_lang", "tgt_lang"} <= proj_cols
    assert conn.execute("SELECT src_lang FROM projects").fetchone()[0] == "english"
    assert {r[1] for r in conn.execute("PRAGMA table_info(files)")} >= {"trailing"}
    assert "is_orphan_ru" not in {r[1] for r in conn.execute("PRAGMA table_info(files)")}
    assert "project_id" not in {r[1] for r in conn.execute("PRAGMA table_info(tm_entries)")}
    assert conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0] == 1
    conn.execute("SELECT COUNT(*) FROM project_meta")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    # бэкапы обеих ступеней
    assert (tmp_path / "old.sqlite3.v1.bak").exists()
    assert (tmp_path / "old.sqlite3.v2.bak").exists()
    conn.close()

    # повторное открытие — no-op
    conn2 = get_connection(db_path)
    assert conn2.execute("SELECT COUNT(*) FROM units").fetchone()[0] == len(V1_STATUSES) - 1
    assert conn2.execute("SELECT status FROM units WHERE key='key0'").fetchone()[0] == "ignored"
    assert conn2.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0] == 1
    conn2.close()


def test_fresh_db_is_current(tmp_path):
    conn = get_connection(tmp_path / "new.sqlite3")
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'p', 'e', 'r')")
    conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f')")
    conn.execute("INSERT INTO units (file_id, key, en_text, status) VALUES (1, 'k', 'e', 'ignored')")
    conn.execute("INSERT INTO legacy_translations (rel_path, key, ru_text) VALUES ('f','old','т')")
    conn.commit()
    assert conn.execute("SELECT tgt_lang FROM projects").fetchone()[0] == "russian"
    conn.close()


def test_migration_v7_to_8_adds_the_issue_cache(tmp_path):
    """v7 -> v8: две колонки под замечания, строки не пересобираются.

    Пустые значения и означают «ещё не проверено»: набор правил живёт в
    настройке приложения и в файле проекта, а миграция идёт до того, как их
    прочитали, — заполнить кеш здесь просто нечем.
    """
    db_path = tmp_path / "v7.sqlite3"
    conn = get_connection(db_path)
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f')")
    conn.execute("INSERT INTO units (file_id, key, en_text, ru_text, status) "
                 "VALUES (1, 'k', 'Cost: $V$', 'Цена: $V$', 'translated')")
    conn.execute("UPDATE units SET qa_hash = 'x', qa_codes = 'dollar_mismatch'")
    # откатываем схему к v7: колонок кеша ещё нет
    conn.execute("ALTER TABLE units DROP COLUMN qa_hash")
    conn.execute("ALTER TABLE units DROP COLUMN qa_codes")
    conn.execute("UPDATE schema_meta SET value = '7' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    again = get_connection(db_path)
    try:
        cols = {r[1] for r in again.execute("PRAGMA table_info(units)")}
        assert {"qa_hash", "qa_codes"} <= cols
        assert again.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == str(SCHEMA_VERSION)
        row = again.execute("SELECT ru_text, qa_hash, qa_codes FROM units").fetchone()
        assert row[0] == "Цена: $V$"        # перевод на месте
        assert row[1] is None and row[2] is None
        # копия файла для этой ступени не нужна: таблица не пересобиралась
        assert not (tmp_path / "v7.sqlite3.v7.bak").exists()
    finally:
        again.close()


def test_migration_v8_to_9_adds_the_glossary(tmp_path):
    """v8 -> v9: таблица глоссария, данные не трогаются.

    Ступень интересна тем, что миграции почти нечего делать: `init_schema`
    прогоняет DDL до неё, а таблица заведена через `CREATE TABLE IF NOT
    EXISTS` — к моменту вызова она уже есть и в старом файле. Проверяем именно
    это: откатив версию и уронив таблицу, получаем её обратно вместе с v9.
    """
    db_path = tmp_path / "v8.sqlite3"
    conn = get_connection(db_path)
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f')")
    conn.execute("INSERT INTO units (file_id, key, en_text, ru_text, status) "
                 "VALUES (1, 'k', 'A Maester of the Citadel', 'Мейстер Цитадели', 'translated')")
    # откатываем схему к v8: глоссария ещё нет
    conn.execute("DROP TABLE glossary")
    conn.execute("UPDATE schema_meta SET value = '8' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    again = get_connection(db_path)
    try:
        assert again.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == str(SCHEMA_VERSION)
        # таблица вернулась и пуста — глоссарий начинается с нуля
        assert again.execute("SELECT COUNT(*) FROM glossary").fetchone()[0] == 0
        # перевод на месте: ступень не пересобирает ни одной существующей таблицы
        assert again.execute("SELECT ru_text FROM units").fetchone()[0] == "Мейстер Цитадели"
        assert not (tmp_path / "v8.sqlite3.v8.bak").exists()
    finally:
        again.close()


def test_migration_v9_to_10_remembers_what_went_stale(tmp_path):
    """v9 -> v10: история помнит прежний оригинал и вид правки.

    Две колонки, `unit_history` не пересобирается. У прежних записей значения
    остаются пустыми — их в тот момент никто не сохранял, и восстановить задним
    числом неоткуда.
    """
    db_path = tmp_path / "v9.sqlite3"
    conn = get_connection(db_path)
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f')")
    conn.execute("INSERT INTO units (id, file_id, key, en_text, ru_text, status) "
                 "VALUES (1, 1, 'k', 'New', 'Новый', 'stale')")
    conn.execute("INSERT INTO unit_history (unit_id, ru_text, status) "
                 "VALUES (1, 'Старый', 'translated')")
    # откатываем схему к v9: колонок ещё нет
    conn.execute("ALTER TABLE unit_history DROP COLUMN prev_en_text")
    conn.execute("ALTER TABLE unit_history DROP COLUMN change_kind")
    conn.execute("UPDATE schema_meta SET value = '9' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    again = get_connection(db_path)
    try:
        cols = {r[1] for r in again.execute("PRAGMA table_info(unit_history)")}
        assert {"prev_en_text", "change_kind"} <= cols
        assert again.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == str(SCHEMA_VERSION)

        row = again.execute(
            "SELECT ru_text, prev_en_text, change_kind FROM unit_history").fetchone()
        assert row[0] == "Старый"           # прежняя запись цела
        assert row[1] is None and row[2] is None
        assert not (tmp_path / "v9.sqlite3.v9.bak").exists()
    finally:
        again.close()
