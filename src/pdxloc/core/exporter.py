"""Экспорт RU-дерева локализации в формате CK3 (BOM, l_russian:, порядок EN-файла)."""
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

from pdxloc import settings
from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_formats
from pdxloc.core.models import ExportOptions, ExportReport, LocEntry
from pdxloc.core.scanner import LEGACY_MARKER
from pdxloc.core.statuses import Status

# Что считается годным для записи в мод. `Status.MACHINE` сюда не входит
# намеренно: машинный перевод никто не читал. Он добавляется только по явной
# галке — см. `ExportOptions.include_machine`.
TRANSLATED_STATUSES = (
    Status.TRANSLATED.value, Status.REVIEWED.value,
    Status.AUTO.value, Status.STALE.value, Status.CUSTOM.value,
)


def _safe_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .") or "project"


def _prune_backups(project_dir: Path, keep: int | None = None) -> None:
    """Оставить только последние снимки: бэкап страхует запись, а не хранит историю.

    Сколько именно — спрашиваем при вызове, а не в значении аргумента по
    умолчанию: то вычислялось бы один раз на импорте модуля, и правка настройки
    не действовала бы до перезапуска.
    """
    if keep is None:
        keep = settings.backup_keep()
    snapshots = sorted(p for p in project_dir.iterdir() if p.is_dir())
    for old in snapshots[:-keep] if keep > 0 else snapshots:
        shutil.rmtree(old, ignore_errors=True)


def _attach_raw(entries: list[LocEntry], fmt, target: Path,
                target_read: tuple[str, str], source: Path,
                source_read: tuple[str, str]) -> None:
    """Подставить записям исходные строки файла — по ключу.

    Двумя проходами: сперва из дерева оригинала, затем из перезаписываемого
    файла — тот новее и должен побеждать. Строка, не нашедшаяся нигде,
    останется без `raw`, и формат запишет её по своему шаблону: это новый ключ,
    взяться его прочим колонкам неоткуда.

    Каждое дерево читается **своей** кодировкой: у старого формата оригинал
    лежит в cp1252, а перевод в cp1251, и общая на двоих испортила бы чужие
    колонки молча — испорченная строка кодируется обратно без всякой ошибки.
    """
    raw: dict[str, str] = {}
    for path, (language, encoding) in ((source, source_read),
                                       (target, target_read)):
        if not path.is_file():
            continue
        try:
            loc = fmt.parse_file(path, language=language, encoding=encoding)
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        raw.update({e.key: e.raw for e in loc.entries if e.raw})
    for entry in entries:
        entry.raw = raw.get(entry.key, "")


def _write_atomically(target: Path, text: str, encoding: str = "utf-8-sig") -> None:
    """Записать файл мода так, чтобы он не мог остаться обрезанным.

    `open(target, "w")` обнуляет файл сразу, до первого байта: упади процесс
    посередине — в папке локализации останется огрызок, и **игра прочитает его
    как настоящий**. Пишем рядом и подменяем одним движением: `os.replace`
    на Windows атомарен, так что виден либо прежний файл целиком, либо новый.

    Соседний `.tmp` игре не виден — она читает только файлы локализации, — а
    прерванный экспорт оставит его мусором, который перезапишется следующей
    записью.

    `fsync` намеренно не зовём: он защищает от внезапного обесточивания, но
    стоит дорого, а файлов за один экспорт бывают сотни. От падения приложения
    (случай, который встречается) защищает и подмена.

    Концы строк: у нынешнего формата серии — LF (так пишет и сама игра), у
    старого — CRLF, как во всех его файлах; иначе правка одной строки показала
    бы в сравнении весь файл изменённым.
    """
    tmp = target.with_name(target.name + ".tmp")
    newline = "\n" if encoding.startswith("utf") else "\r\n"
    with open(tmp, "w", encoding=encoding, newline=newline,
              errors="replace") as fh:
        fh.write(text)
    os.replace(tmp, target)


def export_project(
    conn: sqlite3.Connection,
    project_id: int,
    options: ExportOptions,
    *,
    out_root: Path | None = None,
    backup: bool = True,
    backup_root: Path | None = None,
    progress_cb: Callable[[int, int, str], None] | None = None,
) -> ExportReport:
    """Записать RU-файлы. out_root по умолчанию — ru_root проекта.

    Прежние версии перезаписываемых файлов складываются в отдельное дерево
    (`settings.backups_dir()`): рядом с локализацией их держать нельзя — игра
    читает из той папки все `*.yml` и загрузит копию наравне с оригиналом.
    """
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(fill(translate("Exporter", "Project id=%1 not found"), project_id))
    root = out_root if out_root is not None else Path(proj["ru_root"])
    from pdxloc.project import languages as project_languages

    langs = project_languages(conn, project_id)
    src_lang, tgt_lang = langs.src_lang, langs.tgt_lang

    from pdxloc.project import (get_loc_encoding, get_loc_format,
                                get_source_encoding)

    fmt = loc_formats.get(get_loc_format(conn) or loc_formats.DEFAULT)
    encoding = get_loc_encoding(conn) or fmt.encodings[0]
    src_encoding = get_source_encoding(conn) or encoding
    # Формату с несколькими кодировками её надо знать заранее: от неё зависит,
    # переживут ли запись чужие колонки строки (см. `paradox_csv.render`).
    render_options = {} if len(fmt.encodings) == 1 else {"encoding": encoding}

    files = conn.execute(
        "SELECT * FROM files WHERE project_id = ? AND is_deleted = 0 ORDER BY rel_path",
        (project_id,),
    ).fetchall()

    report = ExportReport()
    translated_statuses = set(TRANSLATED_STATUSES)
    if not options.include_stale:
        translated_statuses.discard(Status.STALE.value)
    if options.include_machine:
        translated_statuses.add(Status.MACHINE.value)

    snapshot: Path | None = None

    def backup_target(target: Path, ru_rel: str) -> None:
        """Отложить прежнюю версию файла. Папку заводим только при первой копии."""
        nonlocal snapshot
        if snapshot is None:
            base = Path(backup_root) if backup_root is not None else settings.backups_dir()
            project_dir = base / _safe_name(proj["name"])
            project_dir.mkdir(parents=True, exist_ok=True)
            snapshot = project_dir / datetime.now().strftime("%Y-%m-%d_%H%M%S")
            snapshot.mkdir(exist_ok=True)
            report.backup_dir = str(snapshot)
        copy = snapshot / ru_rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, copy)

    for i, f in enumerate(files):
        if progress_cb:
            progress_cb(i, len(files), f["rel_path"])
        units = conn.execute(
            "SELECT * FROM units WHERE file_id = ? AND is_deleted = 0 ORDER BY line_no, key",
            (f["id"],),
        ).fetchall()

        entries: list[LocEntry] = []
        written = skipped = 0
        for u in units:
            has_ru = u["ru_text"] is not None and u["status"] in translated_statuses
            inline = ""
            if has_ru:
                text = u["ru_text"]
            elif options.mode == "all_fallback_en":
                text = u["en_text"] or ""
                report.keys_fallback_en += 1
                # помечаем непереведённое: при следующем сканировании эта строка
                # снова опознается как требующая перевода, а не как готовая
                inline = f"# !!! {LEGACY_MARKER}"
            else:
                skipped += 1
                continue
            written += 1
            entries.append(LocEntry(
                key=u["key"],
                version=u["en_version"],
                text=text,
                comment_before=u["comment_before"],
                comment_inline=inline,
            ))

        report.keys_written += written
        report.keys_skipped += skipped
        ru_rel = fmt.map_relpath(f["rel_path"], src_lang, tgt_lang)
        report.per_file.append((ru_rel, written, skipped))
        if not entries:
            continue

        target = root / ru_rel
        if not fmt.language_in_path:
            # Формат старых игр: в строке рядом с переводом стоят французская,
            # немецкая и испанская колонки, маркер `x` и хвостовой комментарий.
            # В базе их нет — она хранит только пару «оригинал → перевод», —
            # поэтому исходные строки берём с диска: сперва из того файла,
            # который перезаписываем, а если его нет, из дерева оригинала.
            _attach_raw(entries, fmt, target, (tgt_lang, encoding),
                        Path(proj["en_root"]) / f["rel_path"],
                        (src_lang, src_encoding))

        trailing = f["trailing"] if "trailing" in f.keys() else ""
        text = fmt.render(tgt_lang, entries, trailing, **render_options)
        # не трогаем файл, если содержимое не изменилось: сохраняем даты
        # изменения и не заставляем менеджеры модов пересобирать пакет
        if target.is_file():
            try:
                if target.read_text(encoding=encoding) == text:
                    report.files_unchanged += 1
                    continue
            except (OSError, UnicodeDecodeError):
                pass
            if backup:
                backup_target(target, ru_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_atomically(target, text, encoding)
        report.files_written += 1

    if snapshot is not None:
        _prune_backups(snapshot.parent)
    if progress_cb:
        progress_cb(len(files), len(files), "done")
    return report
