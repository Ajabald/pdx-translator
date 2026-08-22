"""Project files (.pdxproj) and attaching translation memory databases.

A project is a self-contained SQLite file: strings, files, translation memory,
archive. It can be put anywhere and handed to another person.

Translation memory databases (.pdxtm) are attached to the connection read-only;
the search goes through the uniting view tm_all (see attach_tm_sources).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from pdxloc import db as db_module
from pdxloc import settings
from pdxloc.core import games
from pdxloc.core.i18n import QT_TRANSLATE_NOOP, fill, translate
from pdxloc.db import init_schema, register_functions

# Priority of translation memory sources: our own translations, then exports of
# other people's projects, then the big game databases.
KIND_PRIORITY = {"project-export": 1, "import": 2, "game": 3}
KIND_LABELS = {
    "game": QT_TRANSLATE_NOOP("Project", "game database"),
    "project-export": QT_TRANSLATE_NOOP("Project", "project export"),
    "import": QT_TRANSLATE_NOOP("Project", "import"),
}


def _uri(path: Path, mode: str) -> str:
    return f"file:{quote(str(path).replace(chr(92), '/'), safe='/:')}?mode={mode}"


# --- projects ---

def create_project(
    path: Path,
    *,
    name: str,
    src_root: Path | str,
    tgt_root: Path | str = "",
    game: str = games.CK3,
    src_lang: str = "english",
    tgt_lang: str = "russian",
    src_locale: str = "",
    tgt_locale: str = "",
) -> sqlite3.Connection:
    """Create a new project file and return an open connection.

    The locales are empty by default: that means "the same as the language
    folder", and they need filling in only when translating into a language the
    game does not have.

    `tgt_root` is empty by default for the same kind of reason: a mod that has
    no translation yet has no such folder either, and inventing a path at this
    point would only be a guess. It is asked for at the first write into the mod
    and can be set later (see `set_translation_root`).
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(fill(translate(
            "Project", "The project file already exists: %1"), path))
    conn = open_project(path)
    conn.execute(
        "INSERT INTO projects (id, name, en_root, ru_root, game, src_lang, "
        "tgt_lang, src_locale, tgt_locale) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, str(src_root), str(tgt_root), game, src_lang, tgt_lang,
         src_locale, tgt_locale),
    )
    conn.commit()
    return conn


def open_project(path: Path, tm_paths: list[Path] | None = None) -> sqlite3.Connection:
    """Open a project file, apply the schema and attach the memory databases."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # uri=True is needed not only here: without it databases cannot be attached by URI
    conn = sqlite3.connect(_uri(path, "rwc"), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    # A ceiling for the journal. A scan writes the whole project in one
    # transaction, and `-wal` grew to the size of the database itself (measured
    # on vanilla HOI4: file 181 MB, journal 182 MB) — and there it lay until the
    # next write, so every opening of the project began by reading those
    # megabytes. After a checkpoint the file now truncates itself.
    conn.execute("PRAGMA journal_size_limit = 67108864")
    register_functions(conn)
    init_schema(conn)
    conn.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('format', 'pdxproj')")
    conn.commit()
    attach_tm_sources(conn, tm_paths if tm_paths is not None else project_tm_paths(conn))
    return conn


def checkpoint(conn: sqlite3.Connection) -> None:
    """Move the journal into the database and truncate it.

    Called where the work is known to be over: after a scan, after an import
    and when closing the project. SQLite does not truncate the journal by
    itself — it piles up pages, and without this a `-wal` the size of the
    database is left next to the project and read at every next opening.

    The error is swallowed deliberately: a checkpoint cannot run while somebody
    else is reading the database (an open translation memory window, a
    background counter), and that is no reason to get in the way of closing the
    project — the journal will live to the next time.
    """
    try:
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error:
        pass


def read_only_connection(path: Path) -> sqlite3.Connection:
    """A read-only connection — for background counting.

    Not `open_project`: that one turns on WAL, applies the schema and attaches
    the memory databases, while the background counter only needs to recount
    the rows without touching anything in the file the main thread has open
    right now.
    """
    conn = sqlite3.connect(_uri(Path(path), "ro"), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def project_companions(path: Path, *, with_backups: bool = False) -> list[Path]:
    """The files a project consists of on disk.

    The connection is opened in WAL mode (see open_project), so `-wal` and
    `-shm` live next to the file itself. Deleting only the main file will not
    do: the next project with the same name would pick up a foreign journal.
    """
    path = Path(path)
    files = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
    if with_backups:
        # copies made before schema migrations (db._backup_db_file) and the old-version database
        files += sorted(path.parent.glob(f"{path.name}.v*.bak"))
        files += sorted(path.parent.glob(f"{path.name}.migrated"))
    return [f for f in files if f.exists()]


@dataclass(frozen=True)
class DeleteReport:
    """What was deleted and how. `bypassed_trash` — what went past the recycle bin."""

    removed: list[Path] = field(default_factory=list)
    bypassed_trash: list[Path] = field(default_factory=list)

    def __len__(self) -> int:       # callers count files, they do not take the report apart
        return len(self.removed)


def delete_project_file(path: Path, *, with_backups: bool = False) -> DeleteReport:
    """Delete the project file together with its companions.

    Goes to the recycle bin if the system can (see core/trash). A busy file
    raises OSError — the caller is obliged to explain that to the user, because
    the reason is almost always the same: the project is still open.

    **The recycle bin does not always work**, and that has to be passed
    upwards: Windows does not put a file there if it does not fit its quota,
    and a translation project is hundreds of megabytes. The dialog before
    deleting promises the recycle bin, so the case "promised, but deleted for
    good" is obliged to reach the human instead of getting lost here. Hence
    `bypassed_trash` instead of a bare list of paths.
    """
    from pdxloc.core import trash

    report = DeleteReport()
    for target in project_companions(path, with_backups=with_backups):
        outcome = trash.remove(target)
        if outcome == "missing":
            continue
        report.removed.append(target)
        if outcome == "unlink" and trash.available():
            report.bypassed_trash.append(target)
    return report


@dataclass(frozen=True)
class ProjectLanguages:
    """The languages of a project: the game folder apart, the text language apart.

    `src_lang`/`tgt_lang` decide the folder names, the `_l_xxx` mark in the file
    name and the `l_xxx:` header — that is dictated by the game.
    `src_locale`/`tgt_locale` say what language the text is in: machine
    translation, memory database naming and the language check rules work off
    them. They coincide almost always, but not when the translation goes into a
    language the game does not have.
    """

    src_lang: str
    tgt_lang: str
    src_locale: str
    tgt_locale: str

    @property
    def split(self) -> bool:
        """Do the folder and the text language diverge — is there anything to say in the UI."""
        from pdxloc.core import languages

        return (self.src_locale != languages.default_locale(self.src_lang)
                or self.tgt_locale != languages.default_locale(self.tgt_lang))


def languages(conn: sqlite3.Connection, project_id: int = 1) -> ProjectLanguages:
    """The languages of a project with the locales filled in.

    This used to be sorted out by every consumer itself — five copies of the
    line `proj["src_lang"] if "src_lang" in keys else "english"`, and adding
    the locales would have meant a sixth and a seventh.
    """
    from pdxloc.core import languages as lang_mod

    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    keys = row.keys() if row is not None else ()

    def value(name: str, fallback: str) -> str:
        return row[name] if name in keys and row[name] else fallback

    src_lang = value("src_lang", "english")
    tgt_lang = value("tgt_lang", "russian")
    return ProjectLanguages(
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        src_locale=lang_mod.resolve_locale(src_lang, value("src_locale", "")),
        tgt_locale=lang_mod.resolve_locale(tgt_lang, value("tgt_locale", "")),
    )


def set_languages(conn: sqlite3.Connection, langs: ProjectLanguages,
                  project_id: int = 1) -> None:
    """Write the languages of the project down.

    A locale that coincides with the one derived from the folder is stored
    empty: that way the project does not grow over with values that are known
    anyway, and a change of the language folder drags the text language along
    by itself.
    """
    from pdxloc.core import languages as lang_mod

    def stored(language: str, locale: str) -> str:
        return "" if locale == lang_mod.default_locale(language) else locale

    conn.execute(
        "UPDATE projects SET src_lang = ?, tgt_lang = ?, "
        "src_locale = ?, tgt_locale = ? WHERE id = ?",
        (langs.src_lang, langs.tgt_lang,
         stored(langs.src_lang, langs.src_locale),
         stored(langs.tgt_lang, langs.tgt_locale), project_id))
    conn.commit()


def project_name(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT name FROM projects WHERE id = 1").fetchone()
    return row["name"] if row else translate("Project", "(unnamed)")


# --- the game of the project ---

def game(conn: sqlite3.Connection, project_id: int = 1) -> str:
    """The game identifier. Empty in the database means CK3: the app knew no other games."""
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None or "game" not in row.keys() or not row["game"]:
        return games.CK3
    return row["game"]


def set_game(conn: sqlite3.Connection, game_id: str, project_id: int = 1) -> None:
    conn.execute("UPDATE projects SET game = ? WHERE id = ?", (game_id, project_id))
    conn.commit()


def read_game(path: Path) -> str | None:
    """The game of a project without opening it. `None` — the file does not read as a project.

    With a read-only connection and without applying the schema: it is asked
    before opening, in time to move the file into its own pen — an open project
    holds a `-wal`, and moving it then would be too late.
    """
    try:
        conn = read_only_connection(path)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute("SELECT * FROM projects WHERE id = 1").fetchone()
        if row is None:
            return None
        return row["game"] if "game" in row.keys() and row["game"] else games.CK3
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def move_project_file(path: Path, target_dir: Path) -> Path:
    """Move the project file with its companions into another folder.

    The companions are obligatory: `-wal` and `-shm` are part of the project,
    and a file that has left without its journal will at best lose what was not
    written, and at worst pick up a foreign journal from a namesake neighbour.
    """
    path = Path(path)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    if target == path:
        return path
    if target.exists():
        raise FileExistsError(fill(translate(
            "Project", "The file already exists: %1"), target))
    for companion in project_companions(path):
        companion.rename(target_dir / companion.name)
    return target


def save_project_as(conn: sqlite3.Connection, new_path: Path) -> Path:
    """Save a copy of the project under a new path (the connection is closed by the caller)."""
    new_path = Path(new_path)
    if new_path.exists():
        raise FileExistsError(fill(translate(
            "Project", "The file already exists: %1"), new_path))
    new_path.parent.mkdir(parents=True, exist_ok=True)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # VACUUM INTO does not work inside a transaction and demands the target be absent
    conn.execute("VACUUM INTO ?", (str(new_path),))
    return new_path


# --- moving the database of former versions ---

def _safe_filename(name: str) -> str:
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if ch in bad else ch for ch in name).strip(" .")
    return cleaned or "project"


# --- translation memory databases ---

def tm_meta(path: Path, *, with_count: bool = False) -> dict[str, str] | None:
    """Read the description of a database. None if the file is not a memory database.

    The number of records is counted only on request: `COUNT(*)` goes as a full
    scan of the table (for the vanilla CK3 database that is 244,118 rows and a
    144 MB file), while the description is asked for mostly to find out "is this
    a memory database at all?" — on opening a project that is done for every
    attached database. The number has to be shown in exactly two places, and
    both of them call `list_tm_databases`.
    """
    try:
        conn = sqlite3.connect(_uri(Path(path), "ro"), uri=True)
    except sqlite3.Error:
        return None
    try:
        rows = conn.execute("SELECT key, value FROM tm_meta").fetchall()
        meta = {k: v for k, v in rows}
        if meta.get("format") != "pdxtm":
            return None
        if with_count:
            meta["entries"] = str(
                conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0])
        return meta
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def list_tm_databases(directory: Path | None = None, *,
                      game: str | None = None) -> list[tuple[Path, dict[str, str]]]:
    """The translation memory databases in a folder.

    `game` picks the pen of its own game (`Bdd\\CK3`), and the `Bdd` root gets
    in there as well: databases built before the pens appeared lie there, and
    hiding them from the human would mean declaring them lost.
    """
    if directory is not None:
        directories = [Path(directory)]
    elif game is not None:
        directories = [settings.bdd_pen(game), settings.bdd_dir()]
    else:
        directories = [settings.bdd_dir()]

    result: list[tuple[Path, dict[str, str]]] = []
    seen: set[Path] = set()
    for folder in directories:
        if not folder.is_dir():
            continue
        for p in sorted(folder.glob(f"*{settings.TM_EXT}")):
            if p in seen:
                continue
            meta = tm_meta(p, with_count=True)
            if meta is not None:
                seen.add(p)
                result.append((p, meta))
    return result


def any_tm_database() -> bool:
    """Is there at least one memory database on the machine.

    Separate from `all_tm_databases`, because the question is asked at every
    opening of a project, while the answer "yes" is visible from the very first
    file: collecting a list with descriptions and record counts for its sake
    would mean reading all the databases whole — hundreds of megabytes for
    nothing.
    """
    root = settings.bdd_dir()
    if not root.is_dir():
        return False
    folders = [root, *(p for p in root.glob("*") if p.is_dir())]
    return any(tm_meta(p) is not None
               for folder in folders
               for p in folder.glob(f"*{settings.TM_EXT}"))


def all_tm_databases() -> list[tuple[Path, dict[str, str]]]:
    """The databases of every game at once — for the question "is there any at all".

    The pens are walked one level deep: deeper down the human arranges things
    their own way, and guessing that order is not our business.
    """
    root = settings.bdd_dir()
    folders = [root, *sorted(p for p in root.glob("*") if p.is_dir())] \
        if root.is_dir() else []
    result: list[tuple[Path, dict[str, str]]] = []
    for folder in folders:
        result += list_tm_databases(folder)
    return result


def get_tm_sources(conn: sqlite3.Connection) -> list[str]:
    """The names of the attached databases (no paths — the project stays portable)."""
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = 'tm_sources'").fetchone()
    if not row or not row["value"]:
        return []
    try:
        return [str(x) for x in json.loads(row["value"])]
    except (ValueError, TypeError):
        return []


def set_tm_sources(conn: sqlite3.Connection, names: list[str]) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES ('tm_sources', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps(names, ensure_ascii=False),))
    conn.commit()


# --- the output folder: where the translation is written ---

def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM project_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO project_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def translation_root_of(value: str | None) -> Path | None:
    """The stored translation folder as a path; `None` when it is not set.

    Empty is a lawful value, not an oversight: a mod that has no translation yet
    is created without one, and the folder is asked for at the first write into
    the mod. The one thing that must never happen is `Path("")` — that is the
    current directory, and the scan would take it for the translation tree.
    """
    text = (value or "").strip()
    return Path(text) if text else None


def translation_root(conn: sqlite3.Connection, project_id: int = 1) -> Path | None:
    """The translation folder of the project; `None` when it is not set."""
    row = conn.execute(
        "SELECT ru_root FROM projects WHERE id = ?", (project_id,)).fetchone()
    return translation_root_of(row["ru_root"] if row else None)


def set_translation_root(conn: sqlite3.Connection, path: Path | str | None,
                         project_id: int = 1) -> None:
    """Write the translation folder. `None` clears it back to «not chosen»."""
    conn.execute("UPDATE projects SET ru_root = ? WHERE id = ?",
                 ("" if path is None else str(path), project_id))
    conn.commit()


def get_export_root(conn: sqlite3.Connection) -> str | None:
    """The folder the translation was written to last time.

    Stored apart from `ru_root`: that one is the import source, and writing over
    it by default means erasing the tree we read from.
    """
    return _meta(conn, "export_root")


def set_export_root(conn: sqlite3.Connection, path: Path | str) -> None:
    _set_meta(conn, "export_root", str(path))


# --- localisation format and encoding ---

def get_loc_format(conn: sqlite3.Connection) -> str | None:
    """The format of the project files: `yml` or `csv`. None — not decided yet.

    It is decided at the first scan by the contents of the tree and is taken
    from here ever after. Storing it instead of deciding anew every time is
    needed for the sake of export: the source tree may become unavailable (the
    disk unplugged, the mod removed), and the translation still has to be
    written in the format it was read in — guessing from the leftovers is too
    late.
    """
    return _meta(conn, "loc_format")


def set_loc_format(conn: sqlite3.Connection, format_id: str) -> None:
    _set_meta(conn, "loc_format", format_id)


def get_loc_encoding(conn: sqlite3.Connection) -> str | None:
    """The encoding of the translation tree. None — the format makes do with one (utf-8 with BOM).

    Needed by the old format: vanilla lies in cp1252, the Russian translation
    in cp1251, and writing it in another encoding means handing the game rubbish.
    """
    return _meta(conn, "loc_encoding")


def set_loc_encoding(conn: sqlite3.Connection, encoding: str) -> None:
    _set_meta(conn, "loc_encoding", encoding)


def get_source_encoding(conn: sqlite3.Connection) -> str | None:
    """The encoding of the **source** tree — it happens to differ from the translation one.

    It is stored separately not for symmetry: export completes a line from the
    source file (the other languages lie there), and were it to read vanilla
    cp1252 as cp1251, the French `Reconquête` would turn into `Reconquкte` —
    and silently at that, because such a string writes back perfectly well.
    """
    return _meta(conn, "loc_encoding_src")


def set_source_encoding(conn: sqlite3.Connection, encoding: str) -> None:
    _set_meta(conn, "loc_encoding_src", encoding)


def get_last_export_at(conn: sqlite3.Connection) -> str | None:
    return _meta(conn, "last_export_at")


def set_last_export_at(conn: sqlite3.Connection, when: str | None = None) -> None:
    _set_meta(conn, "last_export_at",
              when or datetime.now().strftime("%Y-%m-%d %H:%M"))


# --- one-off cleanup of strings with no translatable text ---

def get_auto_ignore_done(conn: sqlite3.Connection) -> bool:
    """Has the one-off auto-ignore of markup-only strings passed over the project.

    The cleanup runs when a project is opened and exists for the sake of
    projects created by former versions. Without this mark it would run every
    time — and what was undone with Ctrl+Z would come back at the next opening.
    An undo that is replayed behind your back teaches you not to trust undo at
    all.

    The scan neither looks at the mark nor sets it: it brings in new keys, and
    removing the tag-only ones among them is its ordinary work, not a one-off
    cleanup.
    """
    return _meta(conn, "auto_ignore_done") == "1"


def set_auto_ignore_done(conn: sqlite3.Connection) -> None:
    _set_meta(conn, "auto_ignore_done", "1")


# --- check settings: the project layer ---

def get_qa_overlay(conn: sqlite3.Connection) -> dict:
    """The edits to the rule set made for this project.

    It lives in `project_meta` and not in a table of its own: a schema migration
    for the sake of one JSON string is not needed, and the setting travels with
    the project file — exactly like the list of attached databases.
    """
    raw = _meta(conn, "qa_overlay")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def set_qa_overlay(conn: sqlite3.Connection, overlay: dict | None) -> None:
    from pdxloc.core import qa_rules

    if overlay is None or qa_rules.is_empty_overlay(overlay):
        conn.execute("DELETE FROM project_meta WHERE key = 'qa_overlay'")
        conn.commit()
        return
    _set_meta(conn, "qa_overlay", json.dumps(overlay, ensure_ascii=False))


def project_tm_paths(conn: sqlite3.Connection) -> list[Path]:
    """The paths of the enabled databases: the pen of its own game first, then the Bdd root.

    Only the file name is stored in the project — that way the project stays
    portable. Looking has to be done in two places: databases built before the
    pens appeared lie in the root, and losing them to a move of the folders is
    not on.
    """
    folders = [settings.bdd_pen(game(conn)), settings.bdd_dir()]
    paths: list[Path] = []
    for name in get_tm_sources(conn):
        for folder in folders:
            if (folder / name).is_file():
                paths.append(folder / name)
                break
    return paths


def attach_tm_sources(conn: sqlite3.Connection, tm_paths: list[Path]) -> list[str]:
    """Attach the databases read-only and rebuild the tm_all view.

    The view is temporary, that is, it lives within the connection: the
    background scanner has to call open_project itself instead of receiving
    somebody else's connect.
    """
    for row in conn.execute("PRAGMA database_list").fetchall():
        if row[1].startswith("tm"):
            conn.execute(f"DETACH DATABASE {row[1]}")
    conn.execute("DROP VIEW IF EXISTS tm_all")

    parts = [db_module.TM_VIEW_BASE]
    attached: list[str] = []
    for i, path in enumerate(tm_paths):
        path = Path(path)
        if not path.is_file():
            continue
        meta = tm_meta(path)
        if meta is None:
            continue
        alias = f"tm{i}"
        try:
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (_uri(path, "ro"),))
        except sqlite3.Error:
            continue
        origin = meta.get("name") or path.stem
        prio = KIND_PRIORITY.get(meta.get("kind", "import"), 5)
        # we make the identifiers of attached databases negative: the numbering
        # is its own in every file, and without this deleting a foreign record
        # would wipe our own with the same number
        parts.append(
            f"SELECT -(id + {(i + 1) * 10_000_000}) AS id, "
            "en_hash, en_text, ru_text, source, key, updated_at, "
            f"'{origin.replace(chr(39), chr(39) * 2)}' AS origin, 0 AS editable, "
            f"{prio} AS prio FROM {alias}.tm_entries")
        attached.append(origin)
    conn.execute("CREATE TEMP VIEW tm_all AS " + " UNION ALL ".join(parts))
    return attached


def attached_tm_paths(conn: sqlite3.Connection) -> list[Path]:
    """The files of the attached memory databases — to repeat the set in another thread.

    The `tm_all` view is temporary, that is, it lives within the connection. The
    background count over the translation memory opens its own connection and is
    obliged to gather the same set of databases anew; a list of paths is all it
    takes.
    """
    found: list[Path] = []
    for row in conn.execute("PRAGMA database_list").fetchall():
        alias, path = row[1], row[2]
        if alias.startswith("tm") and path:
            found.append(Path(path))
    return found


@dataclass
class AttachedTm:
    """An attached database for the search of similar strings."""

    alias: str            # tm0, tm1 … — the tables of the database are addressed by it
    origin: str           # the name of the database as the user sees it
    prio: int             # the priority of the source, as in tm_all
    id_offset: int        # the shift of the identifiers, to match tm_all
    has_fts: bool         # whether the index of similar strings is built


def attached_tm_bases(conn: sqlite3.Connection) -> list[AttachedTm]:
    """The attached databases with the mark "is there an index of similar strings".

    The search for similar ones goes over each database separately (the index
    lives inside it) and not through the uniting view tm_all, which is why the
    aliases themselves are needed.
    """
    from pdxloc.core import tm_import

    bases: list[AttachedTm] = []
    for row in conn.execute("PRAGMA database_list").fetchall():
        alias, path = row[1], row[2]
        if not alias.startswith("tm") or not path:
            continue
        meta = tm_meta(Path(path)) or {}
        index = int(alias[2:]) if alias[2:].isdigit() else 0
        bases.append(AttachedTm(
            alias=alias,
            origin=meta.get("name") or Path(path).stem,
            prio=KIND_PRIORITY.get(meta.get("kind", "import"), 5),
            id_offset=(index + 1) * 10_000_000,
            has_fts=tm_import.has_fts_index(conn, alias),
        ))
    return bases


