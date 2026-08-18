"""Спека сборки обещает файлы и версию — обещания проверяются здесь.

Проверять важно потому, что ошибку в спеке видно только на сборке релиза,
то есть уже по тегу, когда job `build` краснеет у всех на виду.
"""
from __future__ import annotations


def test_the_spec_builds_a_version_resource_from_the_real_version() -> None:
    """Свойства exe собираются из `__version__`, а не переписываются руками.

    Продублированная версия разъезжается с настоящей на первом же выпуске, и
    заметить это некому: вкладку «Подробно» никто не открывает, пока она не
    понадобится. Здесь заголовок спеки выполняется и сверяется с пакетом —
    если кто-то впишет число литералом, тест это увидит.
    """
    from pathlib import Path

    from pdxloc import COPYRIGHT, __version__

    root = Path(__file__).resolve().parents[1]
    head = (root / "pdx-translator.spec").read_text(
        encoding="utf-8").split("a = Analysis(")[0]
    namespace: dict = {}
    exec(compile(head, "spec", "exec"), namespace)   # noqa: S102 — свой же файл

    assert namespace["VERSION"] == __version__
    assert namespace["COPYRIGHT"] == COPYRIGHT
    major, minor, patch, _ = namespace["FILEVERS"]
    assert f"{major}.{minor}.{patch}" == __version__
    rendered = str(namespace["version_info"])
    assert __version__ in rendered
    assert "PDX Translator" in rendered


def test_the_spec_points_at_a_real_icon_file() -> None:
    """Спека обещает `.ico` — файл обязан существовать.

    Иначе PyInstaller упадёт на сборке релиза, а узнаем мы об этом уже по тегу,
    когда job `build` покраснеет у всех на виду.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = (root / "pdx-translator.spec").read_text(encoding="utf-8")
    found = re.search(r'^\s*icon="([^"]+)"', spec, re.M)
    assert found, "в спеке не задана иконка"
    assert (root / found.group(1)).is_file(), (
        f"спека ссылается на {found.group(1)}, а файла нет")
