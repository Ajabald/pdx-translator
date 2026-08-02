"""Сканирование проекта: импорт/рескан деревьев локализации в БД.

Первичный импорт и рескан после обновления мода — один и тот же код:
дифф-автомат сравнивает свежий разбор EN/RU-деревьев с состоянием в БД.

Соглашения:
- EN-файлы: *.yml с подстрокой '_l_english' в имени (суффикс бывает в середине,
  например agot_modifiers_l_english_BLA.yml).
- RU-путь = замена '_l_english' -> '_l_russian' в имени файла; каталоги зеркальны.
- Файлы с '_updated' в имени игнорируются (мусор старых скриптов пользователя).
- Маркер старых скриптов '# !!! ТРЕБУЕТ ПЕРЕВОДА' в RU и ru == en означают
  «не переведено».
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ck3loc.core import paradox_yaml, tm, unit_ops
from ck3loc.core.progress import throttled
from ck3loc.core.models import LocEntry, ScanStats
from ck3loc.core.statuses import Status
from ck3loc.core.textdiff import COSMETIC, classify_change
from ck3loc.core.unit_ops import is_markup_only

LEGACY_MARKER = "ТРЕБУЕТ ПЕРЕВОДА"

ProgressCb = Callable[[int, int, str], None]


def lang_tag(language: str) -> str:
    """Метка языка в имени файла: english -> _l_english."""
    return f"_l_{language}"


def map_relpath(rel_posix: str, from_lang: str, to_lang: str) -> str:
    """Путь того же файла в дереве другого языка.

    Меняется только имя файла (метка языка бывает и в середине:
    agot_modifiers_l_english_BLA.yml), каталоги в деревьях зеркальны.
    """
    parts = rel_posix.rsplit("/", 1)
    name = parts[-1].replace(lang_tag(from_lang), lang_tag(to_lang))
    return "/".join(parts[:-1] + [name]) if len(parts) > 1 else name


def en_to_ru_relpath(rel_posix: str) -> str:
    return map_relpath(rel_posix, "english", "russian")


def ru_to_en_relpath(rel_posix: str) -> str:
    return map_relpath(rel_posix, "russian", "english")


def _list_loc_files(root: Path, tag: str, *, skip_updated: bool = False) -> list[Path]:
    """Файлы локализации с меткой языка в имени.

    skip_updated отсеивает мусор старых скриптов пользователя (*_updated.yml).
    Применяется только к дереву перевода: в исходном дереве такого мусора не
    бывает, а имя вроде mod_updated_events_l_english.yml вполне легально.
    """
    return sorted(
        p for p in root.rglob("*.yml")
        if tag in p.name and not (skip_updated and "_updated" in p.name)
    )


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


def scan_project(
    conn: sqlite3.Connection,
    project_id: int,
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ScanStats:
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(f"Проект id={project_id} не найден")
    en_root = Path(proj["en_root"])
    ru_root = Path(proj["ru_root"])
    src_lang = proj["src_lang"] if "src_lang" in proj.keys() else "english"
    tgt_lang = proj["tgt_lang"] if "tgt_lang" in proj.keys() else "russian"
    if not en_root.is_dir():
        raise FileNotFoundError(f"Папка оригинала не найдена: {en_root}")

    stats = ScanStats()
    started_at = datetime.now(timezone.utc).isoformat()

    # --- 1. Разбор дерева оригинала ---
    en_files = _list_loc_files(en_root, lang_tag(src_lang))
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
        lf = paradox_yaml.parse_file(p)
        stats.parse_warnings.extend(lf.warnings)
        entries: dict[str, LocEntry] = {}
        for e in lf.entries:
            if e.key in entries:
                stats.duplicate_keys.append(f"{rel}: {e.key}")
            entries[e.key] = e   # последний побеждает — так делает сама CK3
        en_data[rel] = entries
        file_trailing[rel] = lf.trailing

    # --- 2. Разбор RU: пары к EN-файлам + осиротевшие RU-файлы ---
    def parse_ru_entries(path: Path, rel: str) -> dict[str, LocEntry]:
        lf = paradox_yaml.parse_file(path)
        stats.parse_warnings.extend(lf.warnings)
        entries: dict[str, LocEntry] = {}
        for e in lf.entries:
            if e.key in entries:
                stats.duplicate_keys_ru.append(f"{rel}: {e.key}")
            entries[e.key] = e     # последний побеждает, как в самой игре
        return entries

    ru_data: dict[str, dict[str, LocEntry]] = {}   # rel_path оригинала -> key -> запись
    for rel in en_data:
        rel_tgt = map_relpath(rel, src_lang, tgt_lang)
        ru_path = ru_root / rel_tgt
        if ru_path.is_file():
            ru_data[rel] = parse_ru_entries(ru_path, rel_tgt)
            stats.files_ru += 1

    orphan_ru: dict[str, dict[str, LocEntry]] = {}  # rel_path перевода -> key -> запись
    if ru_root.is_dir():
        for p in _list_loc_files(ru_root, lang_tag(tgt_lang), skip_updated=True):
            rel_ru = p.relative_to(ru_root).as_posix()
            if map_relpath(rel_ru, tgt_lang, src_lang) in en_data:
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

    now = datetime.now(timezone.utc).isoformat()

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
                # новый ключ. Строка из одной разметки переводить нечего —
                # копия оригинала в файле перевода этого не меняет; но если
                # там всё же другой текст, уважаем его как перевод.
                if is_markup_only(e.text) and (not disk_translated or disk_ru == e.text):
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
                # была строка-тег: осталась ей — игнор сохраняем, появился текст — переводить
                if is_markup_only(e.text):
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
            elif status == Status.AUTO.value:
                # авто-подстановка устарела: сброс и повторный поиск в TM (bulk_apply ниже)
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
        (project_id, started_at, datetime.now(timezone.utc).isoformat(),
         json.dumps(stats.__dict__, ensure_ascii=False, default=str)),
    )
    conn.execute(
        "UPDATE projects SET last_opened_at = datetime('now') WHERE id = ?", (project_id,)
    )
    conn.commit()
    if progress_cb:
        progress_cb(total_steps, total_steps, "готово")
    return stats
