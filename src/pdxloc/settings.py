"""Application settings (QSettings) and the standard paths.

Only the environment lives in QSettings: the list of recent projects, the Bdd and
Projects folders, the window geometry. Everything of substance about a project is
stored inside the project file itself — that is what makes it possible to hand
one to another person as a single file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ORG = "pdx-translator"
APP = "pdx-translator"

# What the application was called before the rename. Needed for exactly one
# thing: adopting the previous settings once — see `adopt_previous_settings`.
PREVIOUS_ORG = "ck3-translator"
PREVIOUS_APP = "ck3-translator"

PROJECT_EXT = ".pdxproj"
TM_EXT = ".pdxtm"


def app_root() -> Path:
    """The application directory.

    In a build (PyInstaller) the sources live in a temporary folder, so we go by
    the location of the exe — otherwise the portable mode breaks.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def qsettings():
    from PySide6.QtCore import QSettings
    return QSettings(ORG, APP)


ADOPTED_KEY = "adopted_from_previous"


def previous_qsettings():
    from PySide6.QtCore import QSettings
    return QSettings(PREVIOUS_ORG, PREVIOUS_APP)


def adopt_previous_settings(target=None, source=None) -> int:
    """Adopt the settings of the previous application name, once.

    A rename changes `ORG`/`APP`, that is, the whole QSettings hive. The list of
    recent projects and the theme are a tolerable loss, but the **access keys to
    the translation services** live there too (`core/secrets.py`), and those must
    not vanish in silence: a person will not understand where a paid key went and
    will decide the application is broken. The keys are protected by DPAPI against
    the account rather than the application name, so simply copying the values is
    enough.

    Two rules, both learnt the hard way:

    * **carry over only what the new name does not have.** «The hive is empty»
      will not do as a condition: one launch is enough for the window geometry and
      the theme to land there — and the real settings would stop moving across;
    * **do it once**, and leave a mark saying so. Otherwise a setting the person
      deliberately cleared would rise again on every start.
    """
    target = target if target is not None else qsettings()
    if target.value(ADOPTED_KEY):
        return 0
    source = source if source is not None else previous_qsettings()
    taken = 0
    for key in source.allKeys():
        if target.value(key) is None:
            target.setValue(key, source.value(key))
            taken += 1
    target.setValue(ADOPTED_KEY, True)
    target.sync()
    return taken


def _get(key: str, default: str = "") -> str:
    try:
        value = qsettings().value(key, "")
    except ImportError:
        return default
    return str(value) if value else default


def _set(key: str, value: str) -> None:
    qsettings().setValue(key, value)


def bdd_dir() -> Path:
    """The folder holding the translation memory databases: game ones and project
    exports."""
    return Path(_get("bdd_dir") or app_root() / "Bdd")


def set_bdd_dir(path: Path) -> None:
    _set("bdd_dir", str(path))


def projects_dir() -> Path:
    """The default folder for project files."""
    return Path(_get("projects_dir") or app_root() / "Projects")


def projects_pen(game_id: str) -> Path:
    """The pen of a game inside the projects folder: `Projects\\CK3`.

    Pens are created as they are needed rather than all at once: six empty folders
    for somebody with one mod are litter that looks like a half-finished install.
    """
    from pdxloc.core import games
    return projects_dir() / games.folder(game_id)


def bdd_pen(game_id: str) -> Path:
    """The pen of a game among the memory databases: `Bdd\\CK3`.

    Databases of different games in one heap offer vanilla CK3 rows to a
    Victoria 3 translator — litter that looks like a match from the memory.
    """
    from pdxloc.core import games
    return bdd_dir() / games.folder(game_id)


def set_projects_dir(path: Path) -> None:
    _set("projects_dir", str(path))


# How many snapshots of overwritten files are kept per project by default. More
# are not needed: a backup insures against a bad write, it does not replace a
# version control system. The value is configured in «File → Preferences →
# Folders».
BACKUP_KEEP = 5


def backup_keep() -> int:
    """How many snapshots to keep per project.

    A function rather than a constant: as a default argument value it was computed
    when `exporter` was imported, and the setting had no effect until the
    application was restarted.
    """
    try:
        return max(0, int(_get("backup/keep") or BACKUP_KEEP))
    except ValueError:
        return BACKUP_KEEP


def qa_rules_path() -> Path:
    """The file holding the global check settings.

    Next to the application rather than in QSettings: a rule set gets carried
    between machines and shown to other people, and the Windows registry will not
    do for that. JSON rather than YAML: the application has one dependency,
    PySide6, and a second is not worth a settings file. Besides, the Paradox
    localisation format calls itself `.yml` without being YAML, and two different
    «YAML»s would confuse.
    """
    return app_root() / "qa_rules.json"


def last_browse_dir() -> str:
    """Where the user picked a folder last time; that is where we start."""
    return _get("last_browse_dir")


def set_last_browse_dir(path: Path | str) -> None:
    _set("last_browse_dir", str(path))


def backups_dir() -> Path:
    """The folder of snapshots of files overwritten when writing to the mod.

    The copies must not be put next to the localisation: the game reads every
    `*.yml` from that folder, and a backup file with an `l_russian:` header would
    be loaded on equal terms with the real one, giving duplicate keys.
    """
    return Path(_get("backups_dir") or app_root() / "backups")


def set_backups_dir(path: Path) -> None:
    _set("backups_dir", str(path))


def ensure_dirs() -> None:
    for path in (bdd_dir(), projects_dir()):
        path.mkdir(parents=True, exist_ok=True)


# --- recent projects: [{path, name, game, done, total}] ---

def recent_projects() -> list[dict]:
    raw = _get("recent_projects")
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [d for d in data if isinstance(d, dict) and d.get("path")]


def _save_recent(items: list[dict]) -> None:
    _set("recent_projects", json.dumps(items[:20], ensure_ascii=False))


def remember_project(path: Path, name: str, done: int = 0, total: int = 0,
                     game: str = "") -> None:
    """Move a project to the top of the recent list, refreshing the progress
    snapshot.

    The game is stored here rather than read from the files: the start screen
    groups the list by it, and without a snapshot it would have to open twenty
    SQLite databases on every repaint.
    """
    items = [d for d in recent_projects() if Path(d["path"]) != Path(path)]
    items.insert(0, {"path": str(path), "name": name, "game": game,
                     "done": done, "total": total})
    _save_recent(items)


def project_game_hint(item: dict) -> str:
    """The game of a project from its recent-list entry. Empty means unknown.

    Entries written by older versions carry no game, but a project lying in a pen
    speaks for itself through the folder name. We will not open the file for that:
    the list is drawn far more often than it changes.
    """
    from pdxloc.core import games

    known = str(item.get("game") or "")
    if known:
        return known
    parent = Path(str(item.get("path") or "")).parent
    return games.by_folder(parent.name) or ""


def forget_project(path: Path) -> None:
    _save_recent([d for d in recent_projects() if Path(d["path"]) != Path(path)])


def last_project_path() -> Path | None:
    raw = _get("last_project_path")
    return Path(raw) if raw else None


def set_last_project_path(path: Path | None) -> None:
    _set("last_project_path", str(path) if path else "")
