"""Сборка баз памяти переводов (.ck3tm) из готовых файлов локализации.

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

from ck3loc.core import paradox_yaml, tm
from ck3loc.core.progress import throttled
from ck3loc.db import fts5_available  # noqa: F401  — часть публичного API модуля
from ck3loc.core.scanner import LEGACY_MARKER, _list_loc_files, lang_tag, map_relpath
from ck3loc.core.statuses import Status

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
        raise RuntimeError("В этой сборке SQLite нет FTS5 — поиск похожих недоступен")
    conn = sqlite3.connect(str(path))
    try:
        if progress_cb:
            progress_cb(0, 2, "построение индекса…")
        if not has_fts_index(conn):
            conn.executescript(TM_FTS_DDL)
        conn.execute("INSERT INTO tm_fts(tm_fts) VALUES('rebuild')")
        conn.execute(
            "INSERT INTO tm_meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(TM_SCHEMA_VERSION),))
        conn.commit()
        if progress_cb:
            progress_cb(1, 2, "сжатие…")
        conn.execute("VACUUM")      # rebuild оставляет дыры в файле
        count = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
    finally:
        conn.close()
    if progress_cb:
        progress_cb(2, 2, "готово")
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

    def summary_ru(self) -> str:
        lines = [f"Файлов обработано: {self.files}", f"Пар переводов: {self.pairs}"]
        if self.skipped:
            lines.append(f"Пропущено (нет перевода): {self.skipped}")
        if self.warnings:
            lines.append(f"Предупреждений парсера: {len(self.warnings)}")
        return "\n".join(lines)


def create_tm_database(
    path: Path,
    *,
    name: str,
    src_lang: str,
    tgt_lang: str,
    kind: str = "import",
) -> sqlite3.Connection:
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
        [("format", "ck3tm"), ("schema_version", str(TM_SCHEMA_VERSION)),
         ("name", name), ("src_lang", src_lang), ("tgt_lang", tgt_lang),
         ("kind", kind), ("created_at", "")],
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

    # типовые места: <root>/localization, <root>/game/localization, <root>/replace
    candidates = [root, root / "localization", root / "game" / "localization",
                  root / "localization" / "replace"]
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
    files = _list_loc_files(src_dir, lang_tag(src_lang))
    paired = sum(
        1 for p in files
        if (tgt_dir / map_relpath(
            p.relative_to(src_dir).as_posix(), src_lang, tgt_lang)).is_file()
    )
    return paired, len(files)


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
        raise FileNotFoundError(f"Папка оригинала не найдена: {src_dir}")
    if tgt_dir is None:
        tgt_dir = find_sibling_language_dir(src_dir, tgt_lang)
        if tgt_dir is None:
            raise FileNotFoundError(
                f"Не найдена папка перевода рядом с {src_dir} (ожидалась …/{tgt_lang})")
    tgt_dir = Path(tgt_dir)
    if not tgt_dir.is_dir():
        raise FileNotFoundError(f"Папка перевода не найдена: {tgt_dir}")

    src_files = _list_loc_files(src_dir, lang_tag(src_lang))
    if not src_files:
        raise FileNotFoundError(
            f"В папке {src_dir} нет файлов локализации языка «{src_lang}» "
            f"(ожидались имена вида *_l_{src_lang}.yml)")

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
        tmp_path, name=name, src_lang=src_lang, tgt_lang=tgt_lang, kind=kind)
    try:
        conn.execute("BEGIN")
        for i, path in enumerate(src_files):
            if should_cancel is not None and should_cancel():
                raise TmBuildCancelled
            rel = path.relative_to(src_dir).as_posix()
            report_progress(i, len(src_files), f"{rel} · пар: {report.pairs}")
            tgt_path = tgt_dir / map_relpath(rel, src_lang, tgt_lang)
            if not tgt_path.is_file():
                continue
            src_lf = paradox_yaml.parse_file(path)
            tgt_lf = paradox_yaml.parse_file(tgt_path)
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
        milestone("сохранение базы…")
        conn.commit()
        if has_fts_index(conn):
            # индекс с внешним содержимым не обновляется вставками сам —
            # собираем его разом в конце, это заметно быстрее построчного
            milestone("построение индекса похожих строк…")
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
        raise ValueError(
            f"Не найдено ни одной пары «оригинал — перевод».\n\n"
            f"Проверено файлов оригинала: {len(src_files)}, из них с парой в папке "
            f"перевода: {report.files}.\n"
            f"Обычно причина в том, что указан корень игры или мода, а не папки "
            f"локализации (например …\\game\\localization\\{src_lang} и "
            f"…\\localization\\{tgt_lang}).")

    try:
        out_path.unlink(missing_ok=True)
        tmp_path.replace(out_path)
    except PermissionError as e:
        tmp_path.unlink(missing_ok=True)
        raise PermissionError(
            f"Не удалось заменить файл базы: {out_path}\n\n"
            f"Скорее всего она подключена к текущему проекту — отключите её в "
            f"«Инструменты → Базы памяти переводов…» и повторите.") from e
    milestone("готово")
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

    rows = project_conn.execute(
        """SELECT en_text, ru_text, key, en_hash FROM units
           WHERE is_deleted = 0 AND en_text IS NOT NULL AND ru_text IS NOT NULL
             AND ru_text != en_text AND status IN (?, ?, ?)""",
        (Status.TRANSLATED.value, Status.REVIEWED.value, Status.CUSTOM.value),
    ).fetchall()

    conn = create_tm_database(
        out_path, name=name, src_lang=src_lang, tgt_lang=tgt_lang, kind="project-export")
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
