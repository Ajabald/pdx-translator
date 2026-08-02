"""Операции над строками — единая точка записи в БД.

Через эти функции работают: детальная панель, правка в ячейке таблицы,
quick-колонки статусов, контекстное меню и массовые операции.
Каждая функция коммитит сама.
"""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable

from ck3loc.core import qa, tm
from ck3loc.core.statuses import Status

# Статусы, которые нельзя ставить без наличия перевода
_NEEDS_RU = {Status.TRANSLATED, Status.REVIEWED, Status.CUSTOM}

# Сколько редакций перевода храним на строку — дальше вытесняем старые
HISTORY_LIMIT = 50


def new_batch_id() -> str:
    """Метка групповой операции: по ней потом откатывается всё разом."""
    return uuid.uuid4().hex


def record_history(
    conn: sqlite3.Connection,
    unit_ids: Iterable[int],
    *,
    origin: str = "manual",
    batch_id: str | None = None,
) -> None:
    """Запомнить текущее состояние строк ДО изменения.

    Вызывается перед записью, иначе откатывать будет нечего.
    """
    ids = list(unit_ids)
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"INSERT INTO unit_history (unit_id, ru_text, status, origin, batch_id) "
        f"SELECT id, ru_text, status, ?, ? FROM units WHERE id IN ({placeholders})",
        (origin, batch_id, *ids),
    )
    for unit_id in ids:
        conn.execute(
            """DELETE FROM unit_history WHERE unit_id = ? AND id NOT IN (
                   SELECT id FROM unit_history WHERE unit_id = ?
                   ORDER BY changed_at DESC, id DESC LIMIT ?)""",
            (unit_id, unit_id, HISTORY_LIMIT),
        )


def undo_batch(conn: sqlite3.Connection, batch_id: str) -> int:
    """Вернуть строки к состоянию до групповой операции."""
    rows = conn.execute(
        "SELECT unit_id, ru_text, status FROM unit_history WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE units SET ru_text = ?, status = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (row["ru_text"], row["status"], row["unit_id"]),
        )
    conn.execute("DELETE FROM unit_history WHERE batch_id = ?", (batch_id,))
    conn.commit()
    return len(rows)


def last_batch(conn: sqlite3.Connection) -> tuple[str, str, int] | None:
    """Последняя групповая операция: (batch_id, origin, сколько строк)."""
    row = conn.execute(
        """SELECT batch_id, origin, COUNT(*) AS n, MAX(changed_at) AS at
           FROM unit_history WHERE batch_id IS NOT NULL
           GROUP BY batch_id ORDER BY at DESC LIMIT 1"""
    ).fetchone()
    return (row["batch_id"], row["origin"], row["n"]) if row else None


def unit_history(conn: sqlite3.Connection, unit_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM unit_history WHERE unit_id = ? ORDER BY changed_at DESC, id DESC",
        (unit_id,),
    ).fetchall()


def source_history(conn: sqlite3.Connection, unit_id: int) -> list[sqlite3.Row]:
    """Редакции оригинала — от свежей к старой."""
    return conn.execute(
        "SELECT * FROM source_history WHERE unit_id = ? ORDER BY seen_at DESC, id DESC",
        (unit_id,),
    ).fetchall()


def is_markup_only(en_text: str) -> bool:
    """Строка из одной CK3-разметки: после её вычистки текста не остаётся."""
    return bool(en_text.strip()) and not qa.strip_markup(qa.RE_NEWLINE.sub(" ", en_text)).strip()


def auto_ignore_untranslated(conn: sqlite3.Connection, project_id: int = 1) -> int:
    """Пометить «игнорируемыми» непереведённые строки, где переводить нечего.

    Это строки из одной разметки — например, [GetPlayer.GetDynasty.GetName]:
    в игре они подставляют имя динамически, и держать их в списке
    непереведённых бессмысленно. Строки с переводом не трогаем: если человек
    что-то там написал, значит смысл был.
    """
    rows = conn.execute(
        """SELECT u.id, u.en_text FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0 AND u.status = ?
             AND u.ru_text IS NULL AND u.en_text IS NOT NULL""",
        (project_id, Status.UNTRANSLATED.value),
    ).fetchall()
    ids = [r["id"] for r in rows if is_markup_only(r["en_text"])]
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE units SET status = ?, updated_at = datetime('now') "
        f"WHERE id IN ({placeholders})", (Status.IGNORED.value, *ids))
    conn.commit()
    return len(ids)


def _project_id_of(conn: sqlite3.Connection, unit_id: int) -> int:
    return conn.execute(
        "SELECT f.project_id FROM units u JOIN files f ON f.id = u.file_id WHERE u.id = ?",
        (unit_id,),
    ).fetchone()[0]


def save_ru_text(
    conn: sqlite3.Connection,
    unit_id: int,
    text: str,
    *,
    origin: str = "manual",
    batch_id: str | None = None,
) -> None:
    """Сохранить текст перевода с автопереходами статусов (логика из DetailPane v1)."""
    row = conn.execute("SELECT * FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None:
        return
    ru_text = text if text.strip() else None
    if ru_text != row["ru_text"]:
        record_history(conn, [unit_id], origin=origin, batch_id=batch_id)
    status = row["status"]
    prev_en = row["prev_en_text"]

    if ru_text is None:
        if status in (Status.TRANSLATED.value, Status.REVIEWED.value,
                      Status.AUTO.value, Status.CUSTOM.value):
            status = Status.UNTRANSLATED.value
    elif status in (Status.UNTRANSLATED.value, Status.AUTO.value, Status.IGNORED.value):
        status = Status.TRANSLATED.value
    elif status == Status.STALE.value and ru_text != (row["ru_text"] or ""):
        # правка перевода по новому EN = актуализация
        status = Status.TRANSLATED.value
        prev_en = None

    # правка перевода снимает пометку устаревания: строка приведена в соответствие
    change_kind = None if status != Status.STALE.value else row["change_kind"]
    conn.execute(
        "UPDATE units SET ru_text = ?, status = ?, prev_en_text = ?, change_kind = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (ru_text, status, prev_en, change_kind, unit_id),
    )
    if ru_text and row["en_text"]:
        tm.upsert(conn, row["en_text"], ru_text,
                  project_id=_project_id_of(conn, unit_id), key=row["key"])
    conn.commit()


def set_status(
    conn: sqlite3.Connection,
    unit_ids: Iterable[int],
    status: Status,
    *,
    origin: str = "bulk",
    batch_id: str | None = None,
) -> int:
    """Массовая смена статуса. Возвращает число изменённых строк.

    translated/reviewed/custom требуют непустого ru_text; ignored/untranslated — нет.
    Прежняя редакция оригинала (`prev_en_text`) сохраняется: она нужна, чтобы
    показать, что именно изменил автор мода, и терять её из-за смены статуса
    нельзя. Снимается только пометка устаревания.
    """
    ids = list(unit_ids)
    if not ids:
        return 0
    record_history(conn, ids, origin=origin, batch_id=batch_id)
    placeholders = ",".join("?" * len(ids))
    gate = "AND ru_text IS NOT NULL" if status in _NEEDS_RU else ""
    cur = conn.execute(
        f"UPDATE units SET status = ?, change_kind = NULL, updated_at = datetime('now') "
        f"WHERE id IN ({placeholders}) AND is_deleted = 0 AND en_text IS NOT NULL {gate}",
        (status.value, *ids),
    )
    conn.commit()
    return cur.rowcount


def actualize(
    conn: sqlite3.Connection,
    unit_ids: Iterable[int],
    *,
    batch_id: str | None = None,
) -> int:
    """Подтвердить, что перевод соответствует новой редакции оригинала."""
    ids = list(unit_ids)
    if not ids:
        return 0
    record_history(conn, ids, origin="actualize", batch_id=batch_id)
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE units SET status = ?, change_kind = NULL, updated_at = datetime('now') "
        f"WHERE id IN ({placeholders}) AND status = ? AND ru_text IS NOT NULL",
        (Status.TRANSLATED.value, *ids, Status.STALE.value),
    )
    conn.commit()
    return cur.rowcount


def cosmetic_stale_ids(conn: sqlite3.Connection, project_id: int = 1) -> list[int]:
    """Устаревшие строки, где автор мода правил только оформление."""
    return [r["id"] for r in conn.execute(
        """SELECT u.id FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0 AND u.status = ?
             AND u.change_kind = 'cosmetic' AND u.ru_text IS NOT NULL""",
        (project_id, Status.STALE.value))]


def reset_translation(
    conn: sqlite3.Connection,
    unit_ids: Iterable[int],
    *,
    origin: str = "bulk",
    batch_id: str | None = None,
) -> int:
    ids = list(unit_ids)
    if not ids:
        return 0
    record_history(conn, ids, origin=origin, batch_id=batch_id)
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"UPDATE units SET ru_text = NULL, status = ?, "
        f"updated_at = datetime('now') "
        f"WHERE id IN ({placeholders}) AND en_text IS NOT NULL",
        (Status.UNTRANSLATED.value, *ids),
    )
    conn.commit()
    return cur.rowcount


def count_same_en(conn: sqlite3.Connection, unit_id: int) -> int:
    """Сколько строк проекта получат перевод при «применить ко всем с таким же EN»."""
    row = conn.execute("SELECT en_hash FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None or row["en_hash"] is None:
        return 0
    pid = _project_id_of(conn, unit_id)
    return conn.execute(
        """SELECT COUNT(*) FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.en_hash = ? AND u.id != ?
             AND u.is_deleted = 0 AND u.status IN (?, ?)""",
        (pid, row["en_hash"], unit_id,
         Status.UNTRANSLATED.value, Status.AUTO.value),
    ).fetchone()[0]


def apply_to_same_en(conn: sqlite3.Connection, unit_id: int) -> list[int]:
    """Применить перевод строки ко всем непереведённым строкам с тем же EN-текстом."""
    row = conn.execute("SELECT * FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None or not row["ru_text"] or row["en_hash"] is None:
        return []
    pid = _project_id_of(conn, unit_id)
    targets = [r["id"] for r in conn.execute(
        """SELECT u.id FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.en_hash = ? AND u.id != ?
             AND u.is_deleted = 0 AND u.status IN (?, ?)""",
        (pid, row["en_hash"], unit_id,
         Status.UNTRANSLATED.value, Status.AUTO.value),
    )]
    if targets:
        placeholders = ",".join("?" * len(targets))
        conn.execute(
            f"UPDATE units SET ru_text = ?, status = ?, updated_at = datetime('now') "
            f"WHERE id IN ({placeholders})",
            (row["ru_text"], Status.TRANSLATED.value, *targets),
        )
        tm.upsert(conn, row["en_text"], row["ru_text"], project_id=pid, key=row["key"])
        conn.commit()
    return targets


def apply_best_tm(conn: sqlite3.Connection, unit_id: int) -> bool:
    """Подставить лучший хит из памяти переводов (статус auto)."""
    row = conn.execute("SELECT en_text FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None or not row["en_text"]:
        return False
    hits = tm.lookup(conn, row["en_text"], limit=1)
    if not hits:
        return False
    conn.execute(
        "UPDATE units SET ru_text = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
        (hits[0].ru_text, Status.AUTO.value, unit_id),
    )
    conn.commit()
    return True
