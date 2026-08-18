"""Парсер/писатель локализации старых игр Paradox (CK2, EU3, Victoria 2, HoI3).

До Clausewitz 2.0 текст лежал не в `l_<язык>:`-файлах, а в таблице с точкой с
запятой:

    #CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;;;x
    d_cornwall;Cornwall;Cornouailles;Cornwall;;Cornualles;;;;;;;;;x

Отсюда три отличия от `paradox_yaml`, и каждое меняет работу:

* **язык — это колонка, а не папка.** Файл один на все языки, и перевод живёт
  внутри той же строки, что оригинал;
* **русского в формате нет.** Ни в одной шапке ванильной CK2 нет `RUSSIAN` —
  игра знает английский, французский, немецкий и испанский. Поэтому русификатор
  подменяет английскую колонку, и мы делаем так же (см. `column_of`);
* **кодировка однобайтовая.** Ваниль лежит в cp1252, русский перевод — в cp1251
  вместе со своими шрифтами. Записывать надо в той же, в какой прочитали:
  utf-8 игра прочтёт как мусор.

**Запись идёт подменой одной колонки в исходной строке.** В ванильной CK2 253
строки имеют больше пятнадцати колонок, а в 196 после маркера `x` стоят ещё
пустые разделители; в русификаторе за `x` дописан хвостовой комментарий с
английским оригиналом. Собери мы строку заново по своим правилам — всё это
исчезло бы вместе с французским и немецким переводами. Поэтому `LocEntry.raw`
хранит строку целиком, а `render` меняет в ней ровно один сегмент.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from pdxloc.core.i18n import fill, translate
from pdxloc.core.models import LocEntry, LocFile

SEPARATOR = ";"
COMMENT = "#"
EXT = ".csv"

# Порядок колонок в шапке ванильной CK2. Пятая пропущена намеренно — она пустая
# и в самой игре (`GERMAN;;SPANISH`), исторически там был итальянский.
DEFAULT_COLUMNS: dict[str, int] = {
    "english": 1, "french": 2, "german": 3, "spanish": 5,
}
HEADER_RE = re.compile(r"^#\s*CODE\s*;", re.IGNORECASE)
# Кириллическое слово: три буквы подряд. Одиночная буква не годится — при
# чтении cp1252-файла как cp1251 отдельные `ö` и `é` превращаются в кириллицу.
CYRILLIC_WORD = re.compile(r"[А-я]{3,}")

ENCODINGS = ("cp1251", "cp1252")


def column_of(language: str, header: str = "") -> int:
    """Номер колонки языка. Незнакомый язык пишется вместо английского.

    Русского (как и польского с китайским) в формате нет вовсе, а деть перевод
    куда-то надо — и единственное рабочее место то же, что выбрал живой
    русификатор: колонка английского. Игра прочтёт перевод как основной текст,
    остальные языки останутся на местах.
    """
    if header and HEADER_RE.match(header):
        names = [c.strip().lower() for c in header.lstrip("#").split(SEPARATOR)]
        if language.lower() in names:
            return names.index(language.lower())
    return DEFAULT_COLUMNS.get(language, DEFAULT_COLUMNS["english"])


def detect_encoding(paths: Iterable[Path]) -> str:
    """Кодировка дерева: cp1251, если в нём есть русский текст, иначе cp1252.

    Обе кодировки однобайтовые и декодируют что угодно, поэтому отличаем их не
    по ошибкам разбора, а по содержимому — и **по дереву целиком**, а не по
    файлу: в русификаторе CK2 есть `WikipediaLinks.csv` из одних ссылок
    латиницей, и по нему одному вывод был бы обратным. Замер на живых данных:
    у ванили доля строк с русским словом не превышает 0,0006, у перевода
    доходит до 0,99 — порог посередине берётся с огромным запасом.
    """
    for path in paths:
        try:
            # первых килобайт хватает: перевод виден с первых же строк, а
            # читать всё дерево целиком ради одного вопроса дорого
            with open(path, "rb") as fh:
                text = fh.read(64 * 1024).decode("cp1251", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        if not lines:
            continue
        hits = sum(1 for line in lines if CYRILLIC_WORD.search(line))
        if hits / len(lines) > 0.02:
            return "cp1251"
    return "cp1252"


def _sanitize(text: str) -> str:
    """Убрать суррогаты из текста, который поедет в базу.

    Файлы читаются с `surrogateescape` — иначе байт, которого нет в выбранной
    кодовой странице, потерялся бы при обратной записи (в ванильной CK2 такой
    есть: в `text1.csv` чешская колонка местами лежит в cp1250). Суррогатам
    место в строке, которую мы вернём на диск как есть, но не в SQLite: там они
    роняют запись. Поэтому в переводимом тексте они становятся «?».
    """
    if not text.isprintable() or any("\ud800" <= ch <= "\udfff" for ch in text):
        return "".join("?" if "\ud800" <= ch <= "\udfff" else ch for ch in text)
    return text


def parse_text(text: str, *, language: str = "english",
               source_name: str = "?") -> LocFile:
    """Разобрать содержимое CSV-файла локализации.

    Строка без разделителя — не запись; в ванили таких нет, но у мода бывают, и
    молчать о них нельзя: это либо потерянная точка с запятой, либо мусор.
    """
    entries: list[LocEntry] = []
    warnings: list[str] = []
    pending: list[str] = []
    header = ""
    column = column_of(language)

    for i, line in enumerate(text.splitlines()):
        if not line.strip() or line.startswith(COMMENT):
            if not header and HEADER_RE.match(line):
                header = line
                column = column_of(language, header)
            pending.append(line + "\n")
            continue
        if SEPARATOR not in line:
            warnings.append(fill(translate(
                "ParadoxCsv", "%1:%2: a line without a «;» separator: %3"),
                source_name, i + 1, repr(line.strip()[:60])))
            pending.append(line + "\n")
            continue
        parts = line.split(SEPARATOR)
        entries.append(LocEntry(
            key=_sanitize(parts[0]),
            version="",
            text=_sanitize(parts[column]) if column < len(parts) else "",
            comment_before="".join(pending),
            comment_inline="",
            line_no=len(entries),
            raw=line,
        ))
        pending = []

    return LocFile(
        language=language,
        entries=entries,
        trailing="".join(pending),
        warnings=warnings,
    )


def parse_file(path: Path, *, language: str = "english",
               encoding: str = "") -> LocFile:
    """Прочитать файл. Байты, чужие для кодировки, переживают круг «чтение —
    запись» невредимыми: `surrogateescape` прячет их в строке и возвращает при
    обратной записи. Это не теория — в ванильной CK2 у `text1.csv` чешская
    колонка местами лежит в cp1250, и без этого приёма перевод одной строки
    испортил бы соседние языки во всём файле.
    """
    raw = path.read_bytes()
    encoding = encoding or detect_encoding([path])
    return parse_text(raw.decode(encoding, errors="surrogateescape"),
                      language=language, source_name=path.name)


_REAL_NEWLINE = re.compile(r"\r\n|[\r\n]")


def escape_value(text: str) -> str:
    """Привести значение к виду, который переживёт запись в таблицу.

    Перенос строки — как и в `.yml`, двумя символами: настоящий разорвал бы
    запись пополам. Точка с запятой — отдельная беда этого формата: она здесь
    разделитель колонок, экранирования формат не знает, и оставь мы её как
    есть, перевод сдвинул бы французскую и немецкую колонки вправо, а маркер
    `x` уехал бы за край. Меняем на запятую — потеря заметно меньше, чем
    сломанная строка в игре.
    """
    return _REAL_NEWLINE.sub(lambda _: "\\n", text).replace(SEPARATOR, ",")


def replace_column(raw: str, column: int, value: str) -> str:
    """Подменить одну колонку строки, сохранив все прочие.

    `split`/`join` по разделителю возвращает строку символ в символ, пока число
    сегментов не меняется, — поэтому лишние пустые колонки, маркер `x` и
    хвостовой комментарий после него доживают до файла нетронутыми.
    """
    parts = raw.split(SEPARATOR)
    while len(parts) <= column:
        parts.append("")
    parts[column] = value
    return SEPARATOR.join(parts)


# Шаблон для ключей, которых в исходном дереве не было: ключ, текст, маркер.
# Пятнадцать колонок, как в ванили, здесь ни к чему — игра читает до `x`.
NEW_ROW = "{key};{text};x"


def _fits(line: str, encoding: str) -> bool:
    """Ляжет ли строка в кодировку целиком, ничего не переврав."""
    try:
        line.encode(encoding, errors="surrogateescape")
    except UnicodeEncodeError:
        return False
    return True


def render(language: str, entries: Iterable[LocEntry], trailing: str = "",
           *, encoding: str = "") -> str:
    """Собрать текст файла.

    **Чужие колонки сохраняются, пока они переживают кодировку.** Перевод на
    французский пишется в тот же cp1252, что и оригинал, и немецкий с испанским
    остаются на местах. А вот русский требует cp1251, где нет ни `ê`, ни `ü`:
    сохрани мы там французскую колонку, `Reconquête` стало бы `Reconquкte` —
    испорченный текст вместо перевода. В этом случае строка ужимается до
    «ключ; перевод; x» — ровно так и поступает живой русификатор CK2.

    Последняя строка всегда завершается переносом: в ванильной CK2 девять
    файлов из 124 обрываются без него, но дописать перенос безопасно (игра
    читает построчно), а тянуть за собой признак «этот файл без последнего
    перевода строки» значило бы держать его в модели ради девяти файлов.
    """
    column = column_of(language)
    parts: list[str] = []
    for entry in entries:
        if entry.comment_before:
            parts.append(entry.comment_before)
        text = escape_value(entry.text)
        line = (replace_column(entry.raw, column, text) if entry.raw
                else NEW_ROW.format(key=entry.key, text=text))
        if encoding and not _fits(line, encoding):
            line = NEW_ROW.format(key=entry.key, text=text)
        parts.append(line + "\n")
    if trailing:
        parts.append(trailing)
    return "".join(parts)


def write_file(path: Path, language: str, entries: Iterable[LocEntry],
               trailing: str = "", *, encoding: str = "cp1251",
               newline: str = "\r\n") -> None:
    """Записать файл. Концы строк по умолчанию CRLF — как в самих играх.

    Не мелочь: ванильная CK2 вся до последнего файла CRLF, живой русификатор —
    92 файла из 93. Запиши мы LF, и перевод одной строки показал бы в чужом
    инструменте сравнения весь файл изменённым.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render(language, entries, trailing, encoding=encoding)
    if newline != "\n":
        text = _REAL_NEWLINE.sub(newline, text)
    # surrogateescape возвращает на место байты, чужие для этой кодовой
    # страницы (см. parse_file); всё остальное, что в неё не лезет, заменяем —
    # потерять из-за одного символа целый файл хуже, чем потерять символ,
    # который игра всё равно не покажет
    try:
        data = text.encode(encoding, errors="surrogateescape")
    except UnicodeEncodeError:
        data = text.encode(encoding, errors="replace")
    path.write_bytes(data)


def unescape(text: str) -> str:
    """Раскрыть \\n — только для отображения и QA, не для хранения."""
    return text.replace("\\n", "\n")


def files(root: Path, language: str = "", *, skip_updated: bool = False) -> list[Path]:
    """Файлы локализации в дереве. Язык на имя файла не влияет — он колонка."""
    return sorted(
        p for p in root.rglob(f"*{EXT}")
        if not (skip_updated and "_updated" in p.name)
    )


def map_relpath(rel_posix: str, from_lang: str, to_lang: str) -> str:
    """Путь того же файла в дереве перевода — он же самый.

    Языка нет ни в имени файла, ни в пути: и оригинал, и перевод зовутся
    `HolyFury.csv`, а различаются деревьями (ваниль игры против папки мода).
    """
    return rel_posix


def detect(root: Path) -> bool:
    """Похоже ли дерево на локализацию старого формата.

    Смотрим на содержимое, а не на расширение: `.csv` в папке мода бывает и
    таблицей данных (у CK2 это, например, `culture_table.csv` конвертера в
    EU4). Признак записи — ключ, разделитель и хоть что-то после него.
    """
    for path in root.rglob(f"*{EXT}"):
        try:
            head = path.read_bytes()[:4096].decode("cp1252", errors="replace")
        except OSError:
            continue
        for line in head.splitlines():
            if HEADER_RE.match(line):
                return True
            if not line.strip() or line.startswith(COMMENT):
                continue
            parts = line.split(SEPARATOR)
            if len(parts) >= 3 and parts[0] and not parts[0].isspace():
                return True
    return False
