"""Настройки приложения (QSettings) и стандартные пути.

В QSettings живёт только окружение: список недавних проектов, папки Bdd и
Projects, геометрия окон. Всё содержательное о проекте хранится внутри самого
файла проекта — так его можно передать другому человеку одним файлом.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ORG = "pdx-translator"
APP = "pdx-translator"

# Как приложение звалось до переименования. Нужно ровно затем, чтобы один раз
# перенять прежние настройки — см. `adopt_previous_settings`.
PREVIOUS_ORG = "ck3-translator"
PREVIOUS_APP = "ck3-translator"

PROJECT_EXT = ".pdxproj"
TM_EXT = ".pdxtm"


def app_root() -> Path:
    """Каталог приложения.

    В собранном виде (PyInstaller) исходники лежат во временной папке, поэтому
    ориентируемся на местоположение exe — иначе portable-режим ломается.
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
    """Однократно перенять настройки прежнего имени приложения.

    Переименование меняет `ORG`/`APP`, то есть весь куст QSettings. Список
    недавних проектов и тема — потеря терпимая, а вот **ключи доступа к сервисам
    перевода** лежат там же (`core/secrets.py`), и пропасть молча они не должны:
    человек не поймёт, куда делся оплаченный ключ, и решит, что сломалось
    приложение. Ключи защищены DPAPI по учётной записи, а не по имени
    приложения, поэтому простого копирования значений достаточно.

    Два правила, и оба из грабель:

    * **переносим только то, чего под новым именем нет.** «Куст пуст» не годится
      как условие: хватает одного запуска, чтобы туда легли геометрия окна и
      тема, — и настоящие настройки перестали бы переезжать;
    * **делаем это один раз**, о чём остаётся отметка. Иначе настройка, которую
      человек сознательно сбросил, воскресала бы при каждом запуске.
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
    """Папка с базами памяти переводов (игровые и экспорты проектов)."""
    return Path(_get("bdd_dir") or app_root() / "Bdd")


def set_bdd_dir(path: Path) -> None:
    _set("bdd_dir", str(path))


def projects_dir() -> Path:
    """Папка по умолчанию для файлов проектов."""
    return Path(_get("projects_dir") or app_root() / "Projects")


def projects_pen(game_id: str) -> Path:
    """Загон игры внутри папки проектов: `Projects\\CK3`.

    Загоны заводятся по мере надобности, а не все сразу: шесть пустых папок у
    человека с одним модом — мусор, который выглядит как незаконченная установка.
    """
    from pdxloc.core import games
    return projects_dir() / games.folder(game_id)


def bdd_pen(game_id: str) -> Path:
    """Загон игры среди баз памяти: `Bdd\\CK3`.

    Базы разных игр в одной куче подсказывают ванильные строки CK3 переводчику
    Victoria 3 — мусор, который выглядит как совпадение из памяти.
    """
    from pdxloc.core import games
    return bdd_dir() / games.folder(game_id)


def set_projects_dir(path: Path) -> None:
    _set("projects_dir", str(path))


# Сколько снимков перезаписанных файлов держим на проект по умолчанию. Больше
# не нужно: бэкап страхует от неудачной записи, а не заменяет систему контроля
# версий. Значение настраивается в «Файл → Параметры → Папки».
BACKUP_KEEP = 5


def backup_keep() -> int:
    """Сколько снимков хранить на проект.

    Функция, а не константа: как значение аргумента по умолчанию оно
    вычислялось на импорте `exporter`, и настройка не действовала до
    перезапуска приложения.
    """
    try:
        return max(0, int(_get("backup/keep") or BACKUP_KEEP))
    except ValueError:
        return BACKUP_KEEP


def qa_rules_path() -> Path:
    """Файл с глобальной настройкой проверок.

    Рядом с приложением, а не в QSettings: набор правил переносят между
    машинами и показывают друг другу, а реестр Windows для этого не годится.
    JSON, а не YAML: единственная зависимость приложения — PySide6, и заводить
    вторую ради файла настроек не стоит. К тому же формат локализации Paradox
    сам зовётся `.yml`, не будучи YAML, — два разных «YAML» путали бы.
    """
    return app_root() / "qa_rules.json"


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


# --- недавние проекты: [{path, name, game, done, total}] ---

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
    """Поднять проект наверх списка недавних, обновив снимок прогресса.

    Игра хранится здесь, а не читается из файлов: стартовый экран группирует по
    ней список, и без снимка ему пришлось бы открывать двадцать баз SQLite на
    каждую перерисовку.
    """
    items = [d for d in recent_projects() if Path(d["path"]) != Path(path)]
    items.insert(0, {"path": str(path), "name": name, "game": game,
                     "done": done, "total": total})
    _save_recent(items)


def project_game_hint(item: dict) -> str:
    """Игра проекта по записи списка недавних. Пусто — неизвестна.

    Записи прежних версий игры не содержат, но проект, лежащий в загоне, о себе
    говорит сам — по имени папки. Открывать ради этого файл не станем: список
    рисуется куда чаще, чем меняется.
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
