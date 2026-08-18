"""Сборка баз памяти переводов (.pdxtm) из готовых файлов локализации.

Двумя способами:
  * из пары папок с локализацией — так делается база игры из ванильной
    локализации CK3 (localization/english + localization/russian);
  * из текущего проекта — чтобы поделиться своими переводами.

Базы пишутся в режиме журналирования DELETE: их подключают только на чтение,
а WAL при этом требует служебных файлов рядом.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pdxloc.core.i18n import fill, translate
from pdxloc.core import loc_formats, tm
from pdxloc.core.progress import throttled
from pdxloc.db import fts5_available  # noqa: F401  — часть публичного API модуля
from pdxloc.core.scanner import LEGACY_MARKER
from pdxloc.core.statuses import Status

TM_SCHEMA_VERSION = 2      # v2: полнотекстовый индекс tm_fts для поиска похожих

TM_DDL = """
CREATE TABLE tm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE tm_entries (
    id         INTEGER PRIMARY KEY,
    en_hash    TEXT NOT NULL,
    en_text    TEXT NOT NULL,
    ru_text    TEXT NOT NULL,
    source     TEXT NOT NULL DEFAULT 'import',
    key        TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(en_hash, ru_text)
);
CREATE INDEX idx_tm_hash ON tm_entries(en_hash);
"""

# Индекс кандидатов для поиска похожих строк. content='tm_entries' — внешнее
# содержимое: текст не дублируется, индекс над ванильной базой (244 тыс. записей)
# добавляет к файлу около 30 МБ и отвечает за доли миллисекунды.
TM_FTS_DDL = """
CREATE VIRTUAL TABLE tm_fts USING fts5(
    en_text, content='tm_entries', content_rowid='id', tokenize='unicode61');
"""

ProgressCb = Callable[[int, int, str], None]


def has_fts_index(conn: sqlite3.Connection, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type = 'table' AND name = 'tm_fts'"
    ).fetchone()
    return row is not None


def build_fts_index(path: Path, progress_cb: ProgressCb | None = None) -> int:
    """Достроить индекс похожих строк в существующей базе. Идемпотентна.

    Базы подключаются к проекту только на чтение, поэтому индекс строится
    отдельным соединением — по кнопке, а не втихую при открытии проекта.
    """
    path = Path(path)
    if not fts5_available():
        raise RuntimeError(translate(
            "TmImport",
            "This SQLite build has no FTS5 — similarity search is unavailable"))
    conn = sqlite3.connect(str(path))
    try:
        if progress_cb:
            progress_cb(0, 2, translate("TmImport", "building the index…"))
        if not has_fts_index(conn):
            conn.executescript(TM_FTS_DDL)
        conn.execute("INSERT INTO tm_fts(tm_fts) VALUES('rebuild')")
        conn.execute(
            "INSERT INTO tm_meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(TM_SCHEMA_VERSION),))
        conn.commit()
        if progress_cb:
            progress_cb(1, 2, translate("TmImport", "compacting…"))
        conn.execute("VACUUM")      # rebuild оставляет дыры в файле
        count = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
    finally:
        conn.close()
    if progress_cb:
        progress_cb(2, 2, "done")
    return count


@dataclass
class TmBuildReport:
    files: int = 0
    pairs: int = 0
    skipped: int = 0        # пары, где перевода нет или он равен оригиналу
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    def summary(self) -> str:
        """Итог сборки базы — показывается на вкладке «Собрать базу»."""
        lines = [
            fill(translate("TmImport", "Files processed: %1"), self.files),
            fill(translate("TmImport", "Translation pairs: %1"), self.pairs),
        ]
        if self.skipped:
            lines.append(fill(translate(
                "TmImport", "Skipped (no translation): %1"), self.skipped))
        if self.warnings:
            lines.append(fill(translate(
                "TmImport", "Parser warnings: %1"), len(self.warnings)))
        return "\n".join(lines)


def create_tm_database(
    path: Path,
    *,
    name: str,
    src_lang: str,
    tgt_lang: str,
    kind: str = "import",
    game: str = "",
) -> sqlite3.Connection:
    """Пустая база памяти с описанием в `tm_meta`.

    `game` пустой означает «неизвестна»: базы, собранные до появления игр,
    ничего о себе не говорят, и выдавать за них догадку нельзя — по такой
    догадке база молча пропала бы из списка у проекта другой игры.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.executescript(TM_DDL)
    if fts5_available():
        conn.executescript(TM_FTS_DDL)
    conn.executemany(
        "INSERT INTO tm_meta (key, value) VALUES (?, ?)",
        [("format", "pdxtm"), ("schema_version", str(TM_SCHEMA_VERSION)),
         ("name", name), ("src_lang", src_lang), ("tgt_lang", tgt_lang),
         ("kind", kind), ("game", game), ("created_at", "")],
    )
    conn.execute("UPDATE tm_meta SET value = datetime('now') WHERE key = 'created_at'")
    conn.commit()
    return conn


def find_sibling_language_dir(src_dir: Path, tgt_lang: str) -> Path | None:
    """Соседняя папка того же уровня для другого языка (localization/english → …/russian)."""
    src_dir = Path(src_dir)
    sibling = src_dir.parent / tgt_lang
    return sibling if sibling.is_dir() else None


def find_localization_dirs(
    root: Path, src_lang: str = "english", tgt_lang: str = "russian",
) -> tuple[Path | None, Path | None]:
    """Найти папки локализации внутри указанной.

    Пользователь естественно указывает корень игры или мода, а локализация
    лежит глубже: у CK3 это game\\localization\\english. Без этого поиска пары
    не находятся вовсе: метка языка есть и в имени файла, и в имени каталога,
    а подменяется только в имени — путь к переводу получается несуществующим.
    """
    root = Path(root)
    if not root.is_dir():
        return None, None

    def pair(base: Path) -> tuple[Path | None, Path | None]:
        src = base / src_lang
        tgt = base / tgt_lang
        return (src if src.is_dir() else None, tgt if tgt.is_dir() else None)

    # сам корень уже папка нужного языка
    if root.name == src_lang:
        return root, find_sibling_language_dir(root, tgt_lang)

    # типовые места: <root>/localization, <root>/game/localization, <root>/replace.
    # `localisation` через «s» — это старые игры серии (CK2, EU3, Victoria 2) и
    # EU4 со Stellaris: букву в названии папки Paradox сменила только к CK3
    candidates = [root, root / "localization", root / "localisation",
                  root / "game" / "localization", root / "game" / "localisation",
                  root / "localization" / "replace",
                  root / "localisation" / "replace"]
    for base in candidates:
        if base.is_dir():
            src, tgt = pair(base)
            if src is not None:
                return src, tgt

    # последний шанс: поискать папку языка на разумной глубине
    for depth in ("*", "*/*", "*/*/*"):
        for found in sorted(root.glob(f"{depth}/{src_lang}")):
            if found.is_dir():
                return found, find_sibling_language_dir(found, tgt_lang)
    return None, None


def language_dirs(root: Path, lang: str, max_depth: int = 3) -> list[Path]:
    """Все папки языка внутри указанной, от ближних к дальним.

    Переводы-моды кладут файлы не в одном месте: у русификатора AGOT рядом
    лежат `localization/russian` (перевод самого мода) и
    `localization/replace/russian` (замена ванильных строк). Выбрать нужно ту,
    что действительно парная оригиналу, поэтому возвращаем все.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    found: list[Path] = []
    if root.name == lang:
        found.append(root)
    seen = {p.resolve() for p in found}
    patterns = ["/".join(["*"] * d + [lang]) for d in range(max_depth)]
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_dir() and path.resolve() not in seen:
                seen.add(path.resolve())
                found.append(path)
    return found


def resolve_target_dir(
    src_dir: Path, chosen: Path, src_lang: str = "english", tgt_lang: str = "russian",
) -> tuple[Path | None, list[tuple[Path, int]]]:
    """Какую папку перевода брать для указанной папки оригинала.

    Возвращает лучшую (больше всего пар) и все рассмотренные с числом пар —
    чтобы окно могло объяснить выбор, а не молча подставить другой путь.
    """
    chosen = Path(chosen)
    if not chosen.is_dir():
        return None, []
    candidates = [chosen, *language_dirs(chosen, tgt_lang)]
    scored: list[tuple[Path, int]] = []
    seen: set[Path] = set()
    for path in candidates:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        scored.append((path, count_pairs(src_dir, path, src_lang, tgt_lang)[0]))
    best = max(scored, key=lambda item: item[1], default=(None, 0))
    return (best[0] if best[1] else None), scored


def count_pairs(
    src_dir: Path, tgt_dir: Path, src_lang: str = "english", tgt_lang: str = "russian",
) -> tuple[int, int]:
    """Сколько файлов имеют пару и сколько всего файлов оригинала.

    Дешёвая прикидка до начала работы: если пар нет, собирать нечего.
    """
    src_dir, tgt_dir = Path(src_dir), Path(tgt_dir)
    fmt = loc_formats.get(loc_formats.detect(src_dir))
    files = fmt.files(src_dir, src_lang)
    paired = sum(
        1 for p in files
        if (tgt_dir / fmt.map_relpath(
            p.relative_to(src_dir).as_posix(), src_lang, tgt_lang)).is_file()
    )
    return paired, len(files)


def _encoding_of(fmt: loc_formats.LocFormat, root: Path) -> str:
    """Кодировка дерева. У формата с единственной кодировкой — она и есть."""
    from pdxloc.core import paradox_csv

    if len(fmt.encodings) == 1:
        return fmt.encodings[0]
    return paradox_csv.detect_encoding(fmt.files(root)) if root.is_dir() else ""


class TmBuildCancelled(Exception):
    """Сборка прервана пользователем — недописанная база удаляется."""


def build_tm_from_dirs(
    src_dir: Path,
    tgt_dir: Path | None,
    out_path: Path,
    *,
    name: str,
    src_lang: str = "english",
    tgt_lang: str = "russian",
    kind: str = "import",
    game: str = "",
    progress_cb: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> TmBuildReport:
    """Собрать базу из двух деревьев локализации.

    Пишем во временный файл и переименовываем в конце: иначе при неудаче на
    месте остаётся пустая, но с виду исправная база — её можно подключить и
    долго гадать, почему нет подсказок.
    """
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise FileNotFoundError(fill(translate("TmImport", "Original folder not found: %1"), src_dir))
    if tgt_dir is None:
        tgt_dir = find_sibling_language_dir(src_dir, tgt_lang)
        if tgt_dir is None:
            raise FileNotFoundError(
                fill(translate("TmImport",
                           "No translation folder found next to %1 "
                           "(…/%2 was expected)"), src_dir, tgt_lang))
    tgt_dir = Path(tgt_dir)
    if not tgt_dir.is_dir():
        raise FileNotFoundError(fill(translate("TmImport", "Translation folder not found: %1"), tgt_dir))

    fmt = loc_formats.get(loc_formats.detect(src_dir))
    src_files = fmt.files(src_dir, src_lang)
    # Кодировки деревьев спрашиваем один раз на сборку: у старого формата серии
    # оригинал и перевод лежат в разных однобайтовых кодировках (cp1252 и
    # cp1251), а определять их на каждый файл значило бы читать дерево дважды.
    src_encoding = _encoding_of(fmt, src_dir)
    tgt_encoding = _encoding_of(fmt, tgt_dir)
    if not src_files:
        raise FileNotFoundError(fill(translate(
            "TmImport",
            "The folder %1 has no localization files of the language «%2» "
            "(names like *_l_%2.yml were expected)"), src_dir, src_lang))

    out_path = Path(out_path)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")
    tmp_path.unlink(missing_ok=True)

    report = TmBuildReport()
    report_progress = throttled(progress_cb)

    def milestone(text: str) -> None:
        """Веха идёт мимо ограничителя частоты — иначе её может съесть."""
        if progress_cb is not None:
            progress_cb(len(src_files), len(src_files), text)

    conn = create_tm_database(
        tmp_path, name=name, src_lang=src_lang, tgt_lang=tgt_lang,
        kind=kind, game=game)
    try:
        conn.execute("BEGIN")
        for i, path in enumerate(src_files):
            if should_cancel is not None and should_cancel():
                raise TmBuildCancelled
            rel = path.relative_to(src_dir).as_posix()
            report_progress(i, len(src_files), rel + fill(
                translate("TmImport", " · pairs: %1"), report.pairs))
            tgt_path = tgt_dir / fmt.map_relpath(rel, src_lang, tgt_lang)
            if not tgt_path.is_file():
                continue
            src_lf = fmt.parse_file(path, language=src_lang, encoding=src_encoding)
            tgt_lf = fmt.parse_file(tgt_path, language=tgt_lang, encoding=tgt_encoding)
            report.warnings.extend(src_lf.warnings)
            report.warnings.extend(tgt_lf.warnings)
            report.files += 1
            tgt_entries = {e.key: e for e in tgt_lf.entries}
            rows = []
            for e in src_lf.entries:
                other = tgt_entries.get(e.key)
                if (other is None or not other.text or not e.text
                        or other.text == e.text
                        or LEGACY_MARKER in other.comment_inline):
                    report.skipped += 1
                    continue
                rows.append((tm.en_hash(e.text), e.text, other.text, source_for(kind), e.key))
            conn.executemany(
                "INSERT OR IGNORE INTO tm_entries (en_hash, en_text, ru_text, source, key) "
                "VALUES (?, ?, ?, ?, ?)", rows)
            report.pairs += len(rows)
            # фиксируем порциями: на ванильной локализации это сотни тысяч
            # записей, держать их все в одной транзакции незачем
            if report.files % 100 == 0:
                conn.commit()
                conn.execute("BEGIN")
        milestone(translate("TmImport", "saving the database…"))
        conn.commit()
        if has_fts_index(conn):
            # индекс с внешним содержимым не обновляется вставками сам —
            # собираем его разом в конце, это заметно быстрее построчного
            milestone(translate("TmImport", "building the similar-rows index…"))
            conn.execute("INSERT INTO tm_fts(tm_fts) VALUES('rebuild')")
            conn.commit()
        report.pairs = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
    except BaseException:
        conn.rollback()
        conn.close()
        tmp_path.unlink(missing_ok=True)
        raise
    conn.close()

    if report.pairs == 0:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(fill(translate(
            "TmImport",
            "Not a single «original — translation» pair was found.\n\n"
            "Original files checked: %1, of them with a pair in the translation "
            "folder: %2.\nUsually the reason is that the game or mod root was "
            "given instead of the localization folders "
            "(…\\game\\localization\\%3 and …\\localization\\%4, say)."),
            len(src_files), report.files, src_lang, tgt_lang))

    try:
        out_path.unlink(missing_ok=True)
        tmp_path.replace(out_path)
    except PermissionError as e:
        tmp_path.unlink(missing_ok=True)
        raise PermissionError(fill(translate(
            "TmImport",
            "Could not replace the database file: %1\n\nMost likely it is "
            "attached to the current project — detach it in «Tools → "
            "Translation memory…» and try again."), out_path)) from e
    milestone("done")
    return report


def source_for(kind: str) -> str:
    """Метка источника записи — по ней видно, откуда пришёл вариант перевода."""
    return "game" if kind == "game" else "import"


def export_project_tm(
    project_conn: sqlite3.Connection,
    out_path: Path,
    *,
    name: str,
) -> TmBuildReport:
    """Выгрузить переводы проекта в отдельную базу — чтобы поделиться."""
    proj = project_conn.execute(
        "SELECT name, src_lang, tgt_lang FROM projects WHERE id = 1").fetchone()
    src_lang = proj["src_lang"] if proj else "english"
    tgt_lang = proj["tgt_lang"] if proj else "russian"
    # игру не спрашиваем: проект её знает, и разойтись они не должны
    from pdxloc.project import game as project_game
    game = project_game(project_conn)

    # Список статусов положительный: `Status.MACHINE` и `Status.AUTO` в него не
    # входят намеренно. Такую базу подключают к другим проектам, и машинная
    # догадка, разошедшаяся по чужим проектам как «перевод из базы», —
    # худшее, что может случиться с памятью переводов.
    rows = project_conn.execute(
        """SELECT en_text, ru_text, key, en_hash FROM units
           WHERE is_deleted = 0 AND en_text IS NOT NULL AND ru_text IS NOT NULL
             AND ru_text != en_text AND status IN (?, ?, ?)""",
        (Status.TRANSLATED.value, Status.REVIEWED.value, Status.CUSTOM.value),
    ).fetchall()

    conn = create_tm_database(
        out_path, name=name, src_lang=src_lang, tgt_lang=tgt_lang,
        kind="project-export", game=game)
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO tm_entries (en_hash, en_text, ru_text, source, key) "
            "VALUES (?, ?, ?, 'project-export', ?)",
            [(r["en_hash"] or tm.en_hash(r["en_text"]), r["en_text"], r["ru_text"], r["key"])
             for r in rows])
        if has_fts_index(conn):
            conn.execute("INSERT INTO tm_fts(tm_fts) VALUES('rebuild')")
        conn.commit()
        pairs = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
    finally:
        conn.close()
    return TmBuildReport(files=0, pairs=pairs, skipped=0)
