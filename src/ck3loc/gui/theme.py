"""Цветовые темы интерфейса.

Все цвета приложения собраны здесь, в двух наборах. Раньше они были рассыпаны
по модулям (`core/statuses.py`, `gui/highlighter.py`, модель таблицы) и
рассчитаны только на светлый фон: на тёмном подсветка разметки и заливка
статусов становились нечитаемыми.

Светлый набор — ровно те значения, что были до появления тем, чтобы привычный
вид не поехал. Смена темы применяется на лету: подписчики получают сигнал
`notifier.changed` и перерисовываются.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette

from ck3loc.core.statuses import Status

LIGHT = "light"
DARK = "dark"
THEME_LABELS = {LIGHT: "Светлая", DARK: "Тёмная"}

_LIGHT: dict[str, str] = {
    "text": "#202020",
    "hint": "#555555",
    # заливка строк таблицы по статусу
    f"status.{Status.UNTRANSLATED}": "#f8d0d0",
    f"status.{Status.AUTO}": "#fff3c4",
    f"status.{Status.TRANSLATED}": "#d6f0d6",
    f"status.{Status.REVIEWED}": "#b2e0c8",
    f"status.{Status.STALE}": "#ffdcae",
    f"status.{Status.IGNORED}": "#dde3e8",
    f"status.{Status.CUSTOM}": "#e2d5f1",
    "chip.text": "#202020",
    "chip.border": "#909090",
    "chip.border.active": "#303030",
    # глифы quick-колонок
    "quick.reviewed": "#2e7d32",
    "quick.translated": "#c62828",
    "quick.custom": "#7b1fa2",
    "quick.ignored": "#546e7a",
    "quick.disabled": "#c8c8c8",
    # характер правки оригинала
    "change.cosmetic": "#8d6e63",
    "change.meaningful": "#e65100",
    # замечания проверки
    "issue.error": "#c62828",
    "issue.warning": "#ef6c00",
    # подсветка разметки CK3
    "markup.bracket": "#1857c3",
    "markup.dollar": "#8017c9",
    "markup.icon": "#9a7a00",
    "markup.format": "#3e7d47",
    "markup.escape": "#c86a1f",
    # изменения оригинала
    "diff.insert": "#c8f0c8",
    "diff.delete": "#f6c8c8",
}

_DARK: dict[str, str] = {
    "text": "#e8e8e8",
    "hint": "#a0a0a0",
    f"status.{Status.UNTRANSLATED}": "#4d2b2b",
    f"status.{Status.AUTO}": "#4a4222",
    f"status.{Status.TRANSLATED}": "#28402b",
    f"status.{Status.REVIEWED}": "#1f4739",
    f"status.{Status.STALE}": "#4d3b1f",
    f"status.{Status.IGNORED}": "#343b41",
    f"status.{Status.CUSTOM}": "#3b3050",
    "chip.text": "#e8e8e8",
    "chip.border": "#6a6a6a",
    "chip.border.active": "#d0d0d0",
    "quick.reviewed": "#71c476",
    "quick.translated": "#ef7070",
    "quick.custom": "#c48ee0",
    "quick.ignored": "#9fb3bf",
    "quick.disabled": "#5a5a5a",
    "change.cosmetic": "#c0a89f",
    "change.meaningful": "#ffa347",
    "issue.error": "#ff8080",
    "issue.warning": "#ffb14d",
    "markup.bracket": "#7dabf5",
    "markup.dollar": "#c791f2",
    "markup.icon": "#dcbb52",
    "markup.format": "#83cd91",
    "markup.escape": "#f2a56c",
    "diff.insert": "#2d5633",
    "diff.delete": "#5d2f2f",
}

_PALETTES = {LIGHT: _LIGHT, DARK: _DARK}


class _Notifier(QObject):
    changed = Signal()


notifier = _Notifier()

_current = LIGHT


def current() -> str:
    return _current


def is_dark() -> bool:
    return _current == DARK


def colors() -> dict[str, str]:
    return _PALETTES[_current]


def color(key: str) -> str:
    """Цвет по имени. Отсутствующее имя — ошибка разработчика, не пользователя."""
    return _PALETTES[_current][key]


def qcolor(key: str) -> QColor:
    return QColor(color(key))


def status_color(status: Status | str) -> str:
    return color(f"status.{Status(status)}")


def _dark_palette() -> QPalette:
    """Тёмная палитра Qt: без неё меню и поля остались бы светлыми."""
    bg = QColor("#2b2b2b")
    base = QColor("#232323")
    text = QColor(_DARK["text"])
    p = QPalette()
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, text)
    p.setColor(QPalette.Base, base)
    p.setColor(QPalette.AlternateBase, bg)
    p.setColor(QPalette.ToolTipBase, QColor("#3a3a3a"))
    p.setColor(QPalette.ToolTipText, text)
    p.setColor(QPalette.Text, text)
    p.setColor(QPalette.Button, bg)
    p.setColor(QPalette.ButtonText, text)
    p.setColor(QPalette.BrightText, QColor("#ff6b6b"))
    p.setColor(QPalette.Link, QColor("#7dabf5"))
    p.setColor(QPalette.Highlight, QColor("#3d6ea5"))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    disabled = QColor("#7a7a7a")
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
        p.setColor(QPalette.Disabled, role, disabled)
    return p


def apply_theme(app, name: str, *, save: bool = True) -> None:
    """Переключить тему приложения и сообщить об этом подписчикам."""
    global _current
    if name not in _PALETTES:
        name = LIGHT
    _current = name
    if app is not None:
        app.setPalette(_dark_palette() if name == DARK
                       else app.style().standardPalette())
    if save:
        from ck3loc import settings

        settings.qsettings().setValue("theme", name)
    notifier.changed.emit()


def saved_theme() -> str:
    from ck3loc import settings

    value = settings.qsettings().value("theme", LIGHT)
    return value if value in _PALETTES else LIGHT


def apply_saved(app) -> None:
    """Восстановить тему, выбранную в прошлый раз."""
    apply_theme(app, saved_theme(), save=False)


def on_change(slot) -> None:
    """Подписаться на смену темы.

    Слот должен быть связанным методом QObject: такая связь сама разрывается
    при удалении виджета. Лямбда пережила бы его и обращалась к мёртвому C++
    объекту.
    """
    notifier.changed.connect(slot)
