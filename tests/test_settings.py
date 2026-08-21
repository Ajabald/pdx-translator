"""The application settings: moving the hive after the rename.

The rename changed `ORG`/`APP`, that is, the whole QSettings hive. Losing the
list of recent projects and the theme is no disaster, but the **access keys to the
translation services** lie there too — and they must not vanish silently: a human
will not understand where the paid-for key has gone and will decide that the
application is broken.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

from pdxloc import settings  # noqa: E402

# A call of the constructor, not a mention in a comment or in a type annotation.
CONSTRUCTOR = re.compile(r"\bQSettings\s*\(")


@pytest.fixture
def hives(tmp_path):
    """Two hives in files next to each other, not in the user's registry.

    A real QSettings, but in ini: what is checked is the work with two hives
    exactly, and substituting a stub for it would mean checking the stub. Writing
    into the registry will not do — that is the user's machine.
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

    # the second time — no: a setting a human has reset must not rise from the dead
    source.setValue("mt/key/openai", "ещё один")
    assert settings.adopt_previous_settings(target, source) == 0
    assert target.value("mt/key/openai") is None


def test_own_settings_win_over_the_adopted_ones(hives) -> None:
    """Under the new name things may have been set up already — overwriting that will not do."""
    target, source = hives
    source.setValue("theme", "dark")
    source.setValue("mt/key/deepl", "оплаченный ключ")
    target.setValue("theme", "light")

    assert settings.adopt_previous_settings(target, source) == 1
    assert target.value("theme") == "light"
    assert target.value("mt/key/deepl") == "оплаченный ключ"


def test_one_launch_under_the_new_name_does_not_block_the_move(hives) -> None:
    """One launch is enough for the geometry and the theme to land.

    Were «the hive is not empty» to count as the mark, the real settings — and the
    keys — would never move over at all.
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
    """`QSettings` is built in one place — otherwise the tests write into the registry.

    The isolation of a run (`isolated_qsettings` in conftest) rests on the whole
    code going through `settings.qsettings()`. A `QSettings(ORG, APP)` built
    directly gets round the substitution and travels silently into the user's hive
    — that is how the window geometry, the theme and `pytest-of-*` paths ended up
    there already. A check by grep is cheaper than going through the registry
    after every run.
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
