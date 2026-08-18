"""Сканирование проекта: импорт/рескан деревьев локализации в БД.

Первичный импорт и рескан после обновления мода — один и тот же код:
дифф-автомат сравнивает свежий разбор EN/RU-деревьев с состоянием в БД.

Формат файлов сканер не знает — он спрашивает его у `core/loc_formats.py`:
у нынешних игр серии язык стоит в имени файла и в пути
(`english/x_l_english.yml` → `russian/x_l_russian.yml`), у старых он колонка
внутри той же строки, и путь в дереве перевода тот же самый. Всё, что зависит
от этого, идёт через `fmt.files()` и `fmt.map_relpath()`.

Соглашения самого сканера:
- Файлы с '_updated' в имени игнорируются (мусор старых скриптов пользователя).
- Маркер старых скриптов '# !!! ТРЕБУЕТ ПЕРЕВОДА' в RU и ru == en означают
  «не переведено».
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
    """(ru_text, is_translated) для записи с диска.

    Правила:
      - маркер старых скриптов -> не переведено;
      - текст отличается от оригинала -> переведено;
      - текст совпадает с оригиналом -> переведено только при первичном импорте
        и только если в файле есть хотя бы один настоящий перевод (иначе это
        просто копия исходного дерева). Совпадающий перевод — норма для имён
        собственных, «OK» и чисел.
    """
    if LEGACY_MARKER in entry.comment_inline or not entry.text:
        return entry.text, False
    if entry.text != (en_text or ""):
        return entry.text, True
    return entry.text, is_new_unit and file_has_real_translations


def _file_has_real_translations(
    en_entries: dict[str, LocEntry], ru_entries: dict[str, LocEntry]
) -> bool:
    """Есть ли в RU-файле хоть один перевод, отличающийся от оригинала."""
    for key, ru_entry in ru_entries.items():
        en_entry = en_entries.get(key)
        if (en_entry is not None and ru_entry.text
                and LEGACY_MARKER not in ru_entry.comment_inline
                and ru_entry.text != en_entry.text):
            return True
    return False


class ScanCancelled(Exception):
    """Сканирование прервано пользователем — изменения откатываются целиком."""


def _format_of(conn: sqlite3.Connection, en_root: Path) -> loc_formats.LocFormat:
    """Формат проекта: из файла проекта, а при первом скане — по дереву."""
    from pdxloc import project as project_module

    stored = project_module.get_loc_format(conn)
    if stored:
        return loc_formats.get(stored)
    format_id = loc_formats.detect(en_root)
    project_module.set_loc_format(conn, format_id)
    return loc_formats.get(format_id)


def _encodings_of(conn: sqlite3.Connection, fmt: loc_formats.LocFormat,
                  en_root: Path, ru_root: Path) -> tuple[str, str]:
    """Кодировки дерева оригинала и дерева перевода.

    Раздельно, потому что они и вправду разные: ванильная CK2 лежит в cp1252, а
    русский перевод — в cp1251. Кодировка перевода запоминается в проекте: ею
    же экспорт будет писать, когда дерева под рукой может уже не быть.
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

    # --- 1. Разбор дерева оригинала ---
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
            # Пустое значение в оригинале — почти всегда недосмотр автора мода:
            # ключ заводят заглушкой под ссылку из скрипта. Переводить нечего
            # (строка уйдёт в «игнорировано»), но молчать нельзя — иначе о
            # дефекте не узнает никто. По RU-дереву не считаем: там пустое
            # значение значит просто «ещё не переведено».
            if not e.text.strip():
                stats.empty_source_keys.append(f"{rel}: {e.key}")
            entries[e.key] = e   # последний побеждает — так делает сама CK3
        en_data[rel] = entries
        file_trailing[rel] = lf.trailing

    # --- 2. Разбор RU: пары к EN-файлам + осиротевшие RU-файлы ---
    def parse_ru_entries(path: Path, rel: str) -> dict[str, LocEntry]:
        lf = fmt.parse_file(path, language=tgt_lang, encoding=tgt_encoding)
        stats.parse_warnings.extend(lf.warnings)
        entries: dict[str, LocEntry] = {}
        for e in lf.entries:
            if e.key in entries:
                stats.duplicate_keys_ru.append(f"{rel}: {e.key}")
            entries[e.key] = e     # последний побеждает, как в самой игре
        return entries

    ru_data: dict[str, dict[str, LocEntry]] = {}   # rel_path оригинала -> key -> запись
    for rel in en_data:
        rel_tgt = fmt.map_relpath(rel, src_lang, tgt_lang)
        ru_path = ru_root / rel_tgt
        if ru_path.is_file():
            ru_data[rel] = parse_ru_entries(ru_path, rel_tgt)
            stats.files_ru += 1

    orphan_ru: dict[str, dict[str, LocEntry]] = {}  # rel_path перевода -> key -> запись
    if ru_root.is_dir():
        for p in fmt.files(ru_root, tgt_lang, skip_updated=True):
            rel_ru = p.relative_to(ru_root).as_posix()
            if fmt.map_relpath(rel_ru, tgt_lang, src_lang) in en_data:
                continue
            orphan_ru[rel_ru] = parse_ru_entries(p, rel_ru)
            stats.files_ru += 1

    # --- 3. Снимок состояния БД ---
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
        """Запомнить редакцию оригинала, если она новая для этой строки."""
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
        """Перевод ключа, которого больше нет в оригинале, — в архив."""
        if not text:
            return
        cur = conn.execute(
            "INSERT OR IGNORE INTO legacy_translations (rel_path, key, ru_text) "
            "VALUES (?, ?, ?)", (rel, key, text))
        if cur.rowcount:
            stats.archived += 1

    # --- 4. Дифф-автомат по EN-ключам ---
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
                # новый ключ. Строку из одной разметки (и пустую) переводить
                # нечего — копия оригинала в файле перевода этого не меняет; но
                # если там всё же другой текст, уважаем его как перевод.
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

            # Перевод в базе разошёлся с переводом на диске: база главнее, но
            # раньше правка с диска терялась молча, если EN тоже изменился.
            if (db_unit["ru_text"] is not None and disk_translated
                    and disk_ru != db_unit["ru_text"]):
                stats.ru_conflicts += 1
                stats.ru_conflict_list.append((rel, key, db_unit["ru_text"], disk_ru or ""))

            if db_unit["en_hash"] == new_hash:
                # EN не менялся
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

            # Оригинал изменился: запоминаем редакцию и характер правки
            record_source(db_unit["id"], e.text, new_hash, e.version)
            kind = classify_change(db_unit["en_text"] or "", e.text)
            if kind == COSMETIC:
                stats.changed_cosmetic += 1
            else:
                stats.changed_meaningful += 1

            if status == Status.IGNORED.value:
                # переводить было нечего: так и осталось — игнор сохраняем,
                # появился текст — переводить
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
                # prev_en_text не трогаем: дифф — от текста, на котором основан перевод.
                # Характер правки считаем от него же, а не от промежуточной редакции.
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
                # Подставленное автоматом устарело: сброс и повторный поиск в TM
                # (bulk_apply ниже). Машинный перевод здесь же, а не в «устарело»:
                # он сделан для прежнего текста, читать его никто не читал, и
                # оставить как есть значило бы держать перевод чужой строки под
                # видом почти готового — он ещё и уедет в мод по галке
                # «включая машинный».
                conn.execute(
                    "UPDATE units SET en_text = ?, en_hash = ?, en_version = ?, "
                    "ru_text = NULL, status = ?, is_deleted = 0, line_no = ?, "
                    "comment_before = ?, comment_inline = ?, updated_at = ? WHERE id = ?",
                    (e.text, new_hash, e.version, Status.UNTRANSLATED.value,
                     e.line_no, e.comment_before, e.comment_inline, now, db_unit["id"]),
                )
            else:   # untranslated / orphaned-ставший-EN
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

        # ключи, которых нет в оригинале: перевод в архив, строку не заводим
        for key, ru_entry in ru_entries.items():
            if key not in entries and LEGACY_MARKER not in ru_entry.comment_inline:
                archive(rel, key, ru_entry.text)

    # --- 5. Файлы перевода без пары в оригинале: только архив ---
    for rel_ru, entries in orphan_ru.items():
        stats.orphan_ru_files.append(rel_ru)
        for key, ru_entry in entries.items():
            if LEGACY_MARKER not in ru_entry.comment_inline:
                archive(rel_ru, key, ru_entry.text)

    # --- 6. Исчезнувшие ключи и файлы ---
    for (rel, key), db_unit in units_db.items():
        if (rel, key) in seen_units or db_unit["is_deleted"]:
            continue
        conn.execute(
            "UPDATE units SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (now, db_unit["id"]),
        )
        stats.deleted += 1
        # перевод исчезнувшего ключа сохраняем в архиве
        if db_unit["ru_text"]:
            archive(rel, key, db_unit["ru_text"])
    for rel, row in files_db.items():
        if rel not in en_data and not row["is_deleted"]:
            conn.execute("UPDATE files SET is_deleted = 1 WHERE id = ?", (row["id"],))

    # --- 7. Строки без переводимого текста, память переводов ---
    stats.auto_ignored += unit_ops.auto_ignore_untranslated(conn, project_id)
    tm.feed_from_project(conn, project_id)
    stats.auto_filled = tm.bulk_apply(conn, project_id)

    # --- 8. История сканирования ---
    conn.execute(
        "INSERT INTO scan_history (project_id, started_at, finished_at, stats_json) VALUES (?, ?, ?, ?)",
        (project_id, started_at, datetime.now(UTC).isoformat(),
         json.dumps(stats.__dict__, ensure_ascii=False, default=str)),
    )
    conn.execute(
        "UPDATE projects SET last_opened_at = datetime('now') WHERE id = ?", (project_id,)
    )
    conn.commit()
    # Весь скан — одна транзакция, и журнал к этому моменту размером со всё
    # записанное. Сбрасываем его сразу, а не оставляем следующему открытию.
    from pdxloc.project import checkpoint

    checkpoint(conn)
    if progress_cb:
        progress_cb(total_steps, total_steps, "done")
    return stats
