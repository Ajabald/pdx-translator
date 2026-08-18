"""Операции над строками — единая точка записи в БД.

Через эти функции работают: детальная панель, правка в ячейке таблицы,
quick-колонки статусов, контекстное меню и массовые операции.
Каждая функция коммитит сама.
"""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable

from pdxloc.core import loc_formats, markup, tm
from pdxloc.core.statuses import Status

# Статусы, которые нельзя ставить без наличия перевода
_NEEDS_RU = {Status.TRANSLATED, Status.REVIEWED, Status.CUSTOM, Status.MACHINE}

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

    Вместе с переводом и статусом запоминаются `prev_en_text` и `change_kind`.
    Без них откат возвращал строке «Устарело», но не то, **чем** она устарела:
    дифф пропадал, и человек оставался с красной строкой без объяснения.
    """
    ids = list(unit_ids)
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"INSERT INTO unit_history "
        f"(unit_id, ru_text, status, prev_en_text, change_kind, origin, batch_id) "
        f"SELECT id, ru_text, status, prev_en_text, change_kind, ?, ? "
        f"FROM units WHERE id IN ({placeholders})",
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
        "SELECT unit_id, ru_text, status, prev_en_text, change_kind "
        "FROM unit_history WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE units SET ru_text = ?, status = ?, prev_en_text = ?, "
            "change_kind = ?, updated_at = datetime('now') WHERE id = ?",
            (row["ru_text"], row["status"], row["prev_en_text"],
             row["change_kind"], row["unit_id"]),
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
    return bool(en_text.strip()) and not markup.strip_markup(en_text)


def has_nothing_to_translate(en_text: str | None) -> bool:
    """Переводить нечего: пусто, одни пробелы, одна разметка или ни одной буквы.

    Пустое значение отделено от разметки намеренно. `is_markup_only` отвечает на
    вопрос «это строка ИЗ разметки», и пустая строка ей не является — на этом
    стоят и подсветка, и отбор строк для машинного перевода. А вот переводить в
    пустом значении нечего ровно так же, как в голом теге: в модах такие ключи
    заводят заглушками под ссылку из скрипта, и без этого правила они на каждом
    переимпорте всплывали бы в списке непереведённых.

    Последнее условие — про строку без единой буквы: `_`, `$NAME$: $VAL|+=0$`,
    `£command_power  §Y40§!`. Букв нет — значит нет и слова, которое можно
    перевести, а числа с иконками переводу не подлежат. Замер: в ванильной CK2
    таких 1 422 (из них 1 329 — заглушки `_` в `FR.csv`, файле французской
    грамматики), в HOI4 — 854 (иконка со стоимостью решения), а на живом моде к
    CK3 — **ни одной**: там подобное и так покрыто разметкой.
    """
    text = (en_text or "").strip()
    if not text or is_markup_only(text):
        return True
    return not any(ch.isalpha() for ch in markup.strip_markup(text))


def auto_ignore_untranslated(
    conn: sqlite3.Connection,
    project_id: int = 1,
    *,
    batch_id: str | None = None,
) -> int:
    """Пометить «игнорируемыми» непереведённые строки, где переводить нечего.

    Это строки из одной разметки — например, [GetPlayer.GetDynasty.GetName]:
    в игре они подставляют имя динамически, и держать их в списке
    непереведённых бессмысленно. Сюда же пустые значения из оригинала. Строки с
    переводом не трогаем: если человек что-то там написал, значит смысл был.

    Правка идёт **одной пачкой** и откатывается через Ctrl+Z. Это не
    формальность: набор «переводить нечего» задаётся реестром разметки, а он
    пополняется — добавили токен, и при следующем открытии проекта сотни строк
    меняют статус. Без отката такое изменение необратимо, а заметить его можно
    и через неделю.

    Помнить о своём прошлом решении функция не умеет — этим занимается тот, кто
    её зовёт (см. `project.get_auto_ignore_done`): откат, который переигрывают
    при следующем открытии, хуже отсутствующего.
    """
    rows = conn.execute(
        """SELECT u.id, u.en_text FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0 AND u.status = ?
             AND u.ru_text IS NULL AND u.en_text IS NOT NULL""",
        (project_id, Status.UNTRANSLATED.value),
    ).fetchall()
    ids = [r["id"] for r in rows if has_nothing_to_translate(r["en_text"])]
    if not ids:
        # пустую пачку не записываем: last_batch начал бы отдавать операцию,
        # которой не было, и Ctrl+Z ничего бы не сделал
        return 0
    record_history(conn, ids, origin="auto_ignore",
                   batch_id=batch_id or new_batch_id())
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


def save_machine_text(
    conn: sqlite3.Connection,
    unit_id: int,
    text: str,
    *,
    batch_id: str,
) -> bool:
    """Записать машинный перевод. Возвращает, изменилось ли что-нибудь.

    Отдельная функция, а не флаг у `save_ru_text`: у той контракт — таблица
    переходов, кончающаяся «Переведено», плюс запись в память переводов. Здесь
    ровно наоборот, и оба «наоборот» существенны:

    * статус — «Машинный», потому что текст никто не читал;
    * в память переводов **не пишем**. Память — это то, чему доверяют при
      подстановке в другие строки и в другие проекты; машинная догадка, попав
      туда, начала бы расползаться от имени готового перевода.

    Флаг заставил бы `save_ru_text` пропускать почти всё своё тело, и каждая
    следующая правка той функции обязана была бы про него помнить.
    """
    row = conn.execute("SELECT ru_text, en_text FROM units WHERE id = ?",
                       (unit_id,)).fetchone()
    if row is None:
        return False
    ru_text = loc_formats.normalize_newlines(text)
    if not ru_text.strip():
        # пустой машинный перевод — не перевод; статус «Машинный» без текста
        # означал бы, что строка заполнена, а это враньё
        return False
    if ru_text == row["ru_text"]:
        return False

    record_history(conn, [unit_id], origin="machine", batch_id=batch_id)
    conn.execute(
        "UPDATE units SET ru_text = ?, status = ?, updated_at = datetime('now') "
        "WHERE id = ?", (ru_text, Status.MACHINE.value, unit_id))
    conn.commit()
    return True


def status_after_edit(
    current: str,
    new_text: str | None,
    old_text: str | None,
    prev_en: str | None,
    change_kind: str | None,
) -> tuple[str, str | None, str | None]:
    """Каким станет состояние строки после правки перевода.

    Возвращает `(статус, prev_en_text, change_kind)`. Ни базы, ни записи — чтобы
    таблицу переходов можно было звать и построчно (`save_ru_text`), и пачкой
    (импорт перевода из мода). Логика тут одна на оба пути **намеренно**: разойдись
    они, импорт начал бы оставлять строки в состояниях, которых не бывает при
    ручной правке, — и заметить это можно было бы только глазами, на чужом моде.

    `new_text` — уже приведённый к формату Paradox текст либо `None`, если
    перевод стёрли.
    """
    status, prev = current, prev_en

    if new_text is None:
        if status in (Status.TRANSLATED.value, Status.REVIEWED.value,
                      Status.AUTO.value, Status.MACHINE.value,
                      Status.CUSTOM.value):
            status = Status.UNTRANSLATED.value
    elif status in (Status.UNTRANSLATED.value, Status.AUTO.value,
                    Status.MACHINE.value, Status.IGNORED.value):
        # правка человеком снимает «машинный»: иначе строка навсегда осталась бы
        # непроверенной, а такие в мод не выгружаются — правки просто не доехали бы
        status = Status.TRANSLATED.value
    elif status == Status.STALE.value and new_text != (old_text or ""):
        # правка перевода по новому EN = актуализация
        status = Status.TRANSLATED.value
        prev = None

    # правка перевода снимает пометку устаревания: строка приведена в соответствие
    kind = change_kind if status == Status.STALE.value else None
    return status, prev, kind


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
    # Настоящий перенос строки приводим к виду формата Paradox сразу при записи
    # в базу, а не только при выгрузке в мод: иначе база и файл расходятся
    # ровно на этот символ, и каждое следующее сканирование докладывает
    # «расхождение с файлом» на строке, которую никто не трогал.
    text = loc_formats.normalize_newlines(text)
    ru_text = text if text.strip() else None
    if ru_text != row["ru_text"]:
        record_history(conn, [unit_id], origin=origin, batch_id=batch_id)

    status, prev_en, change_kind = status_after_edit(
        row["status"], ru_text, row["ru_text"], row["prev_en_text"], row["change_kind"])
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


def apply_to_same_en(
    conn: sqlite3.Connection,
    unit_id: int,
    *,
    batch_id: str | None = None,
) -> list[int]:
    """Применить перевод строки ко всем непереведённым строкам с тем же EN-текстом.

    Операция массовая — на живом проекте задевает сотни строк, — поэтому пишет
    историю и обязана вызываться с `batch_id`: без него Ctrl+Z её не увидит.
    Среди целей есть строки со статусом «Авто», у которых перевод уже стоял,
    и затирать его безвозвратно нельзя.
    """
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
        record_history(conn, targets, origin="apply_same", batch_id=batch_id)
        placeholders = ",".join("?" * len(targets))
        conn.execute(
            f"UPDATE units SET ru_text = ?, status = ?, updated_at = datetime('now') "
            f"WHERE id IN ({placeholders})",
            (row["ru_text"], Status.TRANSLATED.value, *targets),
        )
        tm.upsert(conn, row["en_text"], row["ru_text"], project_id=pid, key=row["key"])
        conn.commit()
    return targets


def apply_best_tm(
    conn: sqlite3.Connection,
    unit_id: int,
    *,
    batch_id: str | None = None,
) -> bool:
    """Подставить лучший хит из памяти переводов (статус auto).

    Пишет историю, как и всякая правка перевода: подстановка затирает то, что
    в строке уже стояло, и редакция должна остаться — иначе её не вернуть ни
    Ctrl+Z (когда операция идёт пачкой), ни через историю строки.
    """
    row = conn.execute("SELECT en_text FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None or not row["en_text"]:
        return False
    hits = tm.lookup(conn, row["en_text"], limit=1)
    if not hits:
        return False
    record_history(conn, [unit_id], origin="from_tm", batch_id=batch_id)
    conn.execute(
        "UPDATE units SET ru_text = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
        (hits[0].ru_text, Status.AUTO.value, unit_id),
    )
    conn.commit()
    return True
