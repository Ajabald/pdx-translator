"""Translation memory: an exact match by the hash of the source text, shared
between projects.

source: 'user' for the user's own translations; 'vanilla' (v2) for a database
built from the vanilla CK3 localisation; 'import' for outside imports. On
selection the priority puts 'user' above the rest.
"""
from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from pdxloc.core.models import TmHit
from pdxloc.core.statuses import Status


def escape_like(text: str) -> str:
    """Escape the LIKE wildcards so they are searched for literally (ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def en_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def lookup(conn: sqlite3.Connection, en_text: str, *, limit: int = 5) -> list[TmHit]:
    """The translation variants for a text.

    One variant is one result row; the source and the key are taken from the
    entry that won on priority. Window functions rather than a GROUP BY with bare
    columns: otherwise SQLite returns an arbitrary entry of the group, and the
    source label may not belong to the variant shown.
    """
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
    project_id: int | None = None,   # not stored: the provenance is the project file itself
    key: str | None = None,
) -> None:
    if not ru_text or ru_text == en_text:
        return
    conn.execute(_UPSERT_SQL, (en_hash(en_text), en_text, ru_text, source, key))


_UPSERT_SQL = """
    INSERT INTO tm_entries (en_hash, en_text, ru_text, source, key)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(en_hash, ru_text)
    DO UPDATE SET updated_at = datetime('now'), key = excluded.key
"""


def upsert_many(
    conn: sqlite3.Connection,
    items,                           # Iterable[(en_text, ru_text, key)]
    *,
    source: str = "user",
) -> int:
    """Add a batch to the translation memory. Returns the number of pairs taken.

    The same query as in `upsert` but through a single `executemany`: importing
    somebody else's translation brings tens of thousands of pairs, and the table
    carries a trigger that updates the search index — a per-row call from Python
    costs more there than everything else put together.
    """
    rows = [(en_hash(en), en, ru, source, key)
            for en, ru, key in items
            if ru and ru != en]
    if rows:
        conn.executemany(_UPSERT_SQL, rows)
    return len(rows)


@dataclass
class TmRecord:
    """A translation memory entry, as the manager sees it."""
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
    """Translation memory entries: our own and those from attached databases."""
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
    """Change a translation in the project memory.

    Attached databases are read-only; their entries arrive with negative ids.
    """
    if not ru_text.strip() or entry_id <= 0:
        return False
    try:
        cur = conn.execute(
            "UPDATE tm_entries SET ru_text = ?, updated_at = datetime('now') WHERE id = ?",
            (ru_text, entry_id))
    except sqlite3.IntegrityError:
        # this text already has that translation: drop the original entry
        conn.execute("DELETE FROM tm_entries WHERE id = ?", (entry_id,))
        conn.commit()
        return True
    conn.commit()
    return cur.rowcount > 0


def delete_entries(conn: sqlite3.Connection, entry_ids: Iterable[int]) -> int:
    """Delete entries of the project memory; entries of attached databases are
    skipped."""
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
    """(own entries, the total including attached databases)."""
    own = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM tm_all").fetchone()[0]
    return own, total


def feed_from_project(conn: sqlite3.Connection, project_id: int) -> int:
    """Pour every translated and reviewed row of the project into the memory.

    The list of statuses is a positive one, and `Status.MACHINE` is left out
    deliberately rather than by oversight: the translation memory is what gets
    trusted when filling other rows, and a machine guess landing there would
    start spreading through the project under somebody else's name. The same goes
    for `Status.AUTO`: it was itself filled from the memory, and there is no
    point putting it back.
    """
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


def bulk_apply(conn: sqlite3.Connection, project_id: int,
               *, batch_id: str | None = None) -> int:
    """Fill empty untranslated rows with exact matches from the memory.

    The winner is chosen the same way as in `lookup`: by the priority of the
    source, and on a tie by recency. There used to be a condition here — «exactly
    one variant across all databases» plus `MIN(t.ru_text)` — and it broke twice
    over. Databases disagree about the translation of one and the same row all
    the time («Fire and Blood» has three variants), and on such rows the fill
    quietly did nothing, while F7 in the same situation confidently offers the
    best variant: the manual and the automatic fill behaved differently for no
    reason at all. And `MIN` picks by the alphabet rather than by the source; it
    was safe only while there was always exactly one variant.

    The risk is small: the status stays «Auto», which reads as «filled in, go and
    check».

    **It goes through the history and comes back with Ctrl+Z.** Only empty rows
    are touched, so there seems to be nothing to lose — but that is not an
    argument: an undo that quietly fails to cover one operation in three teaches
    people not to trust undo at all. And the reach here is not small: on a live
    project the fill covers thousands of rows at once, and there is no other way
    to return them to «not translated».

    Returns the number of rows filled.
    """
    from pdxloc.core import unit_ops

    # The rows are selected by a query of their own rather than inside the UPDATE:
    # the history has to be written BEFORE the edit, or there is nothing left to
    # remember.
    ids = [r["id"] for r in conn.execute(
        """
        SELECT u.id
        FROM units u
        JOIN files f ON f.id = u.file_id
        WHERE f.project_id = ? AND u.is_deleted = 0
          AND u.status = ? AND u.ru_text IS NULL AND u.en_hash IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM tm_all t
              WHERE t.en_hash = u.en_hash AND t.ru_text <> ''
          )
        """,
        (project_id, Status.UNTRANSLATED.value),
    )]
    if not ids:
        return 0

    unit_ops.record_history(conn, ids, origin="from_tm",
                            batch_id=batch_id or unit_ops.new_batch_id())
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"""
        UPDATE units SET
            ru_text = (
                SELECT t.ru_text FROM tm_all t
                WHERE t.en_hash = units.en_hash AND t.ru_text <> ''
                ORDER BY t.prio, t.updated_at DESC
                LIMIT 1
            ),
            status = ?,
            updated_at = datetime('now')
        WHERE units.id IN ({placeholders})
        """,
        (Status.AUTO.value, *ids),
    )
    return cur.rowcount
