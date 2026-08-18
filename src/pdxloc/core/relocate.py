"""Смена папки оригинала у существующего проекта.

`en_root` задавался при создании проекта и больше нигде не редактировался, а
папка не вечная: мод скачали заново с Nexus в другое место, библиотеку Steam
перенесли на другой диск, проект передали другому человеку. Раньше выход был
один — править путь руками в SQLite.

Опасность операции в том, что пути файлов в базе относительные: файл, которого
в новой папке нет, на ближайшем сканировании станет удалённым, а его переводы
уедут в архив. Поэтому здесь только считают совпадения — окно показывает их
до нажатия кнопки, а записывает путь отдельный вызов.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pdxloc.core.i18n import fill, translate
from pdxloc.core.paradox_yaml import lang_tag
from pdxloc.core import loc_formats
from pdxloc.core.tm_import import language_dirs

# Насколько глубоко ищем папку языка внутри выбранной: путь до
# localization/replace/english — это три уровня.
MAX_DEPTH = 3


@dataclass
class RootPreview:
    """Что случится, если сделать выбранную папку папкой оригинала."""

    chosen: Path                      # что выбрал пользователь
    root: Path | None = None          # что будет записано (бывает подпапкой chosen)
    matched: list[str] = field(default_factory=list)   # файлы базы, найденные в папке
    missing: list[str] = field(default_factory=list)   # файлы базы, которых там нет
    added: list[str] = field(default_factory=list)     # файлы папки, которых нет в базе
    units_missing: int = 0            # строк в пропавших файлах
    translated_missing: int = 0       # из них с переводом — уедут в архив
    known_files: int = 0              # сколько файлов оригинала знает база
    candidates: list[tuple[Path, int]] = field(default_factory=list)
    error: str | None = None

    @property
    def usable(self) -> bool:
        """Можно ли записать этот путь."""
        return self.error is None and self.root is not None

    @property
    def risky(self) -> bool:
        """Совпал не весь набор — стоит переспросить перед записью."""
        return bool(self.missing)

    def summary(self) -> str:
        """Что случится со строками проекта, если сменить папку."""
        if self.error:
            return self.error
        lines = [fill(translate("Relocate", "Folder: %1"), self.root)]
        if self.root is not None and Path(self.root) != Path(self.chosen):
            lines.append(fill(translate(
                "Relocate", "%1 was chosen, but the localization files lie in "
                            "%2 — that is what will be recorded."),
                self.chosen, self.root))
        lines.append(
            fill(translate("Relocate",
                           "Files matched: %1 out of the %2 the database knows."),
                 len(self.matched), self.known_files))
        if self.missing:
            tail = (fill(translate(
                "Relocate",
                ", of them %1 with a translation will go to the archive."),
                self.translated_missing) if self.translated_missing else ".")
            lines.append(
                fill(translate("Relocate", "Files not found: %1 — %2"),
                     len(self.missing),
                     fill(translate("Relocate", "%1 rows will become deleted"),
                          self.units_missing))
                + tail)
            lines += [f"  {rel}" for rel in self.missing[:20]]
            if len(self.missing) > 20:
                lines.append(fill(translate("Relocate", "  … and %1 more"),
                                  len(self.missing) - 20))
        if self.added:
            lines.append(fill(translate(
                "Relocate",
                "New files: %1 — rows from them appear on the next scan."),
                len(self.added)))
            lines += [f"  {rel}" for rel in self.added[:20]]
            if len(self.added) > 20:
                lines.append(fill(translate("Relocate", "  … and %1 more"),
                                  len(self.added) - 20))
        if not self.matched:
            lines.append(translate(
                "Relocate",
                "Not a single database file was found in this folder. Looks "
                "like another mod's folder was chosen: after the change the "
                "whole translation goes to the archive."))
        elif not self.missing and not self.added:
            lines.append(translate(
                "Relocate",
                "The file set matches completely — the translation is safe."))
        lines.append("")
        lines.append(translate(
            "Relocate",
            "After the folder change a scan (F5) is needed: it re-reads the "
            "files and shows what changed in the original."))
        return "\n".join(lines)


def project_row(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise ValueError(fill(translate("Relocate", "Project id=%1 not found"), project_id))
    return row


def known_rel_paths(conn: sqlite3.Connection, project_id: int) -> list[str]:
    """Файлы оригинала, которые база считает живыми."""
    return [
        r["rel_path"] for r in conn.execute(
            "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0 "
            "ORDER BY rel_path", (project_id,))
    ]


def _disk_rel_paths(root: Path, src_lang: str) -> list[str]:
    return sorted(
        p.relative_to(root).as_posix()
        for p in loc_formats.get(loc_formats.detect(root)).files(root, src_lang)
    )


def _match(known: list[str], on_disk: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Сопоставить наборы путей без учёта регистра (Windows его не различает)."""
    disk_by_lower = {rel.lower(): rel for rel in on_disk}
    matched, missing = [], []
    for rel in known:
        (matched if rel.lower() in disk_by_lower else missing).append(rel)
    known_lower = {rel.lower() for rel in known}
    added = [rel for rel in on_disk if rel.lower() not in known_lower]
    return matched, missing, added


def candidate_roots(chosen: Path, src_lang: str) -> list[Path]:
    """Сама выбранная папка и все папки языка внутри неё.

    Пользователь показывает то папку мода целиком, то localization, то нужную
    папку языка. Выбирать за него молча нельзя, поэтому возвращаем все, а окно
    объясняет, почему взята не та, которую ткнули.
    """
    chosen = Path(chosen)
    if not chosen.is_dir():
        return []
    roots: list[Path] = [chosen]
    seen = {chosen.resolve()}
    for path in language_dirs(chosen, src_lang, max_depth=MAX_DEPTH):
        if path.resolve() not in seen:
            seen.add(path.resolve())
            roots.append(path)
    return roots


def preview_root_change(
    conn: sqlite3.Connection, project_id: int, chosen: Path | str,
) -> RootPreview:
    """Посчитать последствия смены папки оригинала, ничего не меняя."""
    chosen = Path(str(chosen).strip())
    proj = project_row(conn, project_id)
    src_lang = proj["src_lang"] if "src_lang" in proj.keys() else "english"
    known = known_rel_paths(conn, project_id)
    preview = RootPreview(chosen=chosen, known_files=len(known))

    if not str(chosen) or not chosen.is_dir():
        preview.error = fill(
            translate("Relocate", "Folder not found: %1"), chosen)
        return preview

    # Лучшая папка — та, где нашлось больше всего знакомых базе файлов. При
    # равенстве побеждает первая: сама выбранная, а не подпапка.
    scored: list[tuple[Path, int, list[str]]] = []
    for root in candidate_roots(chosen, src_lang):
        on_disk = _disk_rel_paths(root, src_lang)
        matched, _, _ = _match(known, on_disk)
        scored.append((root, len(matched), on_disk))
    preview.candidates = [(root, count) for root, count, _ in scored]

    best = max(scored, key=lambda item: item[1], default=None)
    if best is None or (best[1] == 0 and not any(item[2] for item in scored)):
        preview.error = fill(translate(
            "Relocate", "The folder has no localization files *%1*.yml:\n%2"),
            lang_tag(src_lang), chosen)
        return preview
    if best[1] == 0:
        # знакомых файлов нет, но файлы локализации есть — берём первую папку,
        # где они вообще лежат, и предупреждаем в сводке
        best = next(item for item in scored if item[2])

    root, _, on_disk = best
    preview.root = root
    preview.matched, preview.missing, preview.added = _match(known, on_disk)
    if preview.missing:
        marks = ",".join("?" * len(preview.missing))
        row = conn.execute(
            f"""SELECT COUNT(*) AS total,
                       COUNT(u.ru_text) AS translated
                  FROM units u JOIN files f ON f.id = u.file_id
                 WHERE f.project_id = ? AND u.is_deleted = 0
                       AND f.rel_path IN ({marks})""",
            (project_id, *preview.missing),
        ).fetchone()
        preview.units_missing = row["total"]
        preview.translated_missing = row["translated"]
    return preview


@dataclass
class LanguagePreview:
    """Последствия смены языка папки, посчитанные до записи.

    Смена `src_lang` опаснее, чем кажется: сканер ищет файлы по метке
    `_l_<язык>` в имени, и после смены он попросту не найдёт ни одного — все
    строки станут удалёнными, а переводы уедут в архив. То же, что при ошибке
    в пути, только заметить труднее: папка-то на месте.
    """

    src_lang: str
    tgt_lang: str
    known_files: int = 0
    found: int = 0            # файлов оригинала с новой меткой языка
    units_missing: int = 0
    translated_missing: int = 0
    scan_needed: bool = False       # менялось то, что читает сканер

    @property
    def risky(self) -> bool:
        return self.scan_needed and self.found < self.known_files

    def summary(self) -> str:
        if not self.scan_needed:
            return translate(
                "Relocate",
                "Only the text language changes — files and rows are not "
                "affected. Machine translation, memory database naming and "
                "language-specific checks will use the new value.")
        lines = [fill(translate(
            "Relocate", "Files with the label _l_%1 in the original folder: "
                        "%2 of the %3 the database knows."),
            self.src_lang, self.found, self.known_files)]
        if self.found == 0:
            lines.append(translate(
                "Relocate",
                "Not a single file was found. After the change the scan will "
                "consider every row deleted and the translations will go to "
                "the archive."))
        elif self.found < self.known_files:
            lines.append(fill(translate(
                "Relocate",
                "%1 rows will become deleted, of them %2 with a translation."),
                self.units_missing, self.translated_missing))
        lines.append("")
        lines.append(translate(
            "Relocate",
            "After the change a scan (F5) is needed: it re-reads the files "
            "under the new names."))
        return "\n".join(lines)


def preview_language_change(
    conn: sqlite3.Connection,
    project_id: int,
    src_lang: str,
    tgt_lang: str,
) -> LanguagePreview:
    """Посчитать последствия смены языков папок, ничего не меняя."""
    current = project_row(conn, project_id)
    known = known_rel_paths(conn, project_id)
    preview = LanguagePreview(src_lang=src_lang, tgt_lang=tgt_lang,
                              known_files=len(known))
    keys = current.keys()
    was_src = current["src_lang"] if "src_lang" in keys else "english"
    was_tgt = current["tgt_lang"] if "tgt_lang" in keys else "russian"
    preview.scan_needed = (src_lang != was_src) or (tgt_lang != was_tgt)
    if not preview.scan_needed:
        return preview

    root = Path(current["en_root"])
    if root.is_dir():
        on_disk = _disk_rel_paths(root, src_lang)
        matched, missing, _ = _match(known, on_disk)
        preview.found = len(matched)
        if missing:
            marks = ",".join("?" * len(missing))
            row = conn.execute(
                f"""SELECT COUNT(*) AS total, COUNT(u.ru_text) AS translated
                      FROM units u JOIN files f ON f.id = u.file_id
                     WHERE f.project_id = ? AND u.is_deleted = 0
                           AND f.rel_path IN ({marks})""",
                (project_id, *missing)).fetchone()
            preview.units_missing = row["total"]
            preview.translated_missing = row["translated"]
    return preview


def get_en_root(conn: sqlite3.Connection, project_id: int) -> Path:
    return Path(project_row(conn, project_id)["en_root"])


def set_en_root(conn: sqlite3.Connection, project_id: int, root: Path | str) -> Path:
    """Записать новую папку оригинала. Строки не трогаются — их разберёт скан."""
    root = Path(root)
    conn.execute(
        "UPDATE projects SET en_root = ? WHERE id = ?", (str(root), project_id))
    conn.commit()
    return root
