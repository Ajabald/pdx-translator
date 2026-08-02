"""Файлы проектов (.ck3proj) и подключение баз памяти переводов.

Проект — самостоятельный файл SQLite: строки, файлы, память переводов, архив.
Его можно положить куда угодно и передать другому человеку.

Базы памяти переводов (.ck3tm) подключаются к соединению только на чтение;
поиск идёт по объединяющему представлению tm_all (см. attach_tm_sources).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ck3loc import db as db_module
from ck3loc import settings
from ck3loc.db import init_schema, register_functions

# Приоритет источников памяти переводов: свои переводы, затем экспорты чужих
# проектов, затем большие игровые базы.
KIND_PRIORITY = {"project-export": 1, "import": 2, "game": 3}
KIND_LABELS = {
    "game": "база игры",
    "project-export": "экспорт проекта",
    "import": "импорт",
}


def _uri(path: Path, mode: str) -> str:
    return f"file:{quote(str(path).replace(chr(92), '/'), safe='/:')}?mode={mode}"


# --- проекты ---

def create_project(
    path: Path,
    *,
    name: str,
    src_root: Path | str,
    tgt_root: Path | str,
    src_lang: str = "english",
    tgt_lang: str = "russian",
) -> sqlite3.Connection:
    """Создать новый файл проекта и вернуть открытое соединение."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Файл проекта уже существует: {path}")
    conn = open_project(path)
    conn.execute(
        "INSERT INTO projects (id, name, en_root, ru_root, src_lang, tgt_lang) "
        "VALUES (1, ?, ?, ?, ?, ?)",
        (name, str(src_root), str(tgt_root), src_lang, tgt_lang),
    )
    conn.commit()
    return conn


def open_project(path: Path, tm_paths: list[Path] | None = None) -> sqlite3.Connection:
    """Открыть файл проекта, применить схему и подключить базы памяти."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # uri=True нужен не только здесь: без него нельзя подключать базы по URI
    conn = sqlite3.connect(_uri(path, "rwc"), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    register_functions(conn)
    init_schema(conn)
    conn.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('format', 'ck3proj')")
    conn.commit()
    attach_tm_sources(conn, tm_paths if tm_paths is not None else project_tm_paths(conn))
    return conn


def project_name(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT name FROM projects WHERE id = 1").fetchone()
    return row["name"] if row else "(без имени)"


def save_project_as(conn: sqlite3.Connection, new_path: Path) -> Path:
    """Сохранить копию проекта по новому пути (соединение закрывается вызывающим)."""
    new_path = Path(new_path)
    if new_path.exists():
        raise FileExistsError(f"Файл уже существует: {new_path}")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # VACUUM INTO не работает внутри транзакции и требует отсутствия цели
    conn.execute("VACUUM INTO ?", (str(new_path),))
    return new_path


# --- перенос базы прежних версий ---

def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip(" .")
    return cleaned or "project"


def convert_legacy_db(legacy_path: Path, target_dir: Path | None = None) -> list[Path]:
    """Разложить общую базу прежних версий по отдельным файлам проектов.

    Исходный файл не изменяется: работаем с копиями, а после успешной проверки
    переименовываем оригинал в *.migrated. Если что-то не сходится —
    незавершённая копия удаляется, оригинал остаётся нетронутым.
    """
    import shutil

    legacy_path = Path(legacy_path)
    target_dir = Path(target_dir) if target_dir else settings.projects_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(_uri(legacy_path, "ro"), uri=True)
    src.row_factory = sqlite3.Row
    try:
        projects = src.execute("SELECT id, name FROM projects ORDER BY id").fetchall()
        expected = {
            r["id"]: src.execute(
                "SELECT COUNT(*) FROM units u JOIN files f ON f.id = u.file_id "
                "WHERE f.project_id = ? AND u.status != 'orphaned'", (r["id"],)).fetchone()[0]
            for r in projects
        }
        expected_done = {
            r["id"]: src.execute(
                "SELECT COUNT(*) FROM units u JOIN files f ON f.id = u.file_id "
                "WHERE f.project_id = ? AND u.status IN ('translated','reviewed')",
                (r["id"],)).fetchone()[0]
            for r in projects
        }
    finally:
        src.close()

    created: list[Path] = []
    for row in projects:
        pid, name = row["id"], row["name"]
        out = target_dir / f"{_safe_filename(name)}{settings.PROJECT_EXT}"
        n = 2
        while out.exists():
            out = target_dir / f"{_safe_filename(name)}_{n}{settings.PROJECT_EXT}"
            n += 1
        tmp = dst = conn = None
        try:
            # копия файла целиком, затем выбрасываем всё, кроме нужного проекта
            tmp = sqlite3.connect(_uri(legacy_path, "ro"), uri=True)
            dst = sqlite3.connect(str(out))
            with dst:
                tmp.backup(dst)
            tmp.close()
            tmp = None
            dst.row_factory = sqlite3.Row
            dst.execute("PRAGMA foreign_keys = ON")
            dst.execute("DELETE FROM projects WHERE id != ?", (pid,))   # каскад чистит чужое
            dst.commit()
            # смена id проекта временно рвёт связи, поэтому проверку ключей
            # выключаем — PRAGMA действует только вне транзакции
            dst.execute("PRAGMA foreign_keys = OFF")
            dst.execute("UPDATE files SET project_id = 1 WHERE project_id = ?", (pid,))
            dst.execute("UPDATE scan_history SET project_id = 1 WHERE project_id = ?", (pid,))
            dst.execute("UPDATE projects SET id = 1 WHERE id = ?", (pid,))
            dst.commit()
            dst.close()
            dst = None

            conn = open_project(out, [])       # здесь схема доедет до текущей версии
            units = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
            done = conn.execute(
                "SELECT COUNT(*) FROM units WHERE status IN ('translated','reviewed')"
            ).fetchone()[0]
            conn.close()
            conn = None
            if units != expected[pid] or done != expected_done[pid]:
                raise RuntimeError(
                    f"перенос проекта «{name}»: ожидалось {expected[pid]} строк "
                    f"({expected_done[pid]} переведено), получено {units} ({done})")
            created.append(out)
        except Exception:
            for c in (tmp, dst, conn):
                if c is not None:
                    c.close()
            out.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(str(out) + suffix).unlink(missing_ok=True)
            raise

    # оригинал сохраняем под другим именем — на случай, если что-то упустили
    migrated = legacy_path.with_suffix(legacy_path.suffix + ".migrated")
    if not migrated.exists():
        for suffix in ("-wal", "-shm"):
            Path(str(legacy_path) + suffix).unlink(missing_ok=True)
        shutil.move(str(legacy_path), str(migrated))
    return created


def _has_content(path: Path) -> bool:
    """Есть ли в базе прежней версии хоть что-то, ради чего её переносить."""
    try:
        conn = sqlite3.connect(_uri(path, "ro"), uri=True)
    except sqlite3.Error:
        return False
    try:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        units = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
        return bool(projects and units)
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def migrate_legacy_if_needed() -> list[Path]:
    """Однократный перенос при первом запуске новой версии."""
    if settings.recent_projects():
        return []
    legacy = settings.default_db_path()
    # пустой файл от прежних версий переносить незачем — только мусор плодить
    if not legacy.exists() or not _has_content(legacy):
        return []
    created = convert_legacy_db(legacy)
    for path in created:
        conn = open_project(path, [])
        from ck3loc.core.stats import project_stats
        stats = project_stats(conn, 1)
        settings.remember_project(path, project_name(conn), stats.done, stats.total)
        conn.close()
    return created


# --- базы памяти переводов ---

def tm_meta(path: Path) -> dict[str, str] | None:
    """Прочитать описание базы. None, если файл не является базой памяти."""
    try:
        conn = sqlite3.connect(_uri(Path(path), "ro"), uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = conn.execute("SELECT key, value FROM tm_meta").fetchall()
        meta = {k: v for k, v in rows}
        if meta.get("format") != "ck3tm":
            return None
        meta["entries"] = str(conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0])
        return meta
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def list_tm_databases(directory: Path | None = None) -> list[tuple[Path, dict[str, str]]]:
    """Все корректные базы памяти переводов в папке Bdd."""
    directory = Path(directory) if directory else settings.bdd_dir()
    if not directory.is_dir():
        return []
    result = []
    for p in sorted(directory.glob(f"*{settings.TM_EXT}")):
        meta = tm_meta(p)
        if meta is not None:
            result.append((p, meta))
    return result


def get_tm_sources(conn: sqlite3.Connection) -> list[str]:
    """Имена подключённых баз (без путей — проект остаётся переносимым)."""
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = 'tm_sources'").fetchone()
    if not row or not row["value"]:
        return []
    try:
        return [str(x) for x in json.loads(row["value"])]
    except (ValueError, TypeError):
        return []


def set_tm_sources(conn: sqlite3.Connection, names: list[str]) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES ('tm_sources', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(names, ensure_ascii=False),))
    conn.commit()


# --- папка вывода: куда записывается перевод ---

def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def get_export_root(conn: sqlite3.Connection) -> str | None:
    """Папка, куда записывали перевод в прошлый раз.

    Хранится отдельно от `ru_root`: та — источник импорта, и по умолчанию
    писать поверх неё значит затирать дерево, из которого читали.
    """
    return _meta(conn, "export_root")


def set_export_root(conn: sqlite3.Connection, path: Path | str) -> None:
    _set_meta(conn, "export_root", str(path))


def get_last_export_at(conn: sqlite3.Connection) -> str | None:
    return _meta(conn, "last_export_at")


def set_last_export_at(conn: sqlite3.Connection, when: str | None = None) -> None:
    _set_meta(conn, "last_export_at",
              when or datetime.now().strftime("%Y-%m-%d %H:%M"))


def project_tm_paths(conn: sqlite3.Connection) -> list[Path]:
    """Пути включённых баз, существующих в текущей папке Bdd."""
    bdd = settings.bdd_dir()
    return [bdd / name for name in get_tm_sources(conn) if (bdd / name).is_file()]


def attach_tm_sources(conn: sqlite3.Connection, tm_paths: list[Path]) -> list[str]:
    """Подключить базы на чтение и пересобрать представление tm_all.

    Представление временное, то есть живёт в пределах соединения: фоновому
    сканеру нужно вызывать open_project самому, а не получать чужой connect.
    """
    for row in conn.execute("PRAGMA database_list").fetchall():
        if row[1].startswith("tm"):
            conn.execute(f"DETACH DATABASE {row[1]}")
    conn.execute("DROP VIEW IF EXISTS tm_all")

    parts = [db_module.TM_VIEW_BASE]
    attached: list[str] = []
    for i, path in enumerate(tm_paths):
        path = Path(path)
        if not path.is_file():
            continue
        meta = tm_meta(path)
        if meta is None:
            continue
        alias = f"tm{i}"
        try:
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (_uri(path, "ro"),))
        except sqlite3.Error:
            continue
        origin = meta.get("name") or path.stem
        prio = KIND_PRIORITY.get(meta.get("kind", "import"), 5)
        # идентификаторы подключённых баз делаем отрицательными: нумерация в
        # каждом файле своя, и без этого удаление чужой записи стёрло бы свою
        # с тем же номером
        parts.append(
            f"SELECT -(id + {(i + 1) * 10_000_000}) AS id, "
            "en_hash, en_text, ru_text, source, key, updated_at, "
            f"'{origin.replace(chr(39), chr(39) * 2)}' AS origin, 0 AS editable, "
            f"{prio} AS prio FROM {alias}.tm_entries")
        attached.append(origin)
    conn.execute("CREATE TEMP VIEW tm_all AS " + " UNION ALL ".join(parts))
    db_module.index_own_tm(conn)
    return attached


@dataclass
class AttachedTm:
    """Подключённая база для поиска похожих строк."""

    alias: str            # tm0, tm1 … — по нему адресуются таблицы базы
    origin: str           # имя базы, как его видит пользователь
    prio: int             # приоритет источника, как в tm_all
    id_offset: int        # смещение идентификаторов, чтобы совпадало с tm_all
    has_fts: bool         # построен ли индекс похожих строк


def attached_tm_bases(conn: sqlite3.Connection) -> list[AttachedTm]:
    """Подключённые базы с признаком «есть ли индекс похожих строк».

    Поиск похожих идёт по каждой базе отдельно (индекс живёт внутри неё), а не
    через объединяющее представление tm_all, поэтому нужны сами алиасы.
    """
    from ck3loc.core import tm_import

    bases: list[AttachedTm] = []
    for row in conn.execute("PRAGMA database_list").fetchall():
        alias, path = row[1], row[2]
        if not alias.startswith("tm") or not path:
            continue
        meta = tm_meta(Path(path)) or {}
        index = int(alias[2:]) if alias[2:].isdigit() else 0
        bases.append(AttachedTm(
            alias=alias,
            origin=meta.get("name") or Path(path).stem,
            prio=KIND_PRIORITY.get(meta.get("kind", "import"), 5),
            id_offset=(index + 1) * 10_000_000,
            has_fts=tm_import.has_fts_index(conn, alias),
        ))
    return bases


