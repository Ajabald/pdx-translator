"""Reader and writer for the older Paradox games (CK2, EU3, Victoria 2, HoI3).

Before Clausewitz 2.0 the text lived not in `l_<language>:` files but in a
semicolon-separated table:

    #CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;;;x
    d_cornwall;Cornwall;Cornouailles;Cornwall;;Cornualles;;;;;;;;;x

Hence three differences from `paradox_yaml`, and each of them changes the work:

* **the language is a column, not a folder.** There is one file for every
  language, and the translation lives inside the same row as the original;
* **the format has no Russian.** Not one header in vanilla CK2 says `RUSSIAN` —
  the game knows English, French, German and Spanish. So the Russian pack
  replaces the English column, and we do the same (see `column_of`);
* **the encoding is single-byte.** Vanilla lies in cp1252, the Russian
  translation in cp1251 together with its own fonts. It has to be written back in
  the encoding it was read in: the game reads utf-8 as rubbish.

**Writing works by replacing one column inside the source line.** In vanilla CK2
253 rows have more than fifteen columns, and in 196 of them empty separators
follow the `x` marker; in the Russian pack a trailing comment with the English
original is appended after the `x`. Rebuild the line by our own rules and all of
that would disappear along with the French and German translations. That is why
`LocEntry.raw` keeps the whole line and `render` changes exactly one segment in
it.
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

# The order of the columns in the vanilla CK2 header. The fifth is skipped on
# purpose — it is empty in the game itself (`GERMAN;;SPANISH`), and historically
# held Italian.
DEFAULT_COLUMNS: dict[str, int] = {
    "english": 1, "french": 2, "german": 3, "spanish": 5,
}
HEADER_RE = re.compile(r"^#\s*CODE\s*;", re.IGNORECASE)
# A Cyrillic word: three letters in a row. A single letter will not do — reading
# a cp1252 file as cp1251 turns lone `ö` and `é` into Cyrillic.
CYRILLIC_WORD = re.compile(r"[А-я]{3,}")

ENCODINGS = ("cp1251", "cp1252")


def column_of(language: str, header: str = "") -> int:
    """The column of a language. An unknown one is written over English.

    The format has no Russian at all, nor Polish, nor Chinese, and the translation
    has to go somewhere — and the only workable place is the one the real Russian
    pack chose: the English column. The game reads the translation as its main
    text and the other languages stay where they are.
    """
    if header and HEADER_RE.match(header):
        names = [c.strip().lower() for c in header.lstrip("#").split(SEPARATOR)]
        if language.lower() in names:
            return names.index(language.lower())
    return DEFAULT_COLUMNS.get(language, DEFAULT_COLUMNS["english"])


def detect_encoding(paths: Iterable[Path]) -> str:
    """The encoding of a tree: cp1251 when it holds Russian text, cp1252 otherwise.

    Both encodings are single-byte and decode anything, so they are told apart by
    the content rather than by parse errors — and **over the whole tree** rather
    than per file: the CK2 Russian pack contains `WikipediaLinks.csv`, made
    entirely of Latin links, and on that file alone the verdict would be the
    opposite. Measured on live data: in vanilla the share of rows holding a
    Russian word never exceeds 0.0006, in the translation it reaches 0.99 — a
    threshold in the middle is taken with an enormous margin.
    """
    for path in paths:
        try:
            # the first few kilobytes are enough: a translation shows from the very first
            # rows, and reading the whole tree for one question is expensive
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
    """Strip the surrogates out of text on its way into the database.

    Files are read with `surrogateescape` — otherwise a byte absent from the
    chosen code page would be lost on the way back (vanilla CK2 has one: in
    `text1.csv` the Czech column lies in cp1250 in places). Surrogates belong in
    the line we hand back to disk unchanged, but not in SQLite: there they break
    the write. So in translatable text they become «?».
    """
    if not text.isprintable() or any("\ud800" <= ch <= "\udfff" for ch in text):
        return "".join("?" if "\ud800" <= ch <= "\udfff" else ch for ch in text)
    return text


def parse_text(text: str, *, language: str = "english",
               source_name: str = "?") -> LocFile:
    """Parse the contents of a CSV localisation file.

    A line with no separator is not an entry; vanilla has none, but a mod does,
    and staying silent about them is not allowed: it is either a lost semicolon or
    litter.
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
    """Read a file. Bytes foreign to the encoding survive the read-write round
    trip unharmed: `surrogateescape` hides them inside the string and gives them
    back when it is written. This is not theory — in vanilla CK2 the Czech column
    of `text1.csv` lies in cp1250 in places, and without the trick translating one
    row would corrupt the neighbouring languages throughout the file.
    """
    raw = path.read_bytes()
    encoding = encoding or detect_encoding([path])
    return parse_text(raw.decode(encoding, errors="surrogateescape"),
                      language=language, source_name=path.name)


_REAL_NEWLINE = re.compile(r"\r\n|[\r\n]")


def escape_value(text: str) -> str:
    """Bring a value into a form that survives being written into the table.

    A line break becomes two characters, as in `.yml`: a real one would tear the
    entry in two. The semicolon is a trouble peculiar to this format: here it
    separates the columns, the format knows no escaping, and left as it is a
    translation would shove the French and German columns to the right and push
    the `x` marker off the edge. We turn it into a comma — a noticeably smaller
    loss than a broken row in the game.
    """
    return _REAL_NEWLINE.sub(lambda _: "\\n", text).replace(SEPARATOR, ",")


def replace_column(raw: str, column: int, value: str) -> str:
    """Replace one column of a line, keeping every other.

    `split`/`join` on the separator returns the line character for character as
    long as the number of segments does not change — so the spare empty columns,
    the `x` marker and the trailing comment after it reach the file untouched.
    """
    parts = raw.split(SEPARATOR)
    while len(parts) <= column:
        parts.append("")
    parts[column] = value
    return SEPARATOR.join(parts)


# The template for keys the source tree did not have: key, text, marker. Fifteen
# columns as in vanilla serve nothing here — the game reads up to the `x`.
NEW_ROW = "{key};{text};x"


def _fits(line: str, encoding: str) -> bool:
    """Whether the line fits the encoding whole, without garbling anything."""
    try:
        line.encode(encoding, errors="surrogateescape")
    except UnicodeEncodeError:
        return False
    return True


def render(language: str, entries: Iterable[LocEntry], trailing: str = "",
           *, encoding: str = "") -> str:
    """Assemble the text of the file.

    **Other people's columns are kept as long as they survive the encoding.** A
    French translation is written in the same cp1252 as the original, and German
    and Spanish stay where they are. Russian, however, needs cp1251, which has
    neither `ê` nor `ü`: keep the French column there and `Reconquête` becomes
    `Reconquкte` — corrupted text instead of a translation. In that case the line
    is squeezed down to «key; translation; x», which is exactly what the real CK2
    Russian pack does.

    The last line always ends with a break: in vanilla CK2 nine files out of 124
    end without one, but adding it is safe — the game reads line by line — while
    carrying a «this file has no final newline» flag would mean keeping it in the
    model for the sake of nine files.
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
    """Write a file. The line endings default to CRLF, as in the games themselves.

    Not a detail: vanilla CK2 is CRLF down to the last file, and the real Russian
    pack in 92 files out of 93. Write LF and translating one row would show the
    whole file as changed in somebody else's diff tool.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render(language, entries, trailing, encoding=encoding)
    if newline != "\n":
        text = _REAL_NEWLINE.sub(newline, text)
    # surrogateescape puts back the bytes foreign to this code page (see
    # parse_file); everything else that will not fit is replaced — losing a whole
    # file over one character is worse than losing a character the game would not
    # show anyway
    try:
        data = text.encode(encoding, errors="surrogateescape")
    except UnicodeEncodeError:
        data = text.encode(encoding, errors="replace")
    path.write_bytes(data)


def unescape(text: str) -> str:
    """Expand the line-break escape — for display and the quality counts only."""
    return text.replace("\\n", "\n")


def files(root: Path, language: str = "", *, skip_updated: bool = False) -> list[Path]:
    """Localisation files in a tree. The language does not touch the file name: it
    is a column."""
    return sorted(
        p for p in root.rglob(f"*{EXT}")
        if not (skip_updated and "_updated" in p.name)
    )


def map_relpath(rel_posix: str, from_lang: str, to_lang: str) -> str:
    """The path of the same file in the translation tree — the very same path.

    The language is neither in the file name nor in the path: the original and the
    translation are both called `HolyFury.csv` and differ by their trees, the
    game's vanilla against the mod folder.
    """
    return rel_posix


def detect(root: Path) -> bool:
    """Whether a tree looks like localisation in the older format.

    We look at the content rather than at the extension: a `.csv` in a mod folder
    is sometimes a data table — in CK2, say, the `culture_table.csv` of the EU4
    converter. The sign of an entry is a key, a separator and at least something
    after it.
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
