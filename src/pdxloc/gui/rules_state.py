"""Действующий набор правил проверки — один на всё приложение.

Проверка вызывается из трёх мест (колонка «!» таблицы, пересчёт одной строки
после правки, отчёт F6), и раньше каждое звало `qa.check_unit` без набора, то
есть всегда со встроенными значениями. Настройка обязана доходить до всех трёх
одновременно, иначе таблица и отчёт разойдутся в числах на одном и том же
проекте.

Устройство по образцу `gui/prefs.py`: значение и сигнал о смене. Слоёв два —
глобальный файл рядом с приложением и оверлей внутри файла проекта; их порядок
и правила слияния описаны в `core/qa_rules.py`.
"""
from __future__ import annotations

import json
import sqlite3

from PySide6.QtCore import QObject, Signal

from pdxloc import project as project_module
from pdxloc import settings
from pdxloc.core import qa_rules
from pdxloc.core.qa_rules import RuleSet


class _Notifier(QObject):
    changed = Signal()


notifier = _Notifier()

_global: dict = {}
_project: dict = {}
_locale: str = ""          # язык перевода открытого проекта
_ruleset: RuleSet = qa_rules.default_ruleset()


# --- чтение ---

def ruleset() -> RuleSet:
    """Набор, которым проверяются строки прямо сейчас."""
    return _ruleset


def global_overlay() -> dict:
    return dict(_global)


def project_overlay() -> dict:
    return dict(_project)


def preset() -> str:
    """Действующий пресет.

    Проектный перекрывает глобальный, но только если задан: «Свой» в проекте
    означает «без своего пресета», и глобальный при этом остаётся в силе —
    ровно так же его применяет `qa_rules.resolve`.
    """
    chosen = _project.get("preset")
    if chosen in qa_rules.PRESETS and chosen != qa_rules.CUSTOM:
        return chosen
    return qa_rules.preset_of(_global)


def locale() -> str:
    """Язык перевода открытого проекта — по нему гасятся языковые правила."""
    return _locale


def _rebuild() -> None:
    global _ruleset
    _ruleset = qa_rules.resolve(_global, _project, locale=_locale)
    notifier.changed.emit()


# --- глобальный слой ---

def load_global() -> None:
    """Прочитать файл глобальной настройки. Битый файл — не повод падать."""
    global _global
    path = settings.qa_rules_path()
    data: dict = {}
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            data = parsed
    except (OSError, ValueError):
        data = {}
    _global = data
    _rebuild()


def save_global(overlay: dict) -> None:
    global _global
    path = settings.qa_rules_path()
    _global = dict(overlay)
    try:
        if qa_rules.is_empty_overlay(_global):
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_global, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except OSError:
        pass        # настройка всё равно действует до конца сеанса
    _rebuild()


# --- слой проекта ---

def open_project(conn: sqlite3.Connection) -> None:
    global _project, _locale
    try:
        _project = project_module.get_qa_overlay(conn)
        _locale = project_module.languages(conn).tgt_locale
    except sqlite3.Error:
        _project, _locale = {}, ""
    _rebuild()


def close_project() -> None:
    global _project, _locale
    _project = {}
    _locale = ""
    _rebuild()


def save_project(conn: sqlite3.Connection, overlay: dict) -> None:
    global _project
    _project = {} if qa_rules.is_empty_overlay(overlay) else dict(overlay)
    project_module.set_qa_overlay(conn, _project or None)
    _rebuild()


def on_change(slot) -> None:
    """Подписаться на смену набора.

    Слот должен быть связанным методом QObject: такая связь сама разрывается
    при удалении виджета, а лямбда пережила бы его и обратилась к мёртвому
    C++ объекту.
    """
    notifier.changed.connect(slot)
