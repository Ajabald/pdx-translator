"""Память переводов (TM): exact-match по хешу EN-текста, общая между проектами.

source: 'user' — переводы пользователя; 'vanilla' (v2) — база из ванильной
локализации CK3; 'import' — внешние импорты. Приоритет при выборке: user выше.
"""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from ck3loc.core.models import TmHit
from ck3loc.core.statuses import Status


def escape_like(text: str) -> str:
    """Экранировать спецсимволы LIKE, чтобы искать их буквально (ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def en_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def lookup(conn: sqlite3.Connection, en_text: str, *, limit: int = 5) -> list[TmHit]:
    """Варианты перевода для текста. Один вариант = одна строка результата;
    источник и ключ берутся у записи, победившей по приоритету (оконные функции,
    а не GROUP BY с «голыми» колонками — иначе SQLite вернёт произвольную запись
    группы, и подпись источника может не соответствовать варианту)."""
    rows = conn.execute(
        """
        WITH hits AS (
            SELECT t.id, t.ru_text, t.source, t.origin, t.key, t.updated_at,
                   t.editable, t.prio
            FROM tm_all t
            WHERE t.en_hash = ?
        ), ranked AS (
            SELECT hits.*,
                   ROW_NUMBER() OVER (PARTITION BY ru_text ORDER BY prio, updated_at DESC) AS rn,
                   COUNT(*)     OVER (PARTITION BY ru_text) AS uses
            FROM hits
        )
        SELECT id, ru_text, source, origin, key, uses, updated_at, editable
        FROM ranked WHERE rn = 1
        ORDER BY prio, updated_at DESC
        LIMIT ?
        """,
        (en_hash(en_text), limit),
    ).fetchall()
    return [
        TmHit(
            ru_text=r["ru_text"], source=r["source"], origin=r["origin"],
            key=r["key"], uses=r["uses"], updated_at=r["updated_at"],
            id=r["id"], editable=bool(r["editable"]),
        )
        for r in rows
    ]


def upsert(
    conn: sqlite3.Connection,
    en_text: str,
    ru_text: str,
    *,
    source: str = "user",
    project_id: int | None = None,   # не хранится: провенанс = сам файл проекта
    key: str | None = None,
) -> None:
    if not ru_text or ru_text == en_text:
        return
    conn.execute(
        """
        INSERT INTO tm_entries (en_hash, en_text, ru_text, source, key)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(en_hash, ru_text)
        DO UPDATE SET updated_at = datetime('now'), key = excluded.key
        """,
        (en_hash(en_text), en_text, ru_text, source, key),
    )


@dataclass
class TmRecord:
    """Запись памяти переводов для менеджера."""
    id: int
    en_text: str
    ru_text: str
    source: str
    key: str | None
    origin: str
    editable: bool
    updated_at: str


def browse(
    conn: sqlite3.Connection,
    *,
    search: str = "",
    only_editable: bool = False,
    limit: int = 2000,
) -> list[TmRecord]:
    """Записи памяти переводов (свои и из подключённых баз)."""
    sql = ["SELECT id, en_text, ru_text, source, key, origin, editable, updated_at "
           "FROM tm_all WHERE 1 = 1"]
    params: list = []
    if only_editable:
        sql.append("AND editable = 1")
    if search:
        needle = f"%{escape_like(search.casefold())}%"
        sql.append("AND (pylower(en_text) LIKE ? ESCAPE '\\' "
                   "OR pylower(ru_text) LIKE ? ESCAPE '\\' "
                   "OR pylower(COALESCE(key, '')) LIKE ? ESCAPE '\\')")
        params += [needle, needle, needle]
    sql.append("ORDER BY prio, updated_at DESC LIMIT ?")
    params.append(limit)
    return [
        TmRecord(
            id=r["id"], en_text=r["en_text"], ru_text=r["ru_text"], source=r["source"],
            key=r["key"], origin=r["origin"], editable=bool(r["editable"]),
            updated_at=r["updated_at"],
        )
        for r in conn.execute(" ".join(sql), params)
    ]


def update_entry(conn: sqlite3.Connection, entry_id: int, ru_text: str) -> bool:
    """Изменить перевод в памяти проекта. Подключённые базы только для чтения
    (их записи приходят с отрицательными идентификаторами)."""
    if not ru_text.strip() or entry_id <= 0:
        return False
    try:
        cur = conn.execute(
            "UPDATE tm_entries SET ru_text = ?, updated_at = datetime('now') WHERE id = ?",
            (ru_text, entry_id))
    except sqlite3.IntegrityError:
        # такой перевод для этого текста уже есть — исходную запись убираем
        conn.execute("DELETE FROM tm_entries WHERE id = ?", (entry_id,))
        conn.commit()
        return True
    conn.commit()
    return cur.rowcount > 0


def delete_entries(conn: sqlite3.Connection, entry_ids: Iterable[int]) -> int:
    """Удалить записи памяти проекта; записи подключённых баз пропускаются."""
    ids = [i for i in entry_ids if i > 0]
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(f"DELETE FROM tm_entries WHERE id IN ({placeholders})", ids)
    conn.commit()
    return cur.rowcount


def clear_own(conn: sqlite3.Connection) -> int:
    cur = conn.execute("DELETE FROM tm_entries")
    conn.commit()
    return cur.rowcount


def counts(conn: sqlite3.Connection) -> tuple[int, int]:
    """(своих записей, всего с подключёнными базами)."""
    own = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM tm_all").fetchone()[0]
    return own, total


def feed_from_project(conn: sqlite3.Connection, project_id: int) -> int:
    """Залить в TM все переведённые/проверенные строки проекта."""
    rows = conn.execute(
        """
        SELECT u.en_text, u.ru_text, u.key
        FROM units u JOIN files f ON f.id = u.file_id
        WHERE f.project_id = ? AND u.is_deleted = 0
          AND u.status IN (?, ?, ?) AND u.ru_text IS NOT NULL AND u.en_text IS NOT NULL
        """,
        (project_id, Status.TRANSLATED.value, Status.REVIEWED.value, Status.CUSTOM.value),
    ).fetchall()
    for r in rows:
        upsert(conn, r["en_text"], r["ru_text"], project_id=project_id, key=r["key"])
    return len(rows)


def bulk_apply(conn: sqlite3.Connection, project_id: int) -> int:
    """Заполнить пустые непереведённые строки из TM (только при ровно одном варианте).

    Возвращает число заполненных строк (статус становится 'auto').
    """
    cur = conn.execute(
        """
        UPDATE units SET
            ru_text = (SELECT MIN(t.ru_text) FROM tm_all t WHERE t.en_hash = units.en_hash),
            status = ?,
            updated_at = datetime('now')
        WHERE units.id IN (
            SELECT u.id
            FROM units u
            JOIN files f ON f.id = u.file_id
            WHERE f.project_id = ? AND u.is_deleted = 0
              AND u.status = ? AND u.ru_text IS NULL AND u.en_hash IS NOT NULL
              AND (SELECT COUNT(DISTINCT t.ru_text) FROM tm_all t WHERE t.en_hash = u.en_hash) = 1
        )
        """,
        (Status.AUTO.value, project_id, Status.UNTRANSLATED.value),
    )
    return cur.rowcount
