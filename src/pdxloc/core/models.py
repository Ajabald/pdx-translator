"""Общие dataclass-модели ядра (без Qt)."""
from __future__ import annotations

from dataclasses import dataclass, field

from pdxloc.core.i18n import fill, translate


@dataclass
class LocEntry:
    """Одна запись файла локализации. text — сырой текст между кавычками, эскейпы не раскрыты."""
    key: str
    version: str          # цифры после ':', '' если нет
    text: str
    comment_before: str = ""   # сырые строки (комментарии/пустые) над записью, включая \n на концах строк
    comment_inline: str = ""   # '# …' после закрывающей кавычки, '' если нет
    line_no: int = 0           # порядковый номер записи в файле (0..n-1)
    # Исходная строка файла целиком — нужна форматам, которые пишут подменой
    # одного куска, а не пересборкой записи. В CSV старых игр в строке рядом с
    # переводом стоят ещё французская, немецкая и испанская колонки, маркер `x`
    # и хвостовой комментарий; собери мы строку заново — всё это потерялось бы.
    # У формата `.yml` поле пустое: там запись пересобирается целиком.
    raw: str = ""


@dataclass
class LocFile:
    language: str              # 'english' / 'russian' из заголовка l_xxx:
    entries: list[LocEntry] = field(default_factory=list)
    trailing: str = ""         # комментарии/пустые строки после последней записи
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScanStats:
    files_en: int = 0
    files_ru: int = 0
    new: int = 0
    unchanged: int = 0
    stale: int = 0
    changed_cosmetic: int = 0     # правка оформления: пунктуация, регистр, пробелы
    changed_meaningful: int = 0   # изменился текст или разметка
    deleted: int = 0
    restored: int = 0
    archived: int = 0            # переводы ключей, исчезнувших из оригинала
    auto_filled: int = 0
    auto_ignored: int = 0
    ru_conflicts: int = 0
    duplicate_keys: list[str] = field(default_factory=list)      # 'file.yml: key'
    duplicate_keys_ru: list[str] = field(default_factory=list)   # то же для дерева перевода
    empty_source_keys: list[str] = field(default_factory=list)   # пустое значение в оригинале
    orphan_ru_files: list[str] = field(default_factory=list)     # файлы перевода без пары
    parse_warnings: list[str] = field(default_factory=list)
    # (файл, ключ, перевод в базе, перевод на диске) — база главнее
    ru_conflict_list: list[tuple[str, str, str, str]] = field(default_factory=list)

    def summary(self) -> str:
        """Сводка сканирования одним текстом — для окна итогов и --scan-cli."""
        lines = [
            fill(translate("ScanStats", "EN files: %1, RU: %2"),
                 self.files_en, self.files_ru),
            fill(translate("ScanStats", "New keys: %1"), self.new),
            fill(translate("ScanStats", "Unchanged: %1"), self.unchanged),
            fill(translate("ScanStats",
                           "The original changed: %1 (meaningful %2, cosmetic %3)"),
                 self.stale, self.changed_meaningful, self.changed_cosmetic),
            fill(translate("ScanStats", "Deleted from EN: %1"), self.deleted),
            fill(translate("ScanStats", "Restored: %1"), self.restored),
            fill(translate("ScanStats",
                           "Moved to the archive (absent from the original): %1"),
                 self.archived),
            fill(translate("ScanStats", "Filled from translation memory: %1"),
                 self.auto_filled),
            fill(translate("ScanStats",
                           "Ignored automatically (nothing to translate): %1"),
                 self.auto_ignored),
            fill(translate("ScanStats", "RU conflicts (the database wins): %1"),
                 self.ru_conflicts),
        ]
        if self.duplicate_keys:
            lines.append(fill(translate("ScanStats", "Duplicate keys (original): %1"),
                              len(self.duplicate_keys)))
        if self.duplicate_keys_ru:
            lines.append(fill(translate("ScanStats", "Duplicate keys (translation): %1"),
                              len(self.duplicate_keys_ru)))
        if self.empty_source_keys:
            lines.append(fill(translate("ScanStats", "Keys with an empty original: %1"),
                              len(self.empty_source_keys)))
        if self.parse_warnings:
            lines.append(fill(translate("ScanStats", "Parser warnings: %1"),
                              len(self.parse_warnings)))
        return "\n".join(lines)


@dataclass
class TmHit:
    ru_text: str
    source: str                  # 'user' | 'import' | 'game' | 'project-export'
    origin: str | None           # откуда пришёл вариант: «Проект» или имя базы
    key: str | None
    uses: int
    updated_at: str
    id: int = 0                  # запись памяти; отрицательный = из подключённой базы
    editable: bool = False       # правка возможна только для памяти проекта
    score: float = 1.0           # сходство оригинала: 1.0 — точное совпадение
    en_text: str = ""            # оригинал записи — показывать при неточном совпадении
    prio: int = 0                # приоритет источника, как в tm_all


@dataclass
class Issue:
    unit_id: int
    key: str
    file_rel_path: str
    code: str
    severity: str              # 'error' | 'warning'
    message: str


@dataclass
class ExportOptions:
    mode: str = "translated_only"   # 'translated_only' | 'all_fallback_en'
    include_stale: bool = True
    # Машинный перевод в мод по умолчанию не уходит: его никто не читал, и в
    # игре он способен соврать по смыслу, сломать тултип или потерять иконку.
    # Выпускать его наружу — осознанное решение, а не умолчание.
    include_machine: bool = False


@dataclass
class ExportReport:
    files_written: int = 0
    files_unchanged: int = 0
    keys_written: int = 0
    keys_skipped: int = 0
    keys_fallback_en: int = 0
    per_file: list[tuple[str, int, int]] = field(default_factory=list)  # (ru_rel_path, written, skipped)
    backup_dir: str | None = None   # куда сложены прежние версии перезаписанных файлов
