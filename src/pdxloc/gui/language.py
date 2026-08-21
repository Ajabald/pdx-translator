"""The interface language: loading the translations and announcing a change.

Built like `gui/theme.py` — a value plus a signal, and on that signal the windows
repaint rather than wait for a restart. The reason is the same as with the theme:
the language is chosen in the first-run wizard, and «now restart the program» as
the very first screen makes a poor introduction.

The language names are written in the languages themselves. That is how the
person who needs them finds them: somebody who opened the Russian interface by
mistake looks for «English», not for «Английский».
"""
from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QTranslator, Signal

from pdxloc import settings

# Qt locale code -> what the language calls itself
LANGUAGES: dict[str, str] = {
    "en": "English",
    "ru": "Русский",
    "zh_CN": "简体中文",
}

# English is the language of the strings in the code: it needs no translation
# and has no .qm file.
SOURCE = "en"

PREFIX = "pdxloc_"


class _Notifier(QObject):
    changed = Signal()


notifier = _Notifier()

_current = SOURCE
_translators: list[QTranslator] = []


def _dir():
    # importlib.resources rather than Path(__file__): the path is right both in the
    # sources and inside a PyInstaller onedir build, just as in gui/icons.py
    return resources.files("pdxloc.gui") / "translations"


def current() -> str:
    return _current


def available() -> dict[str, str]:
    """Языки, для которых перевод действительно есть.

    Английский — всегда: это язык оригинала. Остальные показываем, только если
    рядом лежит `.qm` **с непустым содержимым**. Наличия файла мало: `lrelease`
    выдаёт его и на пустом `.ts`, и такой язык переключался бы вникуда — пункт,
    который ничего не делает, хуже отсутствующего.
    """
    found = {SOURCE: LANGUAGES[SOURCE]}
    for code, label in LANGUAGES.items():
        if code == SOURCE:
            continue
        try:
            path = _dir() / f"{PREFIX}{code}.qm"
            if not path.is_file():
                continue
        except (FileNotFoundError, ModuleNotFoundError):
            continue
        probe = QTranslator()
        if probe.load(f"{PREFIX}{code}", str(_dir())) and not probe.isEmpty():
            found[code] = label
    return found


def system_default() -> str:
    """Язык системы, если он у нас есть. Иначе английский.

    Сверяем и полный код (`zh_CN`), и его первую часть (`ru_RU` → `ru`):
    Windows отдаёт локаль с регионом, а переводы у нас по языку.
    """
    name = QLocale.system().name()          # 'ru_RU', 'zh_CN', 'en_US'
    have = available()
    if name in have:
        return name
    base = name.split("_")[0]
    for code in have:
        if code == base or code.split("_")[0] == base:
            return code
    return SOURCE


def apply(app, code: str, *, save: bool = True) -> None:
    """Переключить язык интерфейса и сообщить об этом подписчикам.

    Switching to the language already in force is not an event. A repaint costs
    a lot — the menu is rebuilt, the start screen re-read, the whole table model
    walked — and the signal has many subscribers; without this check a repeated
    call made the window rebuild itself for nothing. The same trick as in
    `prefs.set`.
    """
    global _current
    if code not in LANGUAGES:
        code = SOURCE
    if code == _current and (_translators or code == SOURCE):
        return
    _current = code

    if app is not None:
        for translator in _translators:
            app.removeTranslator(translator)
        _translators.clear()
        if code != SOURCE:
            # our own translation and Qt's stock one: without the second the dialog buttons
            # and the context menu of input fields stay English in the middle of another
            # language
            _load(app, str(_dir()), f"{PREFIX}{code}")
            qt_dir = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
            for name in ("qtbase", "qt"):
                _load(app, qt_dir, f"{name}_{code}")

    if save:
        settings.qsettings().setValue("language", code)
    notifier.changed.emit()


def _load(app, directory: str, name: str) -> None:
    """Install one translation file. We keep the reference, or Qt unloads it."""
    translator = QTranslator(app)
    if translator.load(name, directory):
        app.installTranslator(translator)
        _translators.append(translator)


def saved() -> str:
    """The chosen language. Empty means nobody has chosen yet: take the system one."""
    value = settings.qsettings().value("language", "")
    value = str(value) if value else ""
    # checked against available() rather than the list: a translation may not have
    # been shipped in the build, and silently staying on a «chosen» language with
    # no translation is a lie
    return value if value in available() else system_default()


def apply_saved(app) -> None:
    apply(app, saved(), save=False)


def on_change(slot) -> None:
    """Subscribe to a change of language.

    The slot must be a bound method of a QObject: such a connection breaks itself
    when the widget is deleted. A lambda would outlive it and reach into a dead
    C++ object.
    """
    notifier.changed.connect(slot)
