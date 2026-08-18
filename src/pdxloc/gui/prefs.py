"""Настройки, влияющие на вид и поведение интерфейса.

`settings.py` — сырое хранилище (QSettings), и оно намеренно умеет работать без
Qt: `_get` ловит ImportError ради безоконных режимов. Здесь, наоборот, живут
значения по умолчанию, типизированные геттеры и оповещение о смене: диалог
параметров пишет сюда, а панели перерисовываются по сигналу, а не по перезапуску
приложения.

Заводить настройку без живой точки применения нельзя: мёртвая галка хуже
отсутствующей — она обещает то, чего не делает.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from pdxloc import settings

DEFAULTS: dict[str, object] = {
    "general/reopen_last": True,
    "general/first_run_done": False,
    "editor/font_family": "Consolas",
    "editor/font_size": 10,
    "editor/row_height": 22,
    "editor/cell_limit": 150,
    "editor/show_grid": False,
    "detail/highlight_changes": True,
    "detail/highlight_terms": True,
    "backup/keep": 5,
    "tm/min_score": 60,          # проценты — в UI целый спинбокс
    "tm/suggestions": 8,
    # Машинный перевод. Ключей доступа здесь нет намеренно: они по одному на
    # провайдера и хранятся защищёнными (см. `core/mt.api_key`), а `get` отдал
    # бы защищённую строку вместо ключа.
    "mt/provider": "none",
    "mt/deepl_pro": False,       # у DeepL это другой адрес, не тариф
    "mt/llm_model": "",          # пусто — умолчание провайдера
    "mt/llm_prompt": "",         # пожелания пользователя, а не договор о формате
    "mt/yandex_folder": "",      # у Yandex одного ключа не хватает
    "mt/char_budget": 4500,      # символов в одном запросе
    "mt/throttle_ms": 250,       # пауза между запросами: 150 мс упираются в лимиты
    "mt/retries": 3,             # повторы по исчерпанной квоте
    "mt/timeout_sec": 30,
    "mt/manual_separator": "===%d===",
    "mt/manual_ascii_tokens": False,   # {{N}} вместо ⟦N⟧ для ручного режима
    "export/include_machine": False,   # машинный перевод в мод — осознанный выбор
}


class _Notifier(QObject):
    changed = Signal(str)        # какой ключ поменяли


notifier = _Notifier()


def get(key: str):
    default = DEFAULTS[key]
    value = settings.qsettings().value(key, default)
    if isinstance(default, bool):
        # QSettings возвращает строку 'true'/'false' из реестра
        return value if isinstance(value, bool) else str(value).lower() == "true"
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value


def set(key: str, value) -> None:   # noqa: A001 — читается как prefs.set(...)
    if get(key) == value:
        return
    settings.qsettings().setValue(key, value)
    notifier.changed.emit(key)


def get_flag(key: str, default: bool = False) -> bool:
    """Галка, ключ которой известен не на импорте, а во время работы.

    Такие есть у напоминаний (`gui/ask.py`): имя ключа складывается из имени
    напоминания. В `DEFAULTS` их не пропишешь — `ask` импортируется позже
    самого `prefs`. Проверка «ключ обязан быть объявлен» здесь не действует,
    поэтому пользоваться этим стоит только там, где иначе никак.
    """
    value = settings.qsettings().value(key, default)
    return value if isinstance(value, bool) else str(value).lower() == "true"


def set_flag(key: str, value: bool) -> None:
    if get_flag(key) == value:
        return
    settings.qsettings().setValue(key, value)
    notifier.changed.emit(key)


def on_change(slot) -> None:
    """Подписаться на смену настройки.

    Слот должен быть связанным методом QObject: такая связь сама разрывается
    при удалении виджета. Лямбда пережила бы его и обращалась к мёртвому
    C++ объекту.
    """
    notifier.changed.connect(slot)
