"""Общие dataclass-модели ядра (без Qt)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LocEntry:
    """Одна запись файла локализации. text — сырой текст между кавычками, эскейпы не раскрыты."""
    key: str
    version: str          # цифры после ':', '' если нет
    text: str
    comment_before: str = ""   # сырые строки (комментарии/пустые) над записью, включая \n на концах строк
    comment_inline: str = ""   # '# …' после закрывающей кавычки, '' если нет
    line_no: int = 0           # порядковый номер записи в файле (0..n-1)


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
    orphan_ru_files: list[str] = field(default_factory=list)     # файлы перевода без пары
    parse_warnings: list[str] = field(default_factory=list)
    # (файл, ключ, перевод в базе, перевод на диске) — база главнее
    ru_conflict_list: list[tuple[str, str, str, str]] = field(default_factory=list)

    def summary_ru(self) -> str:
        lines = [
            f"Файлов EN: {self.files_en}, RU: {self.files_ru}",
            f"Новых ключей: {self.new}",
            f"Без изменений: {self.unchanged}",
            f"Оригинал изменился: {self.stale} "
            f"(смысловых {self.changed_meaningful}, косметических {self.changed_cosmetic})",
            f"Удалено из EN: {self.deleted}",
            f"Восстановлено: {self.restored}",
            f"Перенесено в архив (нет в оригинале): {self.archived}",
            f"Заполнено из памяти переводов: {self.auto_filled}",
            f"Игнорировано автоматически (только теги): {self.auto_ignored}",
            f"Конфликтов RU (БД главнее): {self.ru_conflicts}",
        ]
        if self.duplicate_keys:
            lines.append(f"Дубликатов ключей (оригинал): {len(self.duplicate_keys)}")
        if self.duplicate_keys_ru:
            lines.append(f"Дубликатов ключей (перевод): {len(self.duplicate_keys_ru)}")
        if self.parse_warnings:
            lines.append(f"Предупреждений парсера: {len(self.parse_warnings)}")
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


@dataclass
class ExportReport:
    files_written: int = 0
    files_unchanged: int = 0
    keys_written: int = 0
    keys_skipped: int = 0
    keys_fallback_en: int = 0
    per_file: list[tuple[str, int, int]] = field(default_factory=list)  # (ru_rel_path, written, skipped)
    backup_dir: str | None = None   # куда сложены прежние версии перезаписанных файлов
