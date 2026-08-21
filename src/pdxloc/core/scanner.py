"""Scanning a project: importing and rescanning the localisation trees into the DB.

The first import and a rescan after a mod update are one and the same code: a
diff machine compares a fresh parse of the source and translation trees with the
state in the database.

The scanner does not know the file format — it asks `core/loc_formats.py`: in the
current games of the series the language sits in the file name and in the path
(`english/x_l_english.yml` → `russian/x_l_russian.yml`), while in the older ones
it is a column inside the same row and the path in the translation tree is the
very same. Everything that depends on this goes through `fmt.files()` and
`fmt.map_relpath()`.

The scanner's own conventions:
- Files with '_updated' in the name are ignored (litter from the user's old
  scripts).
- The old scripts' marker '# !!! ТРЕБУЕТ ПЕРЕВОДА' in the translation, and
  translation == original, both mean «not translated».
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from collections.abc import Callable

from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_formats, paradox_csv, tm, unit_ops
from pdxloc.core.progress import throttled
from pdxloc.core.models import LocEntry, ScanStats
from pdxloc.core.statuses import Status
from pdxloc.core.textdiff import COSMETIC, classify_change
from pdxloc.core.unit_ops import has_nothing_to_translate

LEGACY_MARKER = "ТРЕБУЕТ ПЕРЕВОДА"

ProgressCb = Callable[[int, int, str], None]


def _ru_entry_state(
    en_text: str | None,
    entry: LocEntry,
    *,
    file_has_real_translations: bool = False,
    is_new_unit: bool = False,
) -> tuple[str, bool]:
    """(ru_text, is_translated) for an entry read from disk.

    The rules:
      - the old scripts' marker -> not translated;
      - the text differs from the original -> translated;
      - the text equals the original -> translated only on the first import, and
        only when the file holds at least one real translation (otherwise it is
        simply a copy of the source tree). A translation identical to the
        original is normal for proper nouns, «OK» and numbers.
    """
    if LEGACY_MARKER in entry.comment_inline or not entry.text:
        return entry.text, False
    if entry.text != (en_text or ""):
        return entry.text, True
    return entry.text, is_new_unit and file_has_real_translations


def _file_has_real_translations(
    en_entries: dict[str, LocEntry], ru_entries: dict[str, LocEntry]
) -> bool:
    """Whether the translation file holds a single entry differing from the original."""
    for key, ru_entry in ru_entries.items():
        en_entry = en_entries.get(key)
        if (en_entry is not None and ru_entry.text
                and LEGACY_MARKER not in ru_entry.comment_inline
                and ru_entry.text != en_entry.text):
            return True
    return False


class ScanCancelled(Exception):
    """The scan was interrupted by the user; the changes are rolled back whole."""


def _format_of(conn: sqlite3.Connection, en_root: Path) -> loc_formats.LocFormat:
    """The project format: from the project file, and from the tree on the first scan."""
    from pdxloc import project as project_module

    stored = project_module.get_loc_format(conn)
    if stored:
        return loc_formats.get(stored)
    format_id = loc_formats.detect(en_root)
    project_module.set_loc_format(conn, format_id)
    return loc_formats.get(format_id)


def _encodings_of(conn: sqlite3.Connection, fmt: loc_formats.LocFormat,
                  en_root: Path, ru_root: Path) -> tuple[str, str]:
    """The encodings of the source tree and of the translation tree.

    Kept apart because they really do differ: vanilla CK2 lies in cp1252 while
    its Russian translation lies in cp1251. The translation encoding is remembered
    in the project: the export will write in it at a time when the tree may no
    longer be at hand.
    """
    from pdxloc import project as project_module

    if len(fmt.encodings) == 1:
        return fmt.encodings[0], fmt.encodings[0]
    src = paradox_csv.detect_encoding(fmt.files(en_root))
    project_module.set_source_encoding(conn, src)
    stored = project_module.get_loc_encoding(conn)
    if stored:
        return src, stored
    tgt = (paradox_csv.detect_encoding(fmt.files(ru_root))
           if ru_root.is_dir() else "cp1251")
    project_module.set_loc_encoding(conn, tgt)
    return src, tgt


def scan_project(
    conn: sqlite3.Connection,
    project_id: int,
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ScanStats:
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(fill(translate("Scanner", "Project id=%1 not found"), project_id))
    en_root = Path(proj["en_root"])
    ru_root = Path(proj["ru_root"])
    from pdxloc.project import languages as project_languages

    langs = project_languages(conn, project_id)
    src_lang, tgt_lang = langs.src_lang, langs.tgt_lang
    if not en_root.is_dir():
        raise FileNotFoundError(fill(translate("Scanner", "Original folder not found: %1"), en_root))

    fmt = _format_of(conn, en_root)
    src_encoding, tgt_encoding = _encodings_of(conn, fmt, en_root, ru_root)

    stats = ScanStats()
    started_at = datetime.now(UTC).isoformat()

    # --- 1. Parsing the source tree ---
    en_files = fmt.files(en_root, src_lang)
    stats.files_en = len(en_files)
    en_data: dict[str, dict[str, LocEntry]] = {}   # rel_path -> key -> entry
    file_trailing: dict[str, str] = {}
    total_steps = len(en_files)
    report_progress = throttled(progress_cb)
    for i, p in enumerate(en_files):
        if should_cancel is not None and should_cancel():
            raise ScanCancelled
        rel = p.relative_to(en_root).as_posix()
        report_progress(i, total_steps, rel)
        lf = fmt.parse_file(p, language=src_lang, encoding=src_encoding)
        stats.parse_warnings.extend(lf.warnings)
        entries: dict[str, LocEntry] = {}
        for e in lf.entries:
            if e.key in entries:
                stats.duplicate_keys.append(f"{rel}: {e.key}")
            # An empty value in the original is almost always an oversight by the mod
            # author: a key is created as a stub for a reference from a script. There is
            # nothing to translate — the row goes to «ignored» — but staying silent is not
            # allowed, or nobody learns about the defect. It is not counted over the
            # translation tree: there an empty value simply means «not translated yet».
            if not e.text.strip():
                stats.empty_source_keys.append(f"{rel}: {e.key}")
            entries[e.key] = e   # the last one wins, as CK3 itself does
        en_data[rel] = entries
        file_trailing[rel] = lf.trailing

    # --- 2. Parsing the translation: pairs for the source files, plus orphans ---
    def parse_ru_entries(path: Path, rel: str) -> dict[str, LocEntry]:
        lf = fmt.parse_file(path, language=tgt_lang, encoding=tgt_encoding)
        stats.parse_warnings.extend(lf.warnings)
        entries: dict[str, LocEntry] = {}
        for e in lf.entries:
            if e.key in entries:
                stats.duplicate_keys_ru.append(f"{rel}: {e.key}")
            entries[e.key] = e     # the last one wins, as in the game itself
        return entries

    ru_data: dict[str, dict[str, LocEntry]] = {}   # rel_path of the original -> key -> entry
    for rel in en_data:
        rel_tgt = fmt.map_relpath(rel, src_lang, tgt_lang)
        ru_path = ru_root / rel_tgt
        if ru_path.is_file():
            ru_data[rel] = parse_ru_entries(ru_path, rel_tgt)
            stats.files_ru += 1

    orphan_ru: dict[str, dict[str, LocEntry]] = {}  # rel_path of the translation -> key -> entry
    if ru_root.is_dir():
        for p in fmt.files(ru_root, tgt_lang, skip_updated=True):
            rel_ru = p.relative_to(ru_root).as_posix()
            if fmt.map_relpath(rel_ru, tgt_lang, src_lang) in en_data:
                continue
            orphan_ru[rel_ru] = parse_ru_entries(p, rel_ru)
            stats.files_ru += 1

    # --- 3. A snapshot of the database state ---
    files_db = {
        r["rel_path"]: r
        for r in conn.execute("SELECT * FROM files WHERE project_id = ?", (project_id,))
    }
    units_db: dict[tuple[str, str], sqlite3.Row] = {}
    for r in conn.execute(
        """SELECT u.*, f.rel_path FROM units u
           JOIN files f ON f.id = u.file_id WHERE f.project_id = ?""",
        (project_id,),
    ):
        units_db[(r["rel_path"], r["key"])] = r

    now = datetime.now(UTC).isoformat()

    def ensure_file(rel: str) -> int:
        trailing = file_trailing.get(rel, "")
        row = files_db.get(rel)
        if row is not None:
            conn.execute(
                "UPDATE files SET is_deleted = 0, trailing = ? WHERE id = ?",
                (trailing, row["id"]))
            return row["id"]
        cur = conn.execute(
            "INSERT INTO files (project_id, rel_path, trailing) VALUES (?, ?, ?)",
            (project_id, rel, trailing))
        return cur.lastrowid

    def record_source(unit_id: int, en_text: str, en_hash: str, version: str) -> None:
        """Remember a revision of the original when it is new for this row."""
        last = conn.execute(
            "SELECT en_hash FROM source_history WHERE unit_id = ? "
            "ORDER BY seen_at DESC, id DESC LIMIT 1", (unit_id,)).fetchone()
        if last is not None and last["en_hash"] == en_hash:
            return
        conn.execute(
            "INSERT INTO source_history (unit_id, en_text, en_hash, en_version, seen_at, scan_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (unit_id, en_text, en_hash, version, now, None),
        )

    def archive(rel: str, key: str, text: str) -> None:
        """The translation of a key the original no longer has goes to the archive."""
        if not text:
            return
        cur = conn.execute(
            "INSERT OR IGNORE INTO legacy_translations (rel_path, key, ru_text) "
            "VALUES (?, ?, ?)", (rel, key, text))
        if cur.rowcount:
            stats.archived += 1

    # --- 4. The diff machine over the source keys ---
    seen_units: set[tuple[str, str]] = set()
    for rel, entries in en_data.items():
        file_id = ensure_file(rel)
        ru_entries = ru_data.get(rel, {})
        has_real = _file_has_real_translations(entries, ru_entries)
        for key, e in entries.items():
            seen_units.add((rel, key))
            new_hash = tm.en_hash(e.text)
            db_unit = units_db.get((rel, key))
            ru_entry = ru_entries.get(key)
            disk_ru, disk_translated = (None, False)
            if ru_entry is not None:
                disk_ru, disk_translated = _ru_entry_state(
                    e.text, ru_entry,
                    file_has_real_translations=has_real,
                    is_new_unit=db_unit is None,
                )

            if db_unit is None:
                # a new key. A row of bare markup, or an empty one, has nothing to translate —
                # a copy of the original in the translation file does not change that; but if
                # there really is other text there, we respect it as a translation.
                if has_nothing_to_translate(e.text) and (not disk_translated or disk_ru == e.text):
                    status, ru_text = Status.IGNORED.value, None
                    stats.auto_ignored += 1
                elif disk_translated:
                    status, ru_text = Status.TRANSLATED.value, disk_ru
                else:
                    status, ru_text = Status.UNTRANSLATED.value, None
                cur = conn.execute(
                    """INSERT INTO units (file_id, key, en_version, en_text, en_hash,
                                          ru_text, status, line_no, comment_before, comment_inline,
                                          updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (file_id, key, e.version, e.text, new_hash, ru_text, status,
                     e.line_no, e.comment_before, e.comment_inline, now),
                )
                record_source(cur.lastrowid, e.text, new_hash, e.version)
                stats.new += 1
                continue

            status = db_unit["status"]
            restored = bool(db_unit["is_deleted"])
            if restored:
                stats.restored += 1

            # The translation in the database and the one on disk have parted ways: the
            # database wins, but an edit made on disk used to be lost in silence whenever
            # the original had changed as well.
            if (db_unit["ru_text"] is not None and disk_translated
                    and disk_ru != db_unit["ru_text"]):
                stats.ru_conflicts += 1
                stats.ru_conflict_list.append((rel, key, db_unit["ru_text"], disk_ru or ""))

            if db_unit["en_hash"] == new_hash:
                # the original did not change
                if status == Status.UNTRANSLATED.value and db_unit["ru_text"] is None and disk_translated:
                    conn.execute(
                        "UPDATE units SET ru_text = ?, status = ?, is_deleted = 0, "
                        "en_version = ?, line_no = ?, comment_before = ?, comment_inline = ?, updated_at = ? "
                        "WHERE id = ?",
                        (disk_ru, Status.TRANSLATED.value, e.version, e.line_no,
                         e.comment_before, e.comment_inline, now, db_unit["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE units SET is_deleted = 0, en_version = ?, line_no = ?, "
                        "comment_before = ?, comment_inline = ? WHERE id = ?",
                        (e.version, e.line_no, e.comment_before, e.comment_inline, db_unit["id"]),
                    )
                if not restored:
                    stats.unchanged += 1
                continue

            # The original changed: remember the revision and the nature of the edit
            record_source(db_unit["id"], e.text, new_hash, e.version)
            kind = classify_change(db_unit["en_text"] or "", e.text)
            if kind == COSMETIC:
                stats.changed_cosmetic += 1
            else:
                stats.changed_meaningful += 1

            if status == Status.IGNORED.value:
                # there was nothing to translate and there still is not — keep the ignore;
                # text appeared, so it needs translating
                if has_nothing_to_translate(e.text):
                    conn.execute(
                        "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, is_deleted = 0, "
                        "line_no = ?, comment_before = ?, comment_inline = ?, updated_at = ? WHERE id = ?",
                        (e.text, new_hash, e.version, e.line_no,
                         e.comment_before, e.comment_inline, now, db_unit["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, "
                        "ru_text = NULL, status = ?, is_deleted = 0, line_no = ?, "
                        "comment_before = ?, comment_inline = ?, updated_at = ? WHERE id = ?",
                        (e.text, new_hash, e.version, Status.UNTRANSLATED.value,
                         e.line_no, e.comment_before, e.comment_inline, now, db_unit["id"]),
                    )
            elif status in (Status.TRANSLATED.value, Status.REVIEWED.value, Status.CUSTOM.value):
                conn.execute(
                    "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, "
                    "prev_en_text = ?, status = ?, is_deleted = 0, line_no = ?, "
                    "comment_before = ?, comment_inline = ?, en_changed_at = ?, "
                    "change_kind = ?, updated_at = ? WHERE id = ?",
                    (e.text, new_hash, e.version, db_unit["en_text"], Status.STALE.value,
                     e.line_no, e.comment_before, e.comment_inline, now, kind, now,
                     db_unit["id"]),
                )
                stats.stale += 1
            elif status == Status.STALE.value:
                # prev_en_text is left alone: the diff is against the text the translation was
                # based on. The nature of the edit is judged from the same text rather than
                # from an intermediate revision.
                kind_from_base = classify_change(db_unit["prev_en_text"] or "", e.text)
                conn.execute(
                    "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, is_deleted = 0, "
                    "line_no = ?, comment_before = ?, comment_inline = ?, en_changed_at = ?, "
                    "change_kind = ?, updated_at = ? WHERE id = ?",
                    (e.text, new_hash, e.version, e.line_no,
                     e.comment_before, e.comment_inline, now, kind_from_base, now,
                     db_unit["id"]),
                )
                stats.stale += 1
            elif status in (Status.AUTO.value, Status.MACHINE.value):
                # What the machine filled in has gone stale: reset it and look in the memory
                # again (bulk_apply below). Machine translation goes here rather than into
                # «outdated»: it was made for the previous text, nobody has read it, and
                # leaving it as it is would mean keeping the translation of another row in the
                # guise of something nearly finished — and it would travel into the mod under
                # the «including machine translation» checkbox.
                conn.execute(
                    "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, "
                    "ru_text = NULL, status = ?, is_deleted = 0, line_no = ?, "
                    "comment_before = ?, comment_inline = ?, updated_at = ? WHERE id = ?",
                    (e.text, new_hash, e.version, Status.UNTRANSLATED.value,
                     e.line_no, e.comment_before, e.comment_inline, now, db_unit["id"]),
                )
            else:   # untranslated, or an orphan that became a source row
                new_status = status
                ru_text = db_unit["ru_text"]
                if disk_translated and ru_text is None:
                    new_status, ru_text = Status.TRANSLATED.value, disk_ru
                conn.execute(
                    "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, "
                    "ru_text = ?, status = ?, is_deleted = 0, line_no = ?, "
                    "comment_before = ?, comment_inline = ?, updated_at = ? WHERE id = ?",
                    (e.text, new_hash, e.version, ru_text, new_status,
                     e.line_no, e.comment_before, e.comment_inline, now, db_unit["id"]),
                )

        # keys the original does not have: the translation goes to the archive and no
        # row is created
        for key, ru_entry in ru_entries.items():
            if key not in entries and LEGACY_MARKER not in ru_entry.comment_inline:
                archive(rel, key, ru_entry.text)

    # --- 5. Translation files with no counterpart: archive only ---
    for rel_ru, entries in orphan_ru.items():
        stats.orphan_ru_files.append(rel_ru)
        for key, ru_entry in entries.items():
            if LEGACY_MARKER not in ru_entry.comment_inline:
                archive(rel_ru, key, ru_entry.text)

    # --- 6. Vanished keys and files ---
    for (rel, key), db_unit in units_db.items():
        if (rel, key) in seen_units or db_unit["is_deleted"]:
            continue
        conn.execute(
            "UPDATE units SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (now, db_unit["id"]),
        )
        stats.deleted += 1
        # the translation of a vanished key is kept in the archive
        if db_unit["ru_text"]:
            archive(rel, key, db_unit["ru_text"])
    for rel, row in files_db.items():
        if rel not in en_data and not row["is_deleted"]:
            conn.execute("UPDATE files SET is_deleted = 1 WHERE id = ?", (row["id"],))

    # --- 7. Rows with nothing to translate, and the translation memory ---
    stats.auto_ignored += unit_ops.auto_ignore_untranslated(conn, project_id)
    tm.feed_from_project(conn, project_id)
    stats.auto_filled = tm.bulk_apply(conn, project_id)

    # --- 8. The scan history ---
    conn.execute(
        "INSERT INTO scan_history (project_id, started_at, finished_at, stats_json) VALUES (?, ?, ?, ?)",
        (project_id, started_at, datetime.now(UTC).isoformat(),
         json.dumps(stats.__dict__, ensure_ascii=False, default=str)),
    )
    conn.execute(
        "UPDATE projects SET last_opened_at = datetime('now') WHERE id = ?", (project_id,)
    )
    conn.commit()
    # The whole scan is one transaction, and by this point the journal is the size
    # of everything written. We flush it now rather than leave it to the next open.
    from pdxloc.project import checkpoint

    checkpoint(conn)
    if progress_cb:
        progress_cb(total_steps, total_steps, "done")
    return stats
