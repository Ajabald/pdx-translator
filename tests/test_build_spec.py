"""Сборка релиза: спека, иконка и описание.

Проверять важно потому, что ошибку здесь видно только на самой сборке, то
есть уже по тегу, когда job `build` краснеет у всех на виду, а описание
релиза правится и вовсе один раз в жизни выпуска.
"""
from __future__ import annotations

import re


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


def test_release_notes_point_at_the_current_version() -> None:
    """Ссылка на архив в описании релиза содержит версию — значит протухает.

    Ровно как «15 встроенных правил» в README: текст остаётся верным на вид, а
    ведёт на файл прошлого выпуска, и человек скачивает не то.
    """
    from pathlib import Path

    from pdxloc import __version__

    root = Path(__file__).resolve().parents[1]
    notes = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert f"pdx-translator-v{__version__}.zip" in notes, (
        f"в RELEASE_NOTES.md нет ссылки на архив v{__version__}")
    stale = re.findall(r"pdx-translator-v(\d+\.\d+\.\d+)\.zip", notes)
    assert set(stale) == {__version__}, (
        f"описание ссылается на чужие версии: {sorted(set(stale) - {__version__})}")


def test_the_workflow_uses_the_release_notes() -> None:
    """Файл без ссылки из workflow — просто текст, который никто не увидит."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "body_path: RELEASE_NOTES.md" in workflow


def test_the_installer_stays_out_of_program_files() -> None:
    """Установщик обязан ставить для пользователя, а не в Program Files.

    Приложение держит `Bdd`, `Projects`, `backups`, `qa_rules.json` и лог рядом
    с собой (`settings.app_root`). В Program Files обычному пользователю писать
    нельзя, и всё это молча сломалось бы. Поменяй кто-нибудь `PrivilegesRequired`
    — тест это увидит.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss


def test_the_installer_does_not_delete_translator_work() -> None:
    """Удаление не должно уносить папки с работой переводчика.

    `[UninstallDelete]` в скрипте быть не должно вовсе: базы памяти, проекты и
    резервные копии переводов — месяцы чужого труда, и вернуть их неоткуда.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "[UninstallDelete]" not in iss


def test_the_installer_version_comes_from_outside() -> None:
    """Версия приходит параметром, а не третьей копией в скрипте."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "#define AppVersion" not in iss, "версия вписана в скрипт — разъедется"
    assert "AppVersion={#AppVersion}" in iss


def test_the_workflow_builds_and_attaches_the_installer() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "installer.iss" in workflow, "установщик не собирается"
    assert "pdx-translator-setup-*.exe" in workflow, "установщик не прикладывается"
