"""Загрузка перевода из готового дерева локализации — отдельной командой.

У ESP/ESM Translator это `Перевод → Загрузка перевода из переведённого мода`
со своим окном правил. У нас до сих пор перевод затягивался только внутри
сканирования и только в пустые строки: если у ключа уже был перевод, версия с
диска молча игнорировалась (сканер лишь считал её расхождением). Поэтому не было
способа принять чужой перевод мода или свои же правки, сделанные в файлах.

**Работа разделена на три шага, и это не украшение.**

    read_tree   — только диск: разобрать файлы перевода
    build_plan  — только сравнение: что и на что менять
    apply_plan  — только запись: одна транзакция на всю пачку

Раньше всё это делал один проход, и окно звало его три-четыре раза за импорт:
предпросмотр при открытии, предпросмотр на каждую галку, ещё раз ради числа в
вопросе «взять N строк?» и только потом по-настоящему. Между тем **галки на
разбор файлов не влияют** — они меняют правила отбора, а файлы читаются одни и
те же. Теперь дерево разбирается один раз, а переключение галки пересчитывает
только сравнение, в памяти.

Запись идёт пачкой, а не построчно, и это вторая половина той же истории. Замер
на 20 000 строк: построчно 16,7 с, пачкой 0,53 с — тридцатидвухкратная разница.
Причина не в SQL, а в `commit` на каждую строку: база живёт в WAL с
`synchronous=FULL`, то есть каждая строка стоила одного fsync. Побочный
результат важен не меньше: пачка либо применяется целиком, либо не применяется
вовсе, тогда как прежний путь при ошибке на середине оставлял половину строк
записанной.

Историю и переходы статусов пакетный путь ведёт теми же средствами, что и
ручная правка: `unit_ops.record_history` и `unit_ops.status_after_edit`.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_formats, tm, unit_ops
from pdxloc.core.models import LocEntry
from pdxloc.core.scanner import LEGACY_MARKER

ProgressCb = Callable[[int, int, str], None]


class ImportCancelled(Exception):
    """Чтение прервано пользователем — в базу ничего не ушло."""


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

    def summary(self) -> str:
        """Итог загрузки перевода из файлов мода."""
        lines = [
            fill(translate("LocImport", "Translation files found: %1"),
                 self.files_found),
            fill(translate("LocImport", "Rows taken: %1"), self.imported),
        ]
        if self.unchanged:
            lines.append(fill(translate("LocImport", "Already the same: %1"),
                              self.unchanged))
        if self.skipped_existing:
            lines.append(fill(translate(
                "LocImport", "Skipped (a translation already exists): %1"),
                self.skipped_existing))
        if self.skipped_equal:
            lines.append(fill(translate(
                "LocImport", "Skipped (translation equals the original): %1"),
                self.skipped_equal))
        if self.skipped_marked:
            lines.append(fill(translate(
                "LocImport", "Skipped (the «needs translation» marker): %1"),
                self.skipped_marked))
        if self.unknown_keys:
            lines.append(fill(translate("LocImport", "Keys absent from the project: %1"),
                 self.unknown_keys))
        return "\n".join(lines)


@dataclass(frozen=True)
class ParsedTree:
    """Разобранное дерево перевода: то, что прочитано с диска.

    Живёт в окне импорта, пока не сменили папку: правила приёма его не меняют.
    """

    tgt_dir: Path
    files: dict[str, dict[str, LocEntry]]      # rel_path оригинала -> {ключ: запись}
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Change:
    """Одна строка, которую примет импорт."""

    unit_id: int
    key: str
    en_text: str | None
    old_text: str | None
    new_text: str          # уже приведён к формату Paradox
    status: str
    prev_en_text: str | None
    change_kind: str | None


@dataclass
class ImportPlan:
    """Что произойдёт при импорте. Ничего не записано — можно показать и передумать."""

    changes: list[Change] = field(default_factory=list)
    report: ImportReport = field(default_factory=ImportReport)


def read_tree(
    tgt_dir: Path,
    rel_paths: list[str],
    src_lang: str,
    tgt_lang: str,
    *,
    fmt: loc_formats.LocFormat | None = None,
    encoding: str = "",
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ParsedTree:
    """Разобрать файлы перевода. Только чтение — база не участвует.

    `rel_paths` — пути файлов **оригинала**: имена файлов перевода получаются из
    них подстановкой языка, и брать с диска что-то сверх проекта незачем.
    """
    tgt_dir = Path(tgt_dir)
    fmt = fmt or loc_formats.get(loc_formats.DEFAULT)
    if not tgt_dir.is_dir():
        raise FileNotFoundError(fill(translate(
            "LocImport", "Translation folder not found: %1"), tgt_dir))

    files: dict[str, dict[str, LocEntry]] = {}
    warnings: list[str] = []
    for i, rel in enumerate(rel_paths):
        if should_cancel is not None and should_cancel():
            raise ImportCancelled
        if progress_cb:
            progress_cb(i, len(rel_paths), rel)
        path = tgt_dir / fmt.map_relpath(rel, src_lang, tgt_lang)
        if not path.is_file():
            continue
        lf = fmt.parse_file(path, language=tgt_lang, encoding=encoding)
        warnings.extend(lf.warnings)
        # последний побеждает, как в игре
        files[rel] = {e.key: e for e in lf.entries}

    if progress_cb:
        progress_cb(len(rel_paths), len(rel_paths), "done")
    return ParsedTree(tgt_dir=tgt_dir, files=files, warnings=warnings)


def build_plan(
    conn: sqlite3.Connection,
    project_id: int,
    tree: ParsedTree,
    options: ImportOptions | None = None,
    *,
    fmt: loc_formats.LocFormat | None = None,
) -> ImportPlan:
    """Сравнить разобранное дерево с проектом. Ничего не пишет и диска не трогает."""
    fmt = fmt or loc_formats.get(loc_formats.DEFAULT)
    options = options or ImportOptions()
    plan = ImportPlan()
    report = plan.report
    report.warnings.extend(tree.warnings)

    # Один запрос на проект вместо запроса на каждый файл: строк бывают сотни
    # тысяч, а файлов — сотни, и лишние сотни обращений к базе тут ни к чему.
    units_by_file: dict[int, dict[str, sqlite3.Row]] = {}
    for row in conn.execute(
        """SELECT u.id, u.key, u.file_id, u.en_text, u.ru_text, u.status,
                  u.prev_en_text, u.change_kind
           FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0""",
        (project_id,),
    ):
        units_by_file.setdefault(row["file_id"], {})[row["key"]] = row

    files = conn.execute(
        "SELECT id, rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
        "ORDER BY rel_path", (project_id,)).fetchall()

    for f in files:
        rel = f["rel_path"]
        if options.only_files is not None and rel not in options.only_files:
            continue
        entries = tree.files.get(rel)
        if entries is None:
            continue
        report.files_found += 1
        units = units_by_file.get(f["id"], {})
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

            # Текст приводим к формату Paradox здесь же, а не при записи: план
            # показывают человеку, и показывать надо то, что действительно ляжет
            # в базу.
            new_text = fmt.escape_value(entry.text)
            status, prev_en, change_kind = unit_ops.status_after_edit(
                unit["status"], new_text, unit["ru_text"],
                unit["prev_en_text"], unit["change_kind"])
            plan.changes.append(Change(
                unit_id=unit["id"], key=key, en_text=unit["en_text"],
                old_text=unit["ru_text"], new_text=new_text,
                status=status, prev_en_text=prev_en, change_kind=change_kind))
            report.imported += 1
            if len(report.samples) < ImportReport.SAMPLE_LIMIT:
                report.samples.append((key, current, entry.text))

    return plan


def apply_plan(
    conn: sqlite3.Connection,
    plan: ImportPlan,
    *,
    batch_id: str | None = None,
) -> ImportReport:
    """Записать план одной транзакцией.

    Либо применяется всё, либо ничего: прежний путь коммитил каждую строку
    отдельно, и ошибка на середине оставляла половину принятой — без способа
    понять, какую именно.
    """
    changes = plan.changes
    if not changes:
        return plan.report

    try:
        unit_ops.record_history(conn, [c.unit_id for c in changes],
                                origin="import", batch_id=batch_id)
        conn.executemany(
            "UPDATE units SET ru_text = ?, status = ?, prev_en_text = ?, "
            "change_kind = ?, updated_at = datetime('now') WHERE id = ?",
            [(c.new_text, c.status, c.prev_en_text, c.change_kind, c.unit_id)
             for c in changes],
        )
        # Принятое пополняет память переводов — как и при ручной правке: перевод
        # чужого мода тем и ценен, что подскажет в своём.
        tm.upsert_many(conn, [(c.en_text, c.new_text, c.key) for c in changes
                              if c.en_text and c.new_text])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    # пачка бывает на десятки тысяч строк — журнал сбрасываем сразу, как и
    # после сканирования (см. project.checkpoint)
    from pdxloc.project import checkpoint

    checkpoint(conn)
    return plan.report


def import_translations(
    conn: sqlite3.Connection,
    project_id: int,
    tgt_dir: Path,
    options: ImportOptions | None = None,
    *,
    dry_run: bool = False,
    batch_id: str | None = None,
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ImportReport:
    """Принять переводы из дерева `tgt_dir` — все три шага разом.

    `dry_run` считает то же самое, но ничего не пишет: массовая операция без
    показа «что именно изменится» опасна.
    """
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        raise ValueError(fill(translate("LocImport", "Project id=%1 not found"), project_id))
    from pdxloc.project import languages as project_languages

    langs = project_languages(conn, project_id)
    rel_paths = [r["rel_path"] for r in conn.execute(
        "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
        "ORDER BY rel_path", (project_id,))]
    from pdxloc.project import get_loc_encoding, get_loc_format

    fmt = loc_formats.get(get_loc_format(conn) or loc_formats.DEFAULT)
    tree = read_tree(tgt_dir, rel_paths, langs.src_lang, langs.tgt_lang,
                     fmt=fmt, encoding=get_loc_encoding(conn) or "",
                     progress_cb=progress_cb, should_cancel=should_cancel)
    plan = build_plan(conn, project_id, tree, options, fmt=fmt)
    if dry_run:
        return plan.report
    return apply_plan(conn, plan, batch_id=batch_id)
