"""Operations on rows — the single point of writing to the database.

Everything goes through these functions: the detail panel, editing in a table
cell, the quick status columns, the context menu and the bulk operations. Each
function commits for itself.
"""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterable

from pdxloc.core import loc_formats, markup, tm
from pdxloc.core.statuses import Status

# Statuses that must not be set without a translation present
_NEEDS_RU = {Status.TRANSLATED, Status.REVIEWED, Status.CUSTOM, Status.MACHINE}

# How many revisions of a translation are kept per row; older ones are evicted
HISTORY_LIMIT = 50


def new_batch_id() -> str:
    """The mark of a group operation: it is what the whole undo goes by later."""
    return uuid.uuid4().hex


def record_history(
    conn: sqlite3.Connection,
    unit_ids: Iterable[int],
    *,
    origin: str = "manual",
    batch_id: str | None = None,
) -> None:
    """Remember the current state of the rows BEFORE the change.

    Called before the write, or there is nothing left to undo.

    Along with the translation and the status, `prev_en_text` and `change_kind`
    are remembered. Without them an undo gave the row back its «Outdated» status
    but not **what** it was outdated against: the diff disappeared, and the person
    was left with a red row and no explanation.
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
    """Return the rows to their state before a group operation."""
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
    """The last group operation: (batch_id, origin, how many rows)."""
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
    """Revisions of the original, newest first."""
    return conn.execute(
        "SELECT * FROM source_history WHERE unit_id = ? ORDER BY seen_at DESC, id DESC",
        (unit_id,),
    ).fetchall()


def is_markup_only(en_text: str) -> bool:
    """A row of nothing but CK3 markup: strip it and no text is left."""
    return bool(en_text.strip()) and not markup.strip_markup(en_text)


def has_nothing_to_translate(en_text: str | None) -> bool:
    """Nothing to translate: empty, all spaces, all markup, or not one letter.

    An empty value is kept apart from markup on purpose. `is_markup_only` answers
    the question «is this a row MADE OF markup», and an empty row is not one — the
    highlighting and the selection of rows for machine translation both rest on
    that. But an empty value has exactly as little to translate as a bare tag: in
    mods such keys are created as stubs for a reference from a script, and without
    this rule they would surface in the untranslated list on every reimport.

    The last condition is about a row without a single letter: `_`,
    `$NAME$: $VAL|+=0$`, `£command_power  §Y40§!`. No letters means no word that
    could be translated, and numbers with icons are not subject to translation.
    Measured: vanilla CK2 has 1 422 of them — 1 329 being `_` stubs in `FR.csv`,
    the French grammar file — HOI4 has 854 (an icon with the cost of a decision),
    and a live CK3 mod has **none**: there such rows are covered by the markup
    rule anyway.
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
    """Mark as «ignored» the untranslated rows with nothing to translate.

    These are rows of pure markup — [GetPlayer.GetDynasty.GetName], say: in the
    game they substitute a name dynamically, and keeping them in the untranslated
    list is pointless. Empty values from the original belong here too. Rows that
    have a translation are left alone: if somebody wrote something there, there
    was a reason.

    The edit goes as **one batch** and comes back with Ctrl+Z. That is not a
    formality: the «nothing to translate» set is defined by the markup registry,
    and the registry grows — add a token and, on the next project open, hundreds
    of rows change status. Without an undo such a change is irreversible, and it
    can go unnoticed for a week.

    The function cannot remember its own past decision — the caller sees to that
    (see `project.get_auto_ignore_done`): an undo that gets replayed on the next
    open is worse than no undo at all.
    """
    rows = conn.execute(
        """SELECT u.id, u.en_text FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0 AND u.status = ?
             AND u.ru_text IS NULL AND u.en_text IS NOT NULL""",
        (project_id, Status.UNTRANSLATED.value),
    ).fetchall()
    ids = [r["id"] for r in rows if has_nothing_to_translate(r["en_text"])]
    if not ids:
        # an empty batch is not recorded: last_batch would start handing back an
        # operation that never happened, and Ctrl+Z would do nothing
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
    """Write a machine translation. Returns whether anything changed.

    A function of its own rather than a flag on `save_ru_text`: that one's
    contract is the transition table ending in «Translated», plus a write into the
    translation memory. Here it is the exact opposite on both counts, and both
    matter:

    * the status is «Machine», because nobody has read the text;
    * we do **not** write into the translation memory. The memory is what gets
      trusted when filling other rows and other projects; a machine guess landing
      there would start spreading under the name of a finished translation.

    A flag would have made `save_ru_text` skip almost its entire body, and every
    later edit to that function would have had to remember it.
    """
    row = conn.execute("SELECT ru_text, en_text FROM units WHERE id = ?",
                       (unit_id,)).fetchone()
    if row is None:
        return False
    ru_text = loc_formats.normalize_newlines(text)
    if not ru_text.strip():
        # an empty machine translation is not a translation; the «Machine» status with
        # no text would say the row is filled in, and that is a lie
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
    the transition table could be called both per row (`save_ru_text`) and as a
    batch (importing a translation from a mod). The logic here is shared by both
    paths **deliberately**: let them diverge and the import would start leaving
    rows in states that never arise from a manual edit — and that could only be
    spotted by eye, on somebody else's mod.

    `new_text` is text already brought into the Paradox form, or `None` when the
    translation was erased.
    """
    status, prev = current, prev_en

    if new_text is None:
        if status in (Status.TRANSLATED.value, Status.REVIEWED.value,
                      Status.AUTO.value, Status.MACHINE.value,
                      Status.CUSTOM.value):
            status = Status.UNTRANSLATED.value
    elif status in (Status.UNTRANSLATED.value, Status.AUTO.value,
                    Status.MACHINE.value, Status.IGNORED.value):
        # an edit by a person clears «machine»: otherwise the row would stay unchecked
        # forever, and such rows are not written to the mod — the edits simply would not
        # arrive
        status = Status.TRANSLATED.value
    elif status == Status.STALE.value and new_text != (old_text or ""):
        # editing the translation against the new original counts as actualising it
        status = Status.TRANSLATED.value
        prev = None

    # editing the translation clears the outdated mark: the row has been brought
    # into line
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
    """Save the translation text with the automatic status transitions.

    The logic comes from DetailPane v1.
    """
    row = conn.execute("SELECT * FROM units WHERE id = ?", (unit_id,)).fetchone()
    if row is None:
        return
    # A real line break is brought into the Paradox form as soon as it is written to
    # the database rather than only on export to the mod: otherwise the database and
    # the file differ by exactly that character, and every subsequent scan reports
    # «diverges from the file» on a row nobody touched.
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
    """A bulk status change. Returns the number of rows changed.

    translated/reviewed/custom require a non-empty ru_text; ignored/untranslated
    do not. The previous revision of the original (`prev_en_text`) is kept: it is
    what shows exactly what the mod author changed, and losing it over a status
    change is not acceptable. Only the outdated mark is cleared.
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
    """Confirm that the translation matches the new revision of the original."""
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
    """Outdated rows where the mod author changed nothing but the presentation."""
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
    """How many project rows would be filled by «apply to all with the same original»."""
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
    """Apply a row's translation to every untranslated row with the same original.

    The operation is a bulk one — on a live project it touches hundreds of rows —
    so it writes history and must be called with a `batch_id`: without one Ctrl+Z
    will not see it. Among the targets are rows with the «Auto» status that
    already had a translation, and overwriting that beyond recovery is not
    acceptable.
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
    """Fill in the best hit from the translation memory, with the «auto» status.

    It writes history, as every edit to a translation does: the fill overwrites
    whatever stood in the row, and that revision has to survive — otherwise it
    cannot be brought back either by Ctrl+Z, when the operation goes as a batch,
    or through the row history.
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
