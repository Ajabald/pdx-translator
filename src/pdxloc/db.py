"""The SQLite connection and the database schema.

The threading rule: one connection per thread — ScanWorker opens its own.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate

SCHEMA_VERSION = 10

# How the project's own memory is labelled in the «Source» column. The value is
# born inside SQL (TM_VIEW_BASE below) and translated at display time — so all
# that stands here is a mark for the string collector.
OWN_ORIGIN = QT_TRANSLATE_NOOP("DetailPane", "Project")

ALL_STATUSES = ("'untranslated','machine','auto','translated','reviewed',"
                "'stale','ignored','custom'")
# Status lists of past versions — needed by the migrations that rebuild the
# units table and must take the data in exactly the shape it lay in.
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
    """Connection-level functions. Mandatory on EVERY connection, the background
    scanner's included, or the search queries fall over.

    pylower: lower-casing by the Unicode rules. SQLite's built-in lower()/upper()
    and COLLATE NOCASE work with ASCII only, so without this function a search in
    Cyrillic is case-sensitive.
    """
    conn.create_function(
        "pylower", 1, lambda s: s.casefold() if s is not None else None,
        deterministic=True,
    )


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection, creating the directory if needed, and apply the schema."""
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
    """The tm_all view — the single point of search over the translation memory.

    With no databases attached it is simply the project's own memory; project.py
    rebuilds it, adding the attached .pdxtm files.
    """
    conn.execute("DROP VIEW IF EXISTS tm_all")
    conn.execute("CREATE TEMP VIEW tm_all AS " + TM_VIEW_BASE)


def fts5_available() -> bool:
    """Whether this SQLite build has FTS5.

    The standard Python builds do, but the application must not fall over on an
    exotic one: without FTS5 there simply is no similar-rows search.
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
    """Build the similar-rows index if this connection does not have one yet.

    It is built on the first similarity query rather than when the project opens:
    a project's memory can be large — 106 268 entries in vanilla HOI4, 0.2 s for
    the index — while it is needed exactly when a translator has landed on a row
    and is looking at the suggestions. Opening a project must not wait for that.
    """
    if conn.execute("SELECT 1 FROM temp.sqlite_master WHERE type = 'table' "
                    "AND name = ?", (OWN_TM_FTS,)).fetchone():
        return
    index_own_tm(conn)


def index_own_tm(conn: sqlite3.Connection) -> None:
    """The similar-rows index for the project's own memory.

    That memory is small and changes constantly, so the index is a temporary one:
    it lives in the connection, as the tm_all view does, and needs no schema
    migration. Triggers keep it in step with the table — without them fresh
    translations would not turn up among the similar ones until a restart.
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
        # inside a trigger body the table names are written without a schema prefix —
        # SQLite forbids qualified names in a trigger's INSERT/UPDATE/DELETE; for a
        # temporary trigger they resolve in temp first anyway
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
        # the index is a speed-up, not a condition of working: without it we search the
        # databases only
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
    # only after the migrations: the view references tables the migration rebuilds,
    # and it would get in the way of dropping them
    ensure_tm_view(conn)


def migrate(conn: sqlite3.Connection, from_version: int) -> None:
    """Schema migrations, applied in order up to the current version."""
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
    """A copy of the database file before an irreversible migration; :memory: is
    skipped."""
    import shutil

    path = _db_file_path(conn)
    if path is None or not path.exists():
        return
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copyfile(path, backup)


def _migrate_1_to_2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: widening the CHECK on units.status (ignored, custom).

    SQLite cannot ALTER a CHECK, so the table is rebuilt.
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
    """v2 -> v3: dropping the «orphaned» status while keeping the translations.

    Translations of keys the original no longer has move into
    legacy_translations — they must not stay in units: with no source text they
    break the statistics and never reach the translation memory. Along the way:
    files loses is_orphan_ru and gains trailing, tm_entries loses its tie to a
    project (a project file is its own provenance), and projects gains the
    languages.
    """
    _backup_db_file(conn, ".v2.bak")
    conn.execute("DROP VIEW IF EXISTS tm_all")   # gets in the way of rebuilding the tables

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
        # units of orphaned files were deleted above, with the status
        conn.execute("DELETE FROM units WHERE file_id NOT IN (SELECT id FROM files_new)")
        conn.execute("DROP TABLE files")
        conn.execute("ALTER TABLE files_new RENAME TO files")

        # units: a CHECK without 'orphaned'
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

        # tm_entries: no project_id, UNIQUE on the pair of texts
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

        # projects: the languages; project_meta
        cols_proj = {r[1] for r in conn.execute("PRAGMA table_info(projects)")}
        if "src_lang" not in cols_proj:
            conn.execute("ALTER TABLE projects ADD COLUMN src_lang TEXT NOT NULL DEFAULT 'english'")
        if "tgt_lang" not in cols_proj:
            conn.execute("ALTER TABLE projects ADD COLUMN tgt_lang TEXT NOT NULL DEFAULT 'russian'")
        conn.execute("CREATE TABLE IF NOT EXISTS project_meta (key TEXT PRIMARY KEY, value TEXT)")

        conn.execute("UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'")

        # Nothing was lost: before = after plus what was archived
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
    """v3 -> v4: the history of revisions of the original and of translations.

    Tables and columns are only added — units is not rebuilt, so the translations
    are not physically moved. The first revision of the original for every row is
    entered retrospectively, so the history does not begin with emptiness.
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

        # the current revision of the original becomes the first history record
        conn.execute("""
            INSERT INTO source_history (unit_id, en_text, en_hash, en_version, seen_at)
            SELECT id, en_text, en_hash, en_version, COALESCE(updated_at, created_at)
            FROM units WHERE en_text IS NOT NULL AND en_hash IS NOT NULL""")
        # the known previous revision of outdated rows becomes one too, dated earlier
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
    """v4 -> v5: the text language apart from the game folder.

    Two new columns and nothing else: `units` is not rebuilt and no copy of the
    file is needed before the migration. The values are left **empty** on purpose
    — an empty locale means «the same as the language folder» (see
    `core/languages.py`), and every existing project carries on without noticing.
    Filling them in now would freeze a guess where the right answer follows
    anyway.
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
    """v6 -> v7: the game of a project.

    One column, as in v4→v5: `units` is untouched and no copy of the file is
    needed. The default value is `ck3`, and that is not a guess: until this
    version the application was called CK3 Translator and knew no other games at
    all.
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
    """v7 -> v8: the check issues are stored together with the row.

    Two columns, as in v4→v5: `units` is not rebuilt and no copy of the file is
    needed. The values stay empty, and that is precisely what «not checked yet»
    means: the first time the table is shown the issues are computed and written.
    They must not be filled in here even if one wanted to: the rule set lives in
    the application settings and in the project file, and the migration runs
    before either has been read.
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
    """v8 -> v9: the glossary of terms.

    The body looks empty, and that is not an oversight. `init_schema` runs the
    `DDL` **before** the migrations, and the table is declared there with
    `CREATE TABLE IF NOT EXISTS` — by this point it exists in an old file too.
    `legacy_translations` appeared the same way in v2→v3 in its day.

    No data is carried over: a glossary starts empty by definition. There would be
    nothing to fill it with here — the candidates are counted over the translation
    memory, and the memory databases are attached later, after the project opens.
    """
    conn.execute("BEGIN")
    try:
        conn.execute("UPDATE schema_meta SET value = '9' WHERE key = 'schema_version'")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _migrate_9_to_10(conn: sqlite3.Connection) -> None:
    """v9 -> v10: the history remembers what a row went stale against.

    Two columns, as in v7→v8: `unit_history` is not rebuilt and no copy of the
    file is needed. For older records the values stay empty, and that is honest —
    nobody was saving them at the time. Undoing such a record gives back the text
    and the status but shows no diff: there is nowhere to recover one from
    retrospectively.
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
    """v5 -> v6: the «machine translation» status.

    The list of statuses is a CHECK constraint, and SQLite cannot alter one — only
    rebuild the table. The constraint is worth it: it is what catches a typo in a
    status at write time rather than a week later in a strange report.

    Not a single row of data changes: only the set of permitted values widens. One
    table is rebuilt, foreign keys point at it from `unit_history` and
    `source_history`, so the swap is done with `foreign_keys` off and an integrity
    check afterwards.
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
