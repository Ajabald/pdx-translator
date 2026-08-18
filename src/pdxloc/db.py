"""Подключение к SQLite и схема БД.

Правило потоков: одно соединение на поток (ScanWorker открывает своё).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate

SCHEMA_VERSION = 10

# Как подписана собственная память проекта в колонке «Источник». Значение
# рождается прямо в SQL (TM_VIEW_BASE ниже) и переводится в момент показа —
# поэтому здесь только пометка для сборщика строк.
OWN_ORIGIN = QT_TRANSLATE_NOOP("DetailPane", "Project")

ALL_STATUSES = ("'untranslated','machine','auto','translated','reviewed',"
                "'stale','ignored','custom'")
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
    -- Игра Paradox, к которой относится мод. Формат локализации у серии общий,
    -- но языковые папки, базы памяти и загон на диске у каждой игры свои
    -- (см. core/games.py). Своя игра хранит здесь слаг своего имени.
    game           TEXT NOT NULL DEFAULT 'ck3',
    src_lang       TEXT NOT NULL DEFAULT 'english',
    tgt_lang       TEXT NOT NULL DEFAULT 'russian',
    -- Язык текста, если он не совпадает с папкой игры (перевод на язык,
    -- которого в игре нет). Пусто = выводится из папки, см. core/languages.py
    src_locale     TEXT NOT NULL DEFAULT '',
    tgt_locale     TEXT NOT NULL DEFAULT '',
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
    -- Замечания проверки, посчитанные в прошлый раз, и отпечаток того, по чему
    -- они посчитаны (набор правил + оба текста). Живут в самой строке, а не в
    -- отдельной таблице: тогда правка перевода обесценивает их сама, и ни один
    -- путь записи не может забыть про сброс кеша. См. core/qa.py.
    qa_hash        TEXT,
    qa_codes       TEXT,
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
    -- Прежняя редакция оригинала и вид правки. Без них откат возвращал строке
    -- статус «Устарело», но не то, ЧЕМ она устарела: дифф пропадал, и человек
    -- видел красную строку без объяснения. Поля живут здесь, а не в units,
    -- потому что откат — операция над историей.
    prev_en_text TEXT,
    change_kind  TEXT,
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

CREATE TABLE IF NOT EXISTS glossary (
    id         INTEGER PRIMARY KEY,
    en_term    TEXT NOT NULL,
    ru_term    TEXT NOT NULL,
    -- candidate — предложено статистикой и ждёт человека; approved — принято и
    -- подсвечивается в поле оригинала; rejected — отклонено насовсем. Третий
    -- статус обязателен: без него каждый следующий прогон возвращал бы тот же
    -- мусор, и курировать список было бы бессмысленно. Тот же приём, что у
    -- qa_ignores: «человек уже посмотрел и сказал нет» — это данные.
    status     TEXT NOT NULL DEFAULT 'candidate'
               CHECK (status IN ('candidate','approved','rejected')),
    -- Уверенность и охват на момент предложения. Хранятся, а не считаются
    -- заново: прогон идёт по памяти переводов, а она меняется, и число рядом
    -- со строкой обязано означать «вот на чём это было предложено».
    score      REAL,
    pairs      INTEGER,
    note       TEXT NOT NULL DEFAULT '',
    origin     TEXT NOT NULL DEFAULT 'auto' CHECK (origin IN ('auto','manual')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    UNIQUE(en_term, ru_term)
);
CREATE INDEX IF NOT EXISTS idx_glossary_status ON glossary(status);

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
    "'Project' AS origin, 1 AS editable, 0 AS prio FROM main.tm_entries"
)


def ensure_tm_view(conn: sqlite3.Connection) -> None:
    """Представление tm_all — единая точка поиска по памяти переводов.

    Без подключённых баз это просто память самого проекта; project.py
    пересоздаёт его, добавляя подключённые .pdxtm.
    """
    conn.execute("DROP VIEW IF EXISTS tm_all")
    conn.execute("CREATE TEMP VIEW tm_all AS " + TM_VIEW_BASE)


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


def ensure_own_tm_index(conn: sqlite3.Connection) -> None:
    """Построить индекс похожих строк, если в этом соединении его ещё нет.

    Строится по первому запросу похожих строк, а не при открытии проекта:
    памяти в проекте бывает много (106 268 записей у ванильной HOI4 — 0,2 с на
    индекс), а нужна она ровно тогда, когда переводчик встал на строку и
    смотрит подсказки. Открытие проекта этого ждать не должно.
    """
    if conn.execute("SELECT 1 FROM temp.sqlite_master WHERE type = 'table' "
                    "AND name = ?", (OWN_TM_FTS,)).fetchone():
        return
    index_own_tm(conn)


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
            fill(translate("Db",
                           "The database has schema version %1, the application "
                           "expects %2. Please update the application."),
                 version, SCHEMA_VERSION)
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
    if version == 4:
        _migrate_4_to_5(conn)
        version = 5
    if version == 5:
        _migrate_5_to_6(conn)
        version = 6
    if version == 6:
        _migrate_6_to_7(conn)
        version = 7
    if version == 7:
        _migrate_7_to_8(conn)
        version = 8
    if version == 8:
        _migrate_8_to_9(conn)
        version = 9
    if version == 9:
        _migrate_9_to_10(conn)
        version = 10
    if version != SCHEMA_VERSION:
        raise RuntimeError(
            fill(translate("Db",
                           "Could not upgrade the database schema from version "
                           "%1 to %2."), from_version, SCHEMA_VERSION)
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
        raise RuntimeError(fill(translate("Db", "Migration v1→v2: foreign keys violated: %1"),
                           problems[:5]))


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
                fill(translate("Db",
                               "Migration v2→v3: row count mismatch "
                               "(was %1, became %2, orphaned %3)"),
                     before_units, after_units, before_orphans))
        if after_tm != before_tm:
            raise RuntimeError(
                fill(translate("Db",
                               "Migration v2→v3: translation memory mismatch "
                               "(unique before %1, after %2)"),
                     before_tm, after_tm))
        if before_orphans and archived == 0:
            raise RuntimeError(translate("Db",
                               "Migration v2→v3: orphaned translations were not "
                               "archived"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(fill(translate("Db", "Migration v2→v3: foreign keys violated: %1"),
                           problems[:5]))


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
            raise RuntimeError(fill(translate(
                "Db", "Migration v3→v4: mismatch (rows before %1, after %2; "
                      "translations before %3, after %4)"),
                before_units, after_units, before_translated, after_translated))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise RuntimeError(fill(translate("Db", "Migration v3→v4: foreign keys violated: %1"),
                           problems[:5]))


def _migrate_4_to_5(conn: sqlite3.Connection) -> None:
    """v4 -> v5: язык текста отдельно от папки игры.

    Две новые колонки и больше ничего: `units` не пересобирается, копия файла
    перед миграцией не нужна. Значения оставляем **пустыми** намеренно —
    пустая локаль означает «совпадает с папкой языка» (см. `core/languages.py`),
    и все существующие проекты продолжают работать, ничего не заметив.
    Проставить их сейчас значило бы зафиксировать догадку там, где верный
    ответ и так выводится.
    """
    conn.execute("BEGIN")
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "src_locale" not in cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN src_locale TEXT NOT NULL DEFAULT ''")
        if "tgt_locale" not in cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN tgt_locale TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE schema_meta SET value = '5' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_6_to_7(conn: sqlite3.Connection) -> None:
    """v6 -> v7: игра проекта.

    Одна колонка, как и в v4→v5: `units` не трогается, копия файла не нужна.
    Значение по умолчанию — `ck3`, и это не догадка: до этой версии приложение
    звалось CK3 Translator и других игр не знало вовсе.
    """
    conn.execute("BEGIN")
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "game" not in cols:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN game TEXT NOT NULL DEFAULT 'ck3'")
        conn.execute("UPDATE schema_meta SET value = '7' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_7_to_8(conn: sqlite3.Connection) -> None:
    """v7 -> v8: замечания проверки хранятся вместе со строкой.

    Две колонки, как в v4→v5: `units` не пересобирается, копия файла не нужна.
    Значения остаются пустыми — это и значит «ещё не проверено»: первый же
    показ таблицы посчитает замечания и запишет их. Заполнять здесь нельзя,
    даже если бы хотелось: набор правил живёт в настройке приложения и в файле
    проекта, а миграция идёт до того, как их прочитали.
    """
    conn.execute("BEGIN")
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(units)")}
        if "qa_hash" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN qa_hash TEXT")
        if "qa_codes" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN qa_codes TEXT")
        conn.execute("UPDATE schema_meta SET value = '8' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_8_to_9(conn: sqlite3.Connection) -> None:
    """v8 -> v9: глоссарий терминов.

    Тело выглядит пустым, и это не недосмотр. `init_schema` прогоняет `DDL`
    **до** миграций, а таблица там заведена через `CREATE TABLE IF NOT EXISTS`
    — к этому месту она уже создана и в старом файле тоже. Ровно так же в своё
    время появилась `legacy_translations` в v2→v3.

    Данных не переносим: глоссарий начинается пустым по определению. Заполнить
    его здесь было бы нечем — кандидаты считаются по памяти переводов, а базы
    памяти подключаются позже, уже после открытия проекта.
    """
    conn.execute("BEGIN")
    try:
        conn.execute("UPDATE schema_meta SET value = '9' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_9_to_10(conn: sqlite3.Connection) -> None:
    """v9 -> v10: история помнит, чем строка устарела.

    Две колонки, как в v7→v8: `unit_history` не пересобирается, копия файла не
    нужна. Значения у прежних записей остаются пустыми, и это честно — в тот
    момент их никто не сохранял. Откат такой записи вернёт текст и статус, но
    диффа не покажет: восстановить его задним числом неоткуда.
    """
    conn.execute("BEGIN")
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(unit_history)")}
        if "prev_en_text" not in cols:
            conn.execute("ALTER TABLE unit_history ADD COLUMN prev_en_text TEXT")
        if "change_kind" not in cols:
            conn.execute("ALTER TABLE unit_history ADD COLUMN change_kind TEXT")
        conn.execute("UPDATE schema_meta SET value = '10' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_5_to_6(conn: sqlite3.Connection) -> None:
    """v5 -> v6: статус «машинный перевод».

    Список статусов задан CHECK-ограничением, а его SQLite менять не умеет —
    только пересборкой таблицы. Ограничение того стоит: именно оно ловит опечатку
    в статусе на записи, а не через неделю на странном отчёте.

    Данные не меняются ни на строку: расширяется только множество допустимых
    значений. Пересобирается одна таблица, внешние ключи на неё смотрят из
    `unit_history` и `source_history`, поэтому обмен делается при выключенном
    `foreign_keys` и с проверкой целостности после.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
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
                en_changed_at  TEXT,
                change_kind    TEXT,
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at     TEXT,
                UNIQUE(file_id, key)
            )
        """)
        cols = ("id, file_id, key, en_version, en_text, en_hash, prev_en_text, "
                "ru_text, status, line_no, comment_before, comment_inline, "
                "is_deleted, en_changed_at, change_kind, created_at, updated_at")
        before = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        conn.execute(f"INSERT INTO units_new ({cols}) SELECT {cols} FROM units")
        conn.execute("DROP TABLE units")
        conn.execute("ALTER TABLE units_new RENAME TO units")
        conn.execute("CREATE INDEX idx_units_file   ON units(file_id)")
        conn.execute(
            "CREATE INDEX idx_units_status ON units(status) WHERE is_deleted = 0")
        conn.execute("CREATE INDEX idx_units_hash   ON units(en_hash)")

        after = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        if before != after:
            raise RuntimeError(
                fill(translate("Db", "Migration v5→v6: row count mismatch "
                                     "(was %1, became %2)"), before, after))
        broken = conn.execute("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(
                fill(translate("Db", "Migration v5→v6: foreign keys violated: %1"),
                     len(broken)))

        conn.execute("UPDATE schema_meta SET value = '6' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
