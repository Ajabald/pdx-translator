"""Settings that shape how the interface looks and behaves.

`settings.py` is the raw store (QSettings), and it deliberately works without Qt:
`_get` catches ImportError for the windowless modes. Here, by contrast, live the
defaults, the typed getters and the change notification: the preferences dialog
writes here, and the panels repaint on a signal rather than on a restart of the
application.

A setting must not be added without a live point where it applies: a dead
checkbox is worse than a missing one, because it promises what it does not do.
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
    "tm/min_score": 60,          # a percentage; in the UI it is an integer spin box
    "tm/suggestions": 8,
    # Machine translation. The access keys are deliberately not here: there is one
    # per provider and they are stored protected (see `core/mt.api_key`), while
    # `get` would hand back the protected string instead of the key.
    "mt/provider": "none",
    "mt/deepl_pro": False,       # with DeepL this is another address, not a plan
    "mt/llm_model": "",          # empty means the provider's own default
    "mt/llm_prompt": "",         # the user's wishes, not the format contract
    "mt/yandex_folder": "",      # with Yandex a key alone is not enough
    "mt/char_budget": 4500,      # characters in a single request
    "mt/throttle_ms": 250,       # pause between requests: 150 ms runs into the limits
    "mt/retries": 3,             # retries after an exhausted quota
    "mt/timeout_sec": 30,
    "mt/manual_separator": "===%d===",
    "mt/manual_ascii_tokens": False,   # {{N}} instead of ⟦N⟧ for the manual route
    "export/include_machine": False,   # machine translation into the mod is a deliberate choice
}


class _Notifier(QObject):
    changed = Signal(str)        # which key was changed


notifier = _Notifier()


def get(key: str):
    default = DEFAULTS[key]
    value = settings.qsettings().value(key, default)
    if isinstance(default, bool):
        # QSettings returns the string 'true'/'false' from the registry
        return value if isinstance(value, bool) else str(value).lower() == "true"
    if isinstance(default, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return value


def set(key: str, value) -> None:   # noqa: A001 — it reads as prefs.set(...)
    if get(key) == value:
        return
    settings.qsettings().setValue(key, value)
    notifier.changed.emit(key)


def get_flag(key: str, default: bool = False) -> bool:
    """A flag whose key is known at run time rather than at import time.

    The reminders have such keys (`gui/ask.py`): the key name is built from the
    reminder name. They cannot be listed in `DEFAULTS` — `ask` is imported later
    than `prefs` itself. The «a key must be declared» check does not apply here,
    so this is worth using only where there is no other way.
    """
    value = settings.qsettings().value(key, default)
    return value if isinstance(value, bool) else str(value).lower() == "true"


def set_flag(key: str, value: bool) -> None:
    if get_flag(key) == value:
        return
    settings.qsettings().setValue(key, value)
    notifier.changed.emit(key)


def on_change(slot) -> None:
    """Subscribe to a change of a setting.

    The slot must be a bound method of a QObject: such a connection breaks itself
    when the widget is deleted. A lambda would outlive it and reach into a dead
    C++ object.
    """
    notifier.changed.connect(slot)
