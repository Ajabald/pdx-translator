"""Reader and writer for the Paradox localisation format (CK3).

This is NOT real YAML: the standard yaml libraries fall over on it.
The format:
    l_english:                       <- the header, the first line
     key_name:0 "text"               <- an entry; the version after ':' is optional
    #comment                         <- a comment; sometimes trailing, after the quote

Files are read and written in UTF-8 with a BOM (encoding='utf-8-sig') — CK3
silently ignores files without one.

The text of an entry is stored raw — between the quotes, with the \" and \n
escapes left unexpanded — so that hashes and version comparisons stay stable.
unescape() is for display and for the quality counts only.

A known limitation: a trailing comment containing a '"' character parses wrongly,
because the regex is greedy. Real data holds none of those.
"""
from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterable

from pdxloc.core.i18n import fill, translate
from pdxloc.core.models import LocEntry, LocFile

# The key is everything up to the colon except spaces, a quote and a hash.
# Listing the permitted characters turned out to be impossible: the vanilla CK3
# localisation has keys with an apostrophe (b_mansa'l-kharaz, b_ka'abir), and
# they were lost in silence — the line was not recognised as an entry, and
# writing the translation to the mod would have dropped it from the file.
KEY = r'[^\s:"#]+'
ENTRY_RE = re.compile(rf'^\s*({KEY}):(\d*)\s*"(.*)"\s*(#.*)?$')
# A line with the closing quote missing — a real defect in mod files: pick the
# text up to the end of the line and warn; the export will add the quote.
ENTRY_NOCLOSE_RE = re.compile(rf'^\s*({KEY}):(\d*)\s*"(.*)$')
HEADER_RE = re.compile(r'^\s*l_([a-z_]+):\s*$')
COMMENT_RE = re.compile(r'^\s*#')


def parse_text(text: str, *, source_name: str = "?") -> LocFile:
    """Parse the contents of a localisation file; the BOM is stripped on reading."""
    language = ""
    entries: list[LocEntry] = []
    warnings: list[str] = []
    pending_comments: list[str] = []   # the lines above the next entry
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
            # No header. We do not complain at once: the vanilla localisation holds files
            # commented out entirely by the Paradox editor — there is no header there and no
            # entries either, so there is nothing to complain about. The decision is made at
            # the end, when it is clear whether any entries were found.
            missing_header = fill(translate(
                "ParadoxYaml", "%1:%2: an l_*: header was expected, found: %3"),
                source_name, i + 1, repr(line.strip()))
            header_seen = True   # from here on we parse as usual
            # the line may turn out to be an entry: fall through to the common parse

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
            warnings.append(fill(translate(
                "ParadoxYaml",
                "%1:%2: no closing quote for the key %3 — the text was taken "
                "to the end of the line"), source_name, i + 1, repr(key)))
            continue

        warnings.append(fill(translate(
            "ParadoxYaml", "%1:%2: unrecognized line: %3"),
            source_name, i + 1, repr(line.strip())))

    if missing_header is not None and entries:
        warnings.insert(0, missing_header)

    return LocFile(
        language=language,
        entries=entries,
        trailing="".join(pending_comments),
        warnings=warnings,
    )


def parse_file(path: Path, *, language: str = "", encoding: str = "") -> LocFile:
    """Parse a file. The language and the encoding are accepted but not asked for.

    The arguments are needed by the other format of the series
    (`core/paradox_csv.py`), where the language is a column and the encoding
    varies; the shared call from `core/loc_formats.py` has to suit both. Here the
    language stands in the file itself, and the format has one encoding.
    """
    text = path.read_text(encoding=encoding or "utf-8-sig")
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
    """Build the file text in the canonical form: one space of indent per entry."""
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


# --- where the language sits in the tree ---


def lang_tag(language: str) -> str:
    """The language marker in a file name: english -> _l_english."""
    return f"_l_{language}"


def map_relpath(rel_posix: str, from_lang: str, to_lang: str) -> str:
    """The path of the same file in the tree of another language.

    Two things change: the language marker in the file name — it also occurs in
    the middle, as in agot_modifiers_l_english_BLA.yml — and the language
    directory in the path.

    The directory is mandatory, because workshop mods are laid out as
    `localization/english/...` and `localization/russian/...`, while people
    naturally point the project root at `localization` itself. While the directory
    went unrenamed, the counterpart looked for next to
    `english/agot/foo_l_english.yml` was `english/agot/foo_l_russian.yml` — which
    of course did not exist, so the whole translation of the mod counted as
    missing and the translation files as orphans.

    Only whole path segments are replaced: `english_notes` is not a language
    folder.
    """
    parts = rel_posix.split("/")
    name = parts[-1].replace(lang_tag(from_lang), lang_tag(to_lang))
    dirs = [to_lang if part == from_lang else part for part in parts[:-1]]
    return "/".join([*dirs, name])


def files(root: Path, language: str = "", *, skip_updated: bool = False) -> list[Path]:
    """Localisation files carrying the language marker in the name.

    skip_updated filters out litter from the user's old scripts (*_updated.yml).
    It applies to the translation tree only: the source tree holds no such litter,
    and a name like mod_updated_events_l_english.yml is perfectly legal.
    """
    tag = lang_tag(language) if language else "_l_"
    return sorted(
        p for p in root.rglob("*.yml")
        if tag in p.name and not (skip_updated and "_updated" in p.name)
    )


def detect(root: Path) -> bool:
    """Whether a tree looks like localisation in the current format of the series.

    The sign is an `l_<language>:` header on the first significant line. The file
    name alone is not enough: a `.yml` next to a mod is sometimes a build config.
    """
    for path in root.rglob("*.yml"):
        try:
            head = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
        except OSError:
            continue
        for line in head.splitlines():
            if HEADER_RE.match(line):
                return True
            if line.strip() and not COMMENT_RE.match(line):
                break      # первая значащая строка не заголовок — не наш файл
    return False
