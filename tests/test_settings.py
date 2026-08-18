"""Настройки приложения: перенос куста после переименования.

Переименование сменило `ORG`/`APP`, то есть весь куст QSettings. Список
недавних проектов и тему потерять не страшно, а вот **ключи доступа к сервисам
перевода** лежат там же — и пропасть молча они не должны: человек не поймёт,
куда делся оплаченный ключ, и решит, что сломалось приложение.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

from pdxloc import settings  # noqa: E402

# Вызов конструктора, а не упоминание в комментарии или в аннотации типа.
CONSTRUCTOR = re.compile(r"\bQSettings\s*\(")


@pytest.fixture
def hives(tmp_path):
    """Два куста в файлах рядом, а не в реестре пользователя.

    Настоящий QSettings, но в ini: проверяется работа именно с двумя кустами, и
    подменять его заглушкой значило бы проверить заглушку. В реестр писать
    нельзя — это машина пользователя.
    """
    def hive(name: str) -> QSettings:
        return QSettings(str(tmp_path / f"{name}.ini"), QSettings.IniFormat)

    return hive("new"), hive("old")


def test_previous_settings_are_adopted_once(hives) -> None:
    target, source = hives
    source.setValue("mt/key/deepl", "оплаченный ключ")
    source.setValue("theme", "dark")

    assert settings.adopt_previous_settings(target, source) == 2
    assert target.value("mt/key/deepl") == "оплаченный ключ"
    assert target.value("theme") == "dark"

    # второй раз — нет: сброшенная человеком настройка не должна воскресать
    source.setValue("mt/key/openai", "ещё один")
    assert settings.adopt_previous_settings(target, source) == 0
    assert target.value("mt/key/openai") is None


def test_own_settings_win_over_the_adopted_ones(hives) -> None:
    """Под новым именем уже могли настроить — затирать это нельзя."""
    target, source = hives
    source.setValue("theme", "dark")
    source.setValue("mt/key/deepl", "оплаченный ключ")
    target.setValue("theme", "light")

    assert settings.adopt_previous_settings(target, source) == 1
    assert target.value("theme") == "light"
    assert target.value("mt/key/deepl") == "оплаченный ключ"


def test_one_launch_under_the_new_name_does_not_block_the_move(hives) -> None:
    """Хватает одного запуска, чтобы легли геометрия и тема.

    Если считать признаком «куст не пуст», настоящие настройки — и ключи —
    не переехали бы уже никогда.
    """
    target, source = hives
    target.setValue("geometry", "…")
    target.setValue("view/toolbar", True)
    source.setValue("mt/key/deepl", "оплаченный ключ")

    assert settings.adopt_previous_settings(target, source) == 1
    assert target.value("mt/key/deepl") == "оплаченный ключ"


def test_nothing_to_adopt_is_not_an_error(hives) -> None:
    target, source = hives
    assert settings.adopt_previous_settings(target, source) == 0


def test_qsettings_is_built_only_in_settings_module() -> None:
    """`QSettings` собирается в одном месте — иначе тесты пишут в реестр.

    Изоляция прогона (`isolated_qsettings` в conftest) держится на том, что
    весь код ходит через `settings.qsettings()`. Собранный напрямую
    `QSettings(ORG, APP)` подмену обойдёт и молча уедет в куст пользователя —
    так там уже оказались геометрия окна, тема и пути `pytest-of-*`. Проверка
    грепом дешевле, чем сверять реестр после каждого прогона.
    """
    src = Path(settings.__file__).resolve().parent
    hits = [
        f"{path.relative_to(src).as_posix()}:{n}: {line.strip()}"
        for path in sorted(src.rglob("*.py"))
        if path.name != "settings.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if CONSTRUCTOR.search(line)
    ]
    assert not hits, (
        "QSettings собирается мимо settings.qsettings() — в тестах это запись "
        "в настоящий реестр:\n" + "\n".join(hits))
