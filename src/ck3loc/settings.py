"""Настройки приложения (QSettings) и стандартные пути.

В QSettings живёт только окружение: список недавних проектов, папки Bdd и
Projects, геометрия окон. Всё содержательное о проекте хранится внутри самого
файла проекта — так его можно передать другому человеку одним файлом.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ORG = "ck3-translator"
APP = "ck3-translator"

PROJECT_EXT = ".ck3proj"
TM_EXT = ".ck3tm"


def app_root() -> Path:
    """Каталог приложения.

    В собранном виде (PyInstaller) исходники лежат во временной папке, поэтому
    ориентируемся на местоположение exe — иначе portable-режим ломается.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_db_path() -> Path:
    """Путь к базе прежних версий (для однократного переноса в файл проекта)."""
    portable = app_root() / "ck3loc.sqlite3"
    if portable.exists():
        return portable
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / "ck3-translator" / "ck3loc.sqlite3"


def qsettings():
    from PySide6.QtCore import QSettings
    return QSettings(ORG, APP)


def _get(key: str, default: str = "") -> str:
    try:
        value = qsettings().value(key, "")
    except ImportError:
        return default
    return str(value) if value else default


def _set(key: str, value: str) -> None:
    qsettings().setValue(key, value)


def bdd_dir() -> Path:
    """Папка с базами памяти переводов (игровые и экспорты проектов)."""
    return Path(_get("bdd_dir") or app_root() / "Bdd")


def set_bdd_dir(path: Path) -> None:
    _set("bdd_dir", str(path))


def projects_dir() -> Path:
    """Папка по умолчанию для файлов проектов."""
    return Path(_get("projects_dir") or app_root() / "Projects")


def set_projects_dir(path: Path) -> None:
    _set("projects_dir", str(path))


# Сколько снимков перезаписанных файлов держим на проект. Больше не нужно:
# бэкап страхует от неудачной записи, а не заменяет систему контроля версий.
BACKUP_KEEP = 5


def last_browse_dir() -> str:
    """Где пользователь выбирал папку в прошлый раз — с этого места и начинаем."""
    return _get("last_browse_dir")


def set_last_browse_dir(path: Path | str) -> None:
    _set("last_browse_dir", str(path))


def backups_dir() -> Path:
    """Папка со снимками файлов, перезаписанных при записи перевода в мод.

    Копии нельзя класть рядом с локализацией: игра читает из её папки все
    `*.yml`, и файл-бэкап с заголовком `l_russian:` она загрузит наравне с
    настоящим, получив дубли ключей.
    """
    return Path(_get("backups_dir") or app_root() / "backups")


def set_backups_dir(path: Path) -> None:
    _set("backups_dir", str(path))


def ensure_dirs() -> None:
    for path in (bdd_dir(), projects_dir()):
        path.mkdir(parents=True, exist_ok=True)


# --- недавние проекты: [{path, name, done, total}] ---

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


def remember_project(path: Path, name: str, done: int = 0, total: int = 0) -> None:
    """Поднять проект наверх списка недавних, обновив снимок прогресса."""
    items = [d for d in recent_projects() if Path(d["path"]) != Path(path)]
    items.insert(0, {"path": str(path), "name": name, "done": done, "total": total})
    _save_recent(items)


def forget_project(path: Path) -> None:
    _save_recent([d for d in recent_projects() if Path(d["path"]) != Path(path)])


def last_project_path() -> Path | None:
    raw = _get("last_project_path")
    return Path(raw) if raw else None


def set_last_project_path(path: Path | None) -> None:
    _set("last_project_path", str(path) if path else "")
