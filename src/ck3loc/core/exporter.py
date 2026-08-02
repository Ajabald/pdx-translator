"""Экспорт RU-дерева локализации в формате CK3 (BOM, l_russian:, порядок EN-файла)."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable

from ck3loc import settings
from ck3loc.core import paradox_yaml
from ck3loc.core.models import ExportOptions, ExportReport, LocEntry
from ck3loc.core.scanner import LEGACY_MARKER, map_relpath
from ck3loc.core.statuses import Status

TRANSLATED_STATUSES = (
    Status.TRANSLATED.value, Status.REVIEWED.value,
    Status.AUTO.value, Status.STALE.value, Status.CUSTOM.value,
)


def _safe_name(name: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip(" .") or "project"


def _prune_backups(project_dir: Path, keep: int = settings.BACKUP_KEEP) -> None:
    """Оставить только последние снимки: бэкап страхует запись, а не хранит историю."""
    snapshots = sorted((p for p in project_dir.iterdir() if p.is_dir()))
    for old in snapshots[:-keep] if keep > 0 else snapshots:
        shutil.rmtree(old, ignore_errors=True)


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
        raise ValueError(f"Проект id={project_id} не найден")
    root = out_root if out_root is not None else Path(proj["ru_root"])
    keys = proj.keys()
    src_lang = proj["src_lang"] if "src_lang" in keys else "english"
    tgt_lang = proj["tgt_lang"] if "tgt_lang" in keys else "russian"

    files = conn.execute(
        "SELECT * FROM files WHERE project_id = ? AND is_deleted = 0 ORDER BY rel_path",
        (project_id,),
    ).fetchall()

    report = ExportReport()
    translated_statuses = set(TRANSLATED_STATUSES)
    if not options.include_stale:
        translated_statuses.discard(Status.STALE.value)

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
        ru_rel = map_relpath(f["rel_path"], src_lang, tgt_lang)
        report.per_file.append((ru_rel, written, skipped))
        if not entries:
            continue

        trailing = f["trailing"] if "trailing" in f.keys() else ""
        text = paradox_yaml.render(tgt_lang, entries, trailing)
        target = root / ru_rel
        # не трогаем файл, если содержимое не изменилось: сохраняем даты
        # изменения и не заставляем менеджеры модов пересобирать пакет
        if target.is_file():
            try:
                if target.read_text(encoding="utf-8-sig") == text:
                    report.files_unchanged += 1
                    continue
            except (OSError, UnicodeDecodeError):
                pass
            if backup:
                backup_target(target, ru_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8-sig", newline="\n") as fh:
            fh.write(text)
        report.files_written += 1

    if snapshot is not None:
        _prune_backups(snapshot.parent)
    if progress_cb:
        progress_cb(len(files), len(files), "готово")
    return report
