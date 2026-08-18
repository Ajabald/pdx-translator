"""Общие фикстуры: генератор синтетических деревьев локализации и in-memory БД."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Приёмочные тесты идут по настоящим деревьям локализации. Путь задаётся
# переменной PDXT_REALDATA; по умолчанию — папка над репозиторием, где эти
# деревья и лежат у автора. Прописывать сюда конкретный диск нельзя: файл
# уезжает в публичный репозиторий.
REALDATA_ROOT = Path(os.environ.get("PDXT_REALDATA") or Path(__file__).parents[2])
REALDATA_EN = REALDATA_ROOT / "localization en" / "replace" / "english"
REALDATA_RU = REALDATA_ROOT / "localization ru" / "replace" / "russian"


# Ванильное дерево HOI4 — второе живое дерево, и уже не CK3: на нём сверены
# токены §…§! и £icon и настроен пресет «HOI4 · Русский». Путь только из
# переменной PDXT_REALDATA_HOI4 (папка `localisation` установленной игры):
# угадывать, где стоит Steam, — не наше дело, а без переменной тест пропускается.
REALDATA_HOI4 = Path(os.environ["PDXT_REALDATA_HOI4"]) \
    if os.environ.get("PDXT_REALDATA_HOI4") else None


def realdata_available() -> bool:
    return REALDATA_EN.is_dir() and REALDATA_RU.is_dir()


def hoi4_realdata_available() -> bool:
    return (REALDATA_HOI4 is not None
            and (REALDATA_HOI4 / "english").is_dir()
            and (REALDATA_HOI4 / "russian").is_dir())


# Ванильная CK2 — единственное живое дерево прежнего формата (CSV). Вторая
# переменная указывает на распакованный русификатор: с ним проверяется пара
# «оригинал ↔ перевод», без него — только разбор и перезапись оригинала.
REALDATA_CK2 = Path(os.environ["PDXT_REALDATA_CK2"]) \
    if os.environ.get("PDXT_REALDATA_CK2") else None
REALDATA_CK2_RU = Path(os.environ["PDXT_REALDATA_CK2_RU"]) \
    if os.environ.get("PDXT_REALDATA_CK2_RU") else None


# Stellaris — третья живая игра. Папка `localisation` (через «s»), внутри
# папки языков; на ней сверена грамматическая система 3.6 (теги и варианты).
REALDATA_STELLARIS = Path(os.environ["PDXT_REALDATA_STELLARIS"]) \
    if os.environ.get("PDXT_REALDATA_STELLARIS") else None


def stellaris_realdata_available() -> bool:
    return (REALDATA_STELLARIS is not None
            and (REALDATA_STELLARIS / "english").is_dir()
            and (REALDATA_STELLARIS / "russian").is_dir())


def ck2_realdata_available() -> bool:
    return REALDATA_CK2 is not None and REALDATA_CK2.is_dir()


def ck2_translation_available() -> bool:
    return REALDATA_CK2_RU is not None and REALDATA_CK2_RU.is_dir()


requires_realdata = pytest.mark.realdata


@pytest.fixture
def make_tree(tmp_path):
    """Создать дерево файлов локализации с BOM.

    spec: dict относительный_путь -> текст файла (без BOM, он добавится).
    Возвращает корень дерева.
    """
    def _make(spec: dict[str, str], subdir: str = "tree") -> Path:
        root = tmp_path / subdir
        for rel, text in spec.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8-sig", newline="\n") as f:
                f.write(text)
        root.mkdir(parents=True, exist_ok=True)
        return root

    return _make


@pytest.fixture(scope="session", autouse=True)
def qsettings_fence(tmp_path_factory):
    """Забор вокруг реестра: ни один `QSettings` не пишет в куст пользователя.

    Прогон оставлял под `HKCU\\Software\\pdx-translator` геометрию окна, тему и
    список недавних проектов с путями `pytest-of-*` — мусор в настройках живого
    приложения, который человек потом видит в «Файл → Параметры».

    Двух вызовов не избежать: `setPath` для нативного формата на Windows
    игнорируется (нативный — это и есть реестр), поэтому сначала формат по
    умолчанию меняется на ini, и только тогда путь имеет смысл.

    Это именно забор, а не дорога: всё приложение ходит через
    `settings.qsettings()`, который подменяет `isolated_qsettings`. Сюда
    попадает лишь то, что подмену обошло, — `QSettings(ORG, APP)`, собранный
    напрямую. Папка обязана остаться пустой; появился файл — значит завёлся код
    мимо `settings.qsettings()`, и его надо чинить, а не радоваться забору.
    """
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        yield None
        return
    fence = tmp_path_factory.mktemp("qsettings-fence")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    for scope in (QSettings.UserScope, QSettings.SystemScope):
        QSettings.setPath(QSettings.IniFormat, scope, str(fence))
    yield fence


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path, monkeypatch):
    """Настройки приложения — в свой ini на каждый тест.

    Дорога, по которой ходит весь код: `settings.qsettings()` зовут и сам
    модуль настроек, и окна, и `core/mt` с ключами к сервисам перевода. Ini
    вместо реестра берётся не ради формата, а ради `tmp_path`: свой файл на
    тест означает, что тема или `mt/provider`, записанные соседом, не достанутся
    следующему. Заодно ключ к платному сервису не переживает прогон.

    `previous_qsettings` подменяется тем же: `adopt_previous_settings` читает
    прежний куст при каждом запуске приложения, и без подмены тест перетащил бы
    себе настоящие настройки пользователя — вместе с ключами.

    Тесты, которым нужно видеть записанное (`test_toolbar`, `test_prefs_dialog`,
    `test_welcome_dialog` и другие), ставят свою заглушку поверх — их
    `monkeypatch` идёт после этого и откатывается раньше.
    """
    from pdxloc import settings

    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        yield None
        return
    current = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    previous = QSettings(str(tmp_path / "previous.ini"), QSettings.IniFormat)
    monkeypatch.setattr(settings, "qsettings", lambda: current)
    monkeypatch.setattr(settings, "previous_qsettings", lambda: previous)
    yield current


@pytest.fixture(autouse=True)
def isolated_backups(tmp_path, monkeypatch):
    """Бэкапы записи перевода — во временную папку.

    Иначе любой тест, экспортирующий поверх существующих файлов, оставляет
    снимки в рабочей папке backups приложения.
    """
    from pdxloc import settings

    monkeypatch.setattr(settings, "backups_dir", lambda: tmp_path / "backups")


@pytest.fixture(autouse=True)
def source_language():
    """Тесты идут на языке оригинала — английском, без переводчиков.

    Ожидания в тестах сверяются с текстом, написанным в коде. Оставь тест
    ставить переводчик глобально на QApplication — и соседний тест начал бы
    получать перевод в зависимости от порядка запуска. Такие падения плавают и
    ловятся тяжелее всего, поэтому язык снимается принудительно после каждого.
    """
    from pdxloc.gui import language

    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is not None:
        language.apply(app, language.SOURCE, save=False)


@pytest.fixture(autouse=True)
def no_first_start_wizard(monkeypatch):
    """Мастер первого запуска в тестах не показывается.

    Он модальный: без этого каждый тест, создающий главное окно, вставал бы
    насмерть на `exec()`. Свой мастер проверяет `test_welcome_dialog.py` —
    там фикстура отключается явно.
    """
    from pdxloc.gui import welcome_dialog

    monkeypatch.setattr(welcome_dialog, "needed", lambda: False)


@pytest.fixture(autouse=True)
def no_reminders(monkeypatch):
    """Напоминания `ask_once` в тестах молчат и отвечают «нет».

    Тоже модальные, и повод показаться у них есть всегда: тестовый проект
    создаётся без единой базы памяти, поэтому напоминание о базах вставало
    насмерть в каждом тесте, открывающем проект. Ответ «нет» совпадает с тем,
    что `ask_once` возвращает у заглушённого вопроса, — тесты видят поведение
    пользователя, который однажды попросил не спрашивать. Своё поведение
    проверяет `test_welcome_dialog.py`, там фикстура отключается явно.
    """
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import ask

    monkeypatch.setattr(ask, "ask_once", lambda *a, **k: QMessageBox.No)


@pytest.fixture(autouse=True)
def isolated_qa_rules(tmp_path, monkeypatch):
    """Настройка проверок — во временную папку, и набор сбрасывается.

    Файл глобальных правил лежит рядом с приложением, то есть прямо в рабочей
    копии: без изоляции тест, открывающий окно правил, переписал бы настройку
    разработчика. А `gui.rules_state` держит действующий набор в модульных
    переменных — они пережили бы тест и подменили бы правила следующему.
    """
    from pdxloc import settings

    monkeypatch.setattr(settings, "qa_rules_path", lambda: tmp_path / "qa_rules.json")
    from pdxloc.gui import rules_state

    monkeypatch.setattr(rules_state, "_global", {})
    monkeypatch.setattr(rules_state, "_project", {})
    monkeypatch.setattr(rules_state, "_ruleset",
                        rules_state.qa_rules.default_ruleset())


@pytest.fixture
def db():
    from pdxloc.db import init_schema, register_functions

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    register_functions(conn)
    init_schema(conn)
    yield conn
    conn.close()
