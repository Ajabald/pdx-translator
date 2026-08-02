"""Загрузка перевода из готового дерева локализации — отдельной командой.

У ESP/ESM Translator это `Перевод → Загрузка перевода из переведённого мода`
со своим окном правил. У нас до сих пор перевод затягивался только внутри
сканирования и только в пустые строки: если у ключа уже был перевод, версия с
диска молча игнорировалась (сканер лишь считал её расхождением). Поэтому не было
способа принять чужой перевод мода или свои же правки, сделанные в файлах.

Импорт идёт через `unit_ops.save_ru_text` — единую точку записи: она ведёт
историю (значит, всю пачку можно откатить одним Ctrl+Z) и пополняет память
переводов.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ck3loc.core import paradox_yaml, unit_ops
from ck3loc.core.scanner import LEGACY_MARKER, map_relpath

ProgressCb = Callable[[int, int, str], None]


@dataclass
class ImportOptions:
    """Правила приёма строк — те же, что в окне Import у EET."""

    overwrite: bool = False              # перезаписывать существующие переводы
    skip_equal_to_source: bool = True    # пропускать строки, где перевод = оригинал
    only_files: set[str] | None = None   # ограничить набором rel_path оригинала


@dataclass
class ImportReport:
    files_found: int = 0
    imported: int = 0
    unchanged: int = 0              # на диске то же, что в проекте
    skipped_existing: int = 0       # перевод уже есть, перезапись выключена
    skipped_equal: int = 0          # перевод совпадает с оригиналом
    skipped_marked: int = 0         # помечено маркером «требует перевода»
    unknown_keys: int = 0           # ключей нет в проекте — чужой или старый мод
    warnings: list[str] = field(default_factory=list)
    samples: list[tuple[str, str, str]] = field(default_factory=list)  # ключ, было, стало

    SAMPLE_LIMIT = 200

    def summary_ru(self) -> str:
        lines = [
            f"Файлов перевода найдено: {self.files_found}",
            f"Строк принято: {self.imported}",
        ]
        if self.unchanged:
            lines.append(f"Уже совпадало: {self.unchanged}")
        if self.skipped_existing:
            lines.append(f"Пропущено (перевод уже есть): {self.skipped_existing}")
        if self.skipped_equal:
            lines.append(f"Пропущено (перевод равен оригиналу): {self.skipped_equal}")
        if self.skipped_marked:
            lines.append(f"Пропущено (маркер «требует перевода»): {self.skipped_marked}")
        if self.unknown_keys:
            lines.append(f"Ключей нет в проекте: {self.unknown_keys}")
        return "\n".join(lines)


def import_translations(
    conn: sqlite3.Connection,
    project_id: int,
    tgt_dir: Path,
    options: ImportOptions | None = None,
    *,
    dry_run: bool = False,
    batch_id: str | None = None,
    progress_cb: ProgressCb | None = None,
) -> ImportReport:
    """Принять переводы из дерева `tgt_dir`.

    `dry_run` считает то же самое, но ничего не пишет — для предпросмотра:
    массовая операция без показа «что именно изменится» опасна.
    """
    options = options or ImportOptions()
    tgt_dir = Path(tgt_dir)
    if not tgt_dir.is_dir():
        raise FileNotFoundError(f"Папка перевода не найдена: {tgt_dir}")

    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(f"Проект id={project_id} не найден")
    keys = proj.keys()
    src_lang = proj["src_lang"] if "src_lang" in keys else "english"
    tgt_lang = proj["tgt_lang"] if "tgt_lang" in keys else "russian"

    files = conn.execute(
        "SELECT id, rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
        "ORDER BY rel_path", (project_id,)).fetchall()
    report = ImportReport()

    for i, f in enumerate(files):
        rel = f["rel_path"]
        if options.only_files is not None and rel not in options.only_files:
            continue
        if progress_cb:
            progress_cb(i, len(files), rel)
        path = tgt_dir / map_relpath(rel, src_lang, tgt_lang)
        if not path.is_file():
            continue
        report.files_found += 1
        lf = paradox_yaml.parse_file(path)
        report.warnings.extend(lf.warnings)
        entries = {e.key: e for e in lf.entries}     # последний побеждает, как в игре

        units = {
            u["key"]: u for u in conn.execute(
                "SELECT id, key, en_text, ru_text, status FROM units "
                "WHERE file_id = ? AND is_deleted = 0", (f["id"],))
        }
        report.unknown_keys += sum(1 for k in entries if k not in units)

        for key, entry in entries.items():
            unit = units.get(key)
            if unit is None or not entry.text:
                continue
            if LEGACY_MARKER in entry.comment_inline:
                report.skipped_marked += 1
                continue
            if options.skip_equal_to_source and entry.text == (unit["en_text"] or ""):
                report.skipped_equal += 1
                continue
            current = unit["ru_text"] or ""
            if entry.text == current:
                report.unchanged += 1
                continue
            if current and not options.overwrite:
                report.skipped_existing += 1
                continue
            report.imported += 1
            if len(report.samples) < ImportReport.SAMPLE_LIMIT:
                report.samples.append((key, current, entry.text))
            if not dry_run:
                unit_ops.save_ru_text(conn, unit["id"], entry.text,
                                      origin="import", batch_id=batch_id)

    if progress_cb:
        progress_cb(len(files), len(files), "готово")
    return report
