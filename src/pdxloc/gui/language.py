"""Язык интерфейса: загрузка переводов и оповещение о смене.

Устроено как `gui/theme.py` — значение плюс сигнал, и по сигналу окна
перерисовываются, а не ждут перезапуска. Причина та же, что у темы: язык
выбирают в мастере первого запуска, и «а теперь перезапустите программу»
первым же экраном — плохое знакомство.

Названия языков написаны на самих языках. Так их находит тот, кому они нужны:
человек, открывший русский интерфейс по ошибке, ищет глазами «English», а не
«Английский».
"""
from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QLibraryInfo, QLocale, QObject, QTranslator, Signal

from pdxloc import settings

# код Qt-локали -> как язык называет себя сам
LANGUAGES: dict[str, str] = {
    "en": "English",
    "ru": "Русский",
    "zh_CN": "简体中文",
}

# Английский — язык строк в коде: для него перевод не нужен и файла .qm нет.
SOURCE = "en"

PREFIX = "pdxloc_"


class _Notifier(QObject):
    changed = Signal()


notifier = _Notifier()

_current = SOURCE
_translators: list[QTranslator] = []


def _dir():
    # importlib.resources, а не Path(__file__): путь верен и в исходниках, и
    # внутри onedir-сборки PyInstaller — так же, как у gui/icons.py
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

    Смена на тот же язык — не событие. Перерисовка стоит дорого (пересборка
    меню, перечитывание стартового экрана, обход всей модели таблицы), а
    подписчиков у сигнала много; без этой проверки повторный вызов заставлял
    окно перестраиваться на ровном месте. Тот же приём, что в `prefs.set`.
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
            # свой перевод и штатный перевод Qt: без второго кнопки диалогов и
            # контекстное меню полей ввода остаются английскими посреди чужого
            # интерфейса
            _load(app, str(_dir()), f"{PREFIX}{code}")
            qt_dir = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
            for name in ("qtbase", "qt"):
                _load(app, qt_dir, f"{name}_{code}")

    if save:
        settings.qsettings().setValue("language", code)
    notifier.changed.emit()


def _load(app, directory: str, name: str) -> None:
    """Поставить один файл перевода. Ссылку держим: иначе Qt его выгрузит."""
    translator = QTranslator(app)
    if translator.load(name, directory):
        app.installTranslator(translator)
        _translators.append(translator)


def saved() -> str:
    """Выбранный язык. Пусто — значит ещё не выбирали: берём язык системы."""
    value = settings.qsettings().value("language", "")
    value = str(value) if value else ""
    # сверяемся с available(), а не со списком: перевод могли не доложить в
    # сборку, и молча остаться на «выбранном» языке без перевода — враньё
    return value if value in available() else system_default()


def apply_saved(app) -> None:
    apply(app, saved(), save=False)


def on_change(slot) -> None:
    """Подписаться на смену языка.

    Слот должен быть связанным методом QObject: такая связь сама разрывается
    при удалении виджета. Лямбда пережила бы его и обратилась к мёртвому C++
    объекту.
    """
    notifier.changed.connect(slot)
