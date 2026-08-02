"""Подключение к SQLite и схема БД.

Правило потоков: одно соединение на поток (ScanWorker открывает своё).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 4

ALL_STATUSES = "'untranslated','auto','translated','reviewed','stale','ignored','custom'"
# Списки статусов прошлых версий — нужны миграциям, которые пересобирают
# таблицу units и обязаны принять данные ровно в том виде, в каком они лежали.
_STATUSES_V2 = ALL_STATUSES + ",'orphaned'"

DDL = f"""
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL UNIQUE,
    en_root        TEXT NOT NULL,
    ru_root        TEXT NOT NULL,
    src_lang       TEXT NOT NULL DEFAULT 'english',
    tgt_lang       TEXT NOT NULL DEFAULT 'russian',
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_opened_at TEXT
);

CREATE TABLE IF NOT EXISTS project_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rel_path     TEXT NOT NULL,
    trailing     TEXT NOT NULL DEFAULT '',
    is_deleted   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(project_id, rel_path)
);

CREATE TABLE IF NOT EXISTS units (
    id             INTEGER PRIMARY KEY,
    file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    key            TEXT NOT NULL,
    en_version     TEXT NOT NULL DEFAULT '',
    en_text        TEXT,
    en_hash        TEXT,
    prev_en_text   TEXT,
    ru_text        TEXT,
    status         TEXT NOT NULL DEFAULT 'untranslated'
                   CHECK (status IN ({ALL_STATUSES})),
    line_no        INTEGER,
    comment_before TEXT NOT NULL DEFAULT '',
    comment_inline TEXT NOT NULL DEFAULT '',
    is_deleted     INTEGER NOT NULL DEFAULT 0,
    en_changed_at  TEXT,
    change_kind    TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT,
    UNIQUE(file_id, key)
);
CREATE INDEX IF NOT EXISTS idx_units_file   ON units(file_id);
CREATE INDEX IF NOT EXISTS idx_units_status ON units(status) WHERE is_deleted = 0;
CREATE INDEX IF NOT EXISTS idx_units_hash   ON units(en_hash);

CREATE TABLE IF NOT EXISTS source_history (
    id         INTEGER PRIMARY KEY,
    unit_id    INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    en_text    TEXT NOT NULL,
    en_hash    TEXT NOT NULL,
    en_version TEXT,
    seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    scan_id    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_source_history_unit ON source_history(unit_id, seen_at DESC);

CREATE TABLE IF NOT EXISTS unit_history (
    id         INTEGER PRIMARY KEY,
    unit_id    INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    ru_text    TEXT,
    status     TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now')),
    origin     TEXT NOT NULL DEFAULT 'manual',
    batch_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_unit  ON unit_history(unit_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_batch ON unit_history(batch_id);

CREATE TABLE IF NOT EXISTS qa_ignores (
    unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    code    TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (unit_id, code)
);

CREATE TABLE IF NOT EXISTS tm_entries (
    id         INTEGER PRIMARY KEY,
    en_hash    TEXT NOT NULL,
    en_text    TEXT NOT NULL,
    ru_text    TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'user',
    key        TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(en_hash, ru_text)
);
CREATE INDEX IF NOT EXISTS idx_tm_hash ON tm_entries(en_hash);

CREATE TABLE IF NOT EXISTS legacy_translations (
    id          INTEGER PRIMARY KEY,
    rel_path    TEXT NOT NULL,
    key         TEXT NOT NULL,
    ru_text     TEXT NOT NULL,
    archived_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(rel_path, key, ru_text)
);

CREATE TABLE IF NOT EXISTS scan_history (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    stats_json  TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def register_functions(conn: sqlite3.Connection) -> None:
    """Функции уровня соединения. Обязательно на КАЖДОМ соединении, включая
    соединение фонового сканера — иначе запросы поиска упадут.

    pylower: приведение к нижнему регистру по правилам Unicode. Встроенные
    lower()/upper() и COLLATE NOCASE в SQLite работают только с ASCII, поэтому
    поиск по кириллице без этой функции регистрозависим.
    """
    conn.create_function(
        "pylower", 1, lambda s: s.casefold() if s is not None else None,
        deterministic=True,
    )


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Открыть соединение (создав каталог при необходимости) и применить схему."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    register_functions(conn)
    init_schema(conn)
    return conn


TM_VIEW_BASE = (
    "SELECT id, en_hash, en_text, ru_text, source, key, updated_at, "
    "'Проект' AS origin, 1 AS editable, 0 AS prio FROM main.tm_entries"
)


def ensure_tm_view(conn: sqlite3.Connection) -> None:
    """Представление tm_all — единая точка поиска по памяти переводов.

    Без подключённых баз это просто память самого проекта; project.py
    пересоздаёт его, добавляя подключённые .ck3tm.
    """
    conn.execute("DROP VIEW IF EXISTS tm_all")
    conn.execute("CREATE TEMP VIEW tm_all AS " + TM_VIEW_BASE)
    index_own_tm(conn)


def fts5_available() -> bool:
    """Есть ли FTS5 в этой сборке SQLite.

    В стандартных сборках Python он есть, но приложение не должно падать на
    экзотической: без FTS5 просто не будет поиска похожих строк.
    """
    global _FTS5
    if _FTS5 is None:
        probe = sqlite3.connect(":memory:")
        try:
            probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            _FTS5 = True
        except sqlite3.Error:
            _FTS5 = False
        finally:
            probe.close()
    return _FTS5


_FTS5: bool | None = None

OWN_TM_FTS = "own_tm_fts"


def index_own_tm(conn: sqlite3.Connection) -> None:
    """Индекс похожих строк для памяти самого проекта.

    Она маленькая и постоянно меняется, поэтому индекс временный — живёт в
    соединении, как и представление tm_all, и не требует миграции схемы.
    Триггеры держат его в согласии с таблицей: без них свежие переводы не
    находились бы среди похожих до перезапуска.
    """
    if not fts5_available():
        return
    try:
        conn.executescript(f"""
            DROP TABLE IF EXISTS temp.{OWN_TM_FTS};
            CREATE VIRTUAL TABLE temp.{OWN_TM_FTS} USING fts5(
                en_text, content='', tokenize='unicode61');
        """)
        conn.execute(
            f"INSERT INTO temp.{OWN_TM_FTS}(rowid, en_text) "
            "SELECT id, en_text FROM main.tm_entries")
        # внутри тела триггера имена таблиц пишутся без префикса схемы — SQLite
        # запрещает квалифицированные имена в INSERT/UPDATE/DELETE триггера;
        # у временного триггера они и так разрешаются сперва в temp
        conn.executescript(f"""
            DROP TRIGGER IF EXISTS own_tm_ai;
            DROP TRIGGER IF EXISTS own_tm_ad;
            CREATE TEMP TRIGGER own_tm_ai AFTER INSERT ON main.tm_entries BEGIN
                INSERT INTO {OWN_TM_FTS}(rowid, en_text)
                VALUES (new.id, new.en_text);
            END;
            CREATE TEMP TRIGGER own_tm_ad AFTER DELETE ON main.tm_entries BEGIN
                INSERT INTO {OWN_TM_FTS}({OWN_TM_FTS}, rowid, en_text)
                VALUES ('delete', old.id, old.en_text);
            END;
        """)
        conn.commit()
    except sqlite3.Error:
        # индекс — ускоритель, а не условие работы: без него ищем только по базам
        pass


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    else:
        migrate(conn, int(row[0]))
    # только после миграций: представление ссылается на таблицы, которые
    # миграция пересоздаёт, и мешало бы их удалению
    ensure_tm_view(conn)


def migrate(conn: sqlite3.Connection, from_version: int) -> None:
    """Миграции схемы, последовательно до текущей версии."""
    version = from_version
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"БД имеет версию схемы {version}, приложение ожидает {SCHEMA_VERSION}. "
            "Обновите приложение."
        )
    if version == 1:
        _migrate_1_to_2(conn)
        version = 2
    if version == 2:
        _migrate_2_to_3(conn)
        version = 3
    if version == 3:
        _migrate_3_to_4(conn)
        version = 4
    if version != SCHEMA_VERSION:
        raise RuntimeError(
            f"Не удалось обновить схему БД с версии {from_version} до {SCHEMA_VERSION}."
        )


def _db_file_path(conn: sqlite3.Connection) -> Path | None:
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main" and row[2]:
            return Path(row[2])
    return None


def _backup_db_file(conn: sqlite3.Connection, suffix: str) -> None:
    """Копия файла БД рядом перед необратимой миграцией (для :memory: — пропуск)."""
    import shutil

    path = _db_file_path(conn)
    if path is None or not path.exists():
        return
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copyfile(path, backup)


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: расширение CHECK по units.status (ignored, custom).

    SQLite не умеет ALTER CHECK — пересобираем таблицу.
    """
    _backup_db_file(conn, ".v1.bak")

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute(f"""
            CREATE TABLE units_new (
                id             INTEGER PRIMARY KEY,
                file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                key            TEXT NOT NULL,
                en_version     TEXT NOT NULL DEFAULT '',
                en_text        TEXT,
                en_hash        TEXT,
                prev_en_text   TEXT,
                ru_text        TEXT,
                status         TEXT NOT NULL DEFAULT 'untranslated'
                               CHECK (status IN ({_STATUSES_V2})),
                line_no        INTEGER,
                comment_before TEXT NOT NULL DEFAULT '',
                comment_inline TEXT NOT NULL DEFAULT '',
                is_deleted     INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT,
                UNIQUE(file_id, key)
            )
        """)
        cols = ("id, file_id, key, en_version, en_text, en_hash, prev_en_text, "
                "ru_text, status, line_no, comment_before, comment_inline, "
                "is_deleted, created_at, updated_at")
        conn.execute(f"INSERT INTO units_new ({cols}) SELECT {cols} FROM units")
        conn.execute("DROP TABLE units")
        conn.execute("ALTER TABLE units_new RENAME TO units")
        conn.execute("CREATE INDEX idx_units_file   ON units(file_id)")
        conn.execute("CREATE INDEX idx_units_status ON units(status) WHERE is_deleted = 0")
        conn.execute("CREATE INDEX idx_units_hash   ON units(en_hash)")
        conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"Миграция v1→v2: нарушены внешние ключи: {problems[:5]}")


def _migrate_2_to_3(conn: sqlite3.Connection) -> None:
    """v2 -> v3: удаление статуса «осиротевший» с сохранением переводов.

    Переводы ключей, которых больше нет в оригинале, переезжают в
    legacy_translations (их нельзя держать в units: без исходного текста они
    ломают статистику и не попадают в память переводов). Заодно:
    files теряет is_orphan_ru и получает trailing, tm_entries теряет привязку
    к проекту (файл проекта сам себе провенанс), projects получает языки.
    """
    _backup_db_file(conn, ".v2.bak")
    conn.execute("DROP VIEW IF EXISTS tm_all")   # мешает пересборке таблиц

    before_units = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
    before_orphans = conn.execute(
        "SELECT COUNT(*) FROM units WHERE status = 'orphaned'").fetchone()[0]
    before_tm = conn.execute(
        "SELECT COUNT(DISTINCT en_hash || char(31) || ru_text) FROM tm_entries").fetchone()[0]

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS legacy_translations (
                id          INTEGER PRIMARY KEY,
                rel_path    TEXT NOT NULL,
                key         TEXT NOT NULL,
                ru_text     TEXT NOT NULL,
                archived_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(rel_path, key, ru_text)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO legacy_translations (rel_path, key, ru_text)
            SELECT f.rel_path, u.key, u.ru_text
            FROM units u JOIN files f ON f.id = u.file_id
            WHERE u.status = 'orphaned' AND u.ru_text IS NOT NULL AND u.ru_text != ''
        """)
        archived = conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0]
        conn.execute("DELETE FROM units WHERE status = 'orphaned'")

        # files: -is_orphan_ru, +trailing
        conn.execute("""
            CREATE TABLE files_new (
                id         INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                rel_path   TEXT NOT NULL,
                trailing   TEXT NOT NULL DEFAULT '',
                is_deleted INTEGER NOT NULL DEFAULT 0,
                UNIQUE(project_id, rel_path)
            )
        """)
        conn.execute(
            "INSERT INTO files_new (id, project_id, rel_path, is_deleted) "
            "SELECT id, project_id, rel_path, is_deleted FROM files WHERE is_orphan_ru = 0")
        # юниты осиротевших файлов уже удалены выше вместе со статусом
        conn.execute("DELETE FROM units WHERE file_id NOT IN (SELECT id FROM files_new)")
        conn.execute("DROP TABLE files")
        conn.execute("ALTER TABLE files_new RENAME TO files")

        # units: CHECK без 'orphaned'
        conn.execute(f"""
            CREATE TABLE units_new (
                id             INTEGER PRIMARY KEY,
                file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                key            TEXT NOT NULL,
                en_version     TEXT NOT NULL DEFAULT '',
                en_text        TEXT,
                en_hash        TEXT,
                prev_en_text   TEXT,
                ru_text        TEXT,
                status         TEXT NOT NULL DEFAULT 'untranslated'
                               CHECK (status IN ({ALL_STATUSES})),
                line_no        INTEGER,
                comment_before TEXT NOT NULL DEFAULT '',
                comment_inline TEXT NOT NULL DEFAULT '',
                is_deleted     INTEGER NOT NULL DEFAULT 0,
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT,
                UNIQUE(file_id, key)
            )
        """)
        cols = ("id, file_id, key, en_version, en_text, en_hash, prev_en_text, "
                "ru_text, status, line_no, comment_before, comment_inline, "
                "is_deleted, created_at, updated_at")
        conn.execute(f"INSERT INTO units_new ({cols}) SELECT {cols} FROM units")
        conn.execute("DROP TABLE units")
        conn.execute("ALTER TABLE units_new RENAME TO units")
        conn.execute("CREATE INDEX idx_units_file   ON units(file_id)")
        conn.execute("CREATE INDEX idx_units_status ON units(status) WHERE is_deleted = 0")
        conn.execute("CREATE INDEX idx_units_hash   ON units(en_hash)")

        # tm_entries: -project_id, UNIQUE по паре текстов
        conn.execute("""
            CREATE TABLE tm_new (
                id         INTEGER PRIMARY KEY,
                en_hash    TEXT NOT NULL,
                en_text    TEXT NOT NULL,
                ru_text    TEXT NOT NULL,
                source     TEXT NOT NULL DEFAULT 'user',
                key        TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(en_hash, ru_text)
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO tm_new (en_hash, en_text, ru_text, source, key, updated_at) "
            "SELECT en_hash, en_text, ru_text, source, key, updated_at "
            "FROM tm_entries ORDER BY updated_at DESC")
        conn.execute("DROP TABLE tm_entries")
        conn.execute("ALTER TABLE tm_new RENAME TO tm_entries")
        conn.execute("CREATE INDEX idx_tm_hash ON tm_entries(en_hash)")

        # projects: языки; project_meta
        cols_proj = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "src_lang" not in cols_proj:
            conn.execute("ALTER TABLE projects ADD COLUMN src_lang TEXT NOT NULL DEFAULT 'english'")
        if "tgt_lang" not in cols_proj:
            conn.execute("ALTER TABLE projects ADD COLUMN tgt_lang TEXT NOT NULL DEFAULT 'russian'")
        conn.execute("CREATE TABLE IF NOT EXISTS project_meta (key TEXT PRIMARY KEY, value TEXT)")

        conn.execute("UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'")

        # Ничего не потеряли: было = стало + заархивированное
        after_units = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        after_tm = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
        if after_units + before_orphans != before_units:
            raise RuntimeError(
                f"Миграция v2→v3: расхождение в строках "
                f"(было {before_units}, стало {after_units}, осиротевших {before_orphans})")
        if after_tm != before_tm:
            raise RuntimeError(
                f"Миграция v2→v3: расхождение в памяти переводов "
                f"(было уникальных {before_tm}, стало {after_tm})")
        if before_orphans and archived == 0:
            raise RuntimeError("Миграция v2→v3: осиротевшие переводы не заархивированы")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"Миграция v2→v3: нарушены внешние ключи: {problems[:5]}")


def _migrate_3_to_4(conn: sqlite3.Connection) -> None:
    """v3 -> v4: история редакций оригинала и переводов.

    Только добавление таблиц и колонок — units не пересобирается, поэтому
    переводы физически не перемещаются. Первая редакция оригинала для каждой
    строки заносится задним числом, чтобы история не начиналась с пустоты.
    """
    _backup_db_file(conn, ".v3.bak")

    before_units = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
    before_translated = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]

    try:
        conn.execute("BEGIN")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(units)")}
        if "en_changed_at" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN en_changed_at TEXT")
        if "change_kind" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN change_kind TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_history (
                id INTEGER PRIMARY KEY,
                unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                en_text TEXT NOT NULL, en_hash TEXT NOT NULL, en_version TEXT,
                seen_at TEXT NOT NULL DEFAULT (datetime('now')), scan_id INTEGER
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source_history_unit "
                     "ON source_history(unit_id, seen_at DESC)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unit_history (
                id INTEGER PRIMARY KEY,
                unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                ru_text TEXT, status TEXT,
                changed_at TEXT NOT NULL DEFAULT (datetime('now')),
                origin TEXT NOT NULL DEFAULT 'manual', batch_id TEXT
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_unit "
                     "ON unit_history(unit_id, changed_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_batch "
                     "ON unit_history(batch_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS qa_ignores (
                unit_id INTEGER NOT NULL REFERENCES units(id) ON DELETE CASCADE,
                code TEXT NOT NULL,
                added_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (unit_id, code)
            )""")

        # текущая редакция оригинала становится первой записью истории
        conn.execute("""
            INSERT INTO source_history (unit_id, en_text, en_hash, en_version, seen_at)
            SELECT id, en_text, en_hash, en_version, COALESCE(updated_at, created_at)
            FROM units WHERE en_text IS NOT NULL AND en_hash IS NOT NULL""")
        # известная прошлая редакция устаревших строк — тоже, но раньше по времени
        conn.execute("""
            INSERT INTO source_history (unit_id, en_text, en_hash, en_version, seen_at)
            SELECT id, prev_en_text, '', en_version, created_at
            FROM units WHERE prev_en_text IS NOT NULL AND prev_en_text != ''""")

        conn.execute("UPDATE schema_meta SET value = '4' WHERE key = 'schema_version'")

        after_units = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        after_translated = conn.execute(
            "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
        if after_units != before_units or after_translated != before_translated:
            raise RuntimeError(
                f"Миграция v3→v4: расхождение (строк было {before_units}, стало "
                f"{after_units}; переводов было {before_translated}, стало {after_translated})")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(f"Миграция v3→v4: нарушены внешние ключи: {problems[:5]}")
