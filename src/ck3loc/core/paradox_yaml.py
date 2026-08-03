"""Парсер/писатель формата локализации Paradox (CK3).

Это НЕ настоящий YAML: стандартные yaml-библиотеки на нём падают.
Формат:
    l_english:                       <- заголовок, первая строка
     key_name:0 "text"               <- запись; номер версии после ':' опционален
    #comment                         <- комментарий; бывает и хвостовой после кавычки

Файлы читаются и пишутся в UTF-8 с BOM (encoding='utf-8-sig') — CK3 молча
игнорирует файлы без BOM.

Текст записей хранится «сырым» (между кавычками, эскейпы \" и \n не раскрыты),
чтобы хеши и сравнение версий были стабильны. unescape() — только для
отображения и QA-подсчётов.

Известное ограничение: хвостовой комментарий, содержащий символ '"',
распарсится неверно (регекс жадный). В реальных данных таких нет.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ck3loc.core.models import LocEntry, LocFile

# Ключ — всё до двоеточия, кроме пробелов, кавычки и решётки. Перечислять
# разрешённые символы оказалось нельзя: в ванильной локализации CK3 есть ключи
# с апострофом (b_mansa'l-kharaz, b_ka'abir), и они молча терялись — строка не
# опознавалась как запись, а при записи перевода в мод исчезла бы из файла.
KEY = r'[^\s:"#]+'
ENTRY_RE = re.compile(rf'^\s*({KEY}):(\d*)\s*"(.*)"\s*(#.*)?$')
# Строка с пропущенной закрывающей кавычкой (реальные дефекты в файлах модов):
# подбираем текст до конца строки, предупреждаем; экспорт допишет кавычку.
ENTRY_NOCLOSE_RE = re.compile(rf'^\s*({KEY}):(\d*)\s*"(.*)$')
HEADER_RE = re.compile(r'^\s*l_([a-z_]+):\s*$')
COMMENT_RE = re.compile(r'^\s*#')


def parse_text(text: str, *, source_name: str = "?") -> LocFile:
    """Разобрать содержимое файла локализации (без BOM — срезается при чтении)."""
    language = ""
    entries: list[LocEntry] = []
    warnings: list[str] = []
    pending_comments: list[str] = []   # строки над следующей записью
    header_seen = False
    missing_header: str | None = None

    for i, line in enumerate(text.splitlines()):
        if not header_seen:
            m = HEADER_RE.match(line)
            if m:
                language = m.group(1)
                header_seen = True
                continue
            if not line.strip():
                continue
            # Заголовка нет. Ругаемся не сразу: в ванильной локализации есть
            # файлы, целиком закомментированные редактором Paradox, — там
            # заголовка нет и записей тоже, ругаться не на что. Решаем в конце,
            # когда видно, нашлись ли записи.
            missing_header = f"{source_name}:{i + 1}: ожидался заголовок l_*:, найдено: {line.strip()!r}"
            header_seen = True   # дальше парсим как обычно
            # строка может оказаться записью — падаем в общий разбор

        m = ENTRY_RE.match(line)
        if m:
            key, version, value, inline = m.group(1), m.group(2), m.group(3), m.group(4) or ""
            entries.append(LocEntry(
                key=key,
                version=version,
                text=value,
                comment_before="".join(pending_comments),
                comment_inline=inline.strip(),
                line_no=len(entries),
            ))
            pending_comments = []
            continue

        if not line.strip() or COMMENT_RE.match(line):
            pending_comments.append(line + "\n")
            continue

        m = ENTRY_NOCLOSE_RE.match(line)
        if m:
            key, version, value = m.group(1), m.group(2), m.group(3).rstrip()
            entries.append(LocEntry(
                key=key,
                version=version,
                text=value,
                comment_before="".join(pending_comments),
                comment_inline="",
                line_no=len(entries),
            ))
            pending_comments = []
            warnings.append(f"{source_name}:{i + 1}: нет закрывающей кавычки у ключа {key!r} — текст взят до конца строки")
            continue

        warnings.append(f"{source_name}:{i + 1}: нераспознанная строка: {line.strip()!r}")

    if missing_header is not None and entries:
        warnings.insert(0, missing_header)

    return LocFile(
        language=language,
        entries=entries,
        trailing="".join(pending_comments),
        warnings=warnings,
    )


def parse_file(path: Path) -> LocFile:
    text = path.read_text(encoding="utf-8-sig")
    return parse_text(text, source_name=path.name)


_REAL_NEWLINE = re.compile(r"\r\n|[\r\n]")


def escape_value(text: str) -> str:
    """Привести значение к одной строке.

    В формате Paradox перенос внутри текста записывается двумя символами
    (обратный слэш и «n»); настоящий перевод строки разрывает запись пополам, и
    файл становится битым: первая половина остаётся без закрывающей кавычки, а
    вторая перестаёт быть записью. Попасть туда он может легко — достаточно
    нажать Enter в поле перевода или вставить текст из мессенджера.

    Кавычки при этом НЕ трогаем: игра читает значение до последней кавычки в
    строке, и голая кавычка внутри текста — норма (в ванильной локализации CK3
    таких записей 8413 против 89 с экранированной).
    """
    return _REAL_NEWLINE.sub(lambda _: "\\n", text)


def render(language: str, entries: Iterable[LocEntry], trailing: str = "") -> str:
    """Собрать текст файла в каноническом формате (один пробел отступа у записей)."""
    parts: list[str] = [f"l_{language}:\n"]
    for e in entries:
        if e.comment_before:
            parts.append(e.comment_before)
        ver = e.version if e.version else ""
        line = f' {e.key}:{ver} "{escape_value(e.text)}"'
        if e.comment_inline:
            line += " " + _REAL_NEWLINE.sub(" ", e.comment_inline)
        parts.append(line + "\n")
    if trailing:
        parts.append(trailing)
    return "".join(parts)


def write_file(path: Path, language: str, entries: Iterable[LocEntry], trailing: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(render(language, entries, trailing))


def unescape(text: str) -> str:
    """Раскрыть \\n и \\" — только для отображения и QA, не для хранения."""
    return text.replace("\\n", "\n").replace('\\"', '"')
