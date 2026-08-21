"""Building a release: the spec, the icon and the description.

Checking matters because an error here shows only at the build itself, that is,
already on a tag, when the `build` job goes red in front of everyone, while the
description of a release gets edited once in the life of an issue at all.
"""
from __future__ import annotations

import re


def test_the_spec_builds_a_version_resource_from_the_real_version() -> None:
    """The properties of the exe are assembled from `__version__`, not rewritten by hand.

    A duplicated version parts ways with the real one at the very first release,
    and there is nobody to notice: nobody opens the «Details» tab until they need
    it. Here the head of the spec is executed and checked against the package — if
    somebody writes the number as a literal, the test will see it.
    """
    from pathlib import Path

    from pdxloc import COPYRIGHT, __version__

    root = Path(__file__).resolve().parents[1]
    head = (root / "pdx-translator.spec").read_text(
        encoding="utf-8").split("a = Analysis(")[0]
    namespace: dict = {}
    exec(compile(head, "spec", "exec"), namespace)   # noqa: S102 — a file of our own

    assert namespace["VERSION"] == __version__
    assert namespace["COPYRIGHT"] == COPYRIGHT
    major, minor, patch, _ = namespace["FILEVERS"]
    assert f"{major}.{minor}.{patch}" == __version__
    rendered = str(namespace["version_info"])
    assert __version__ in rendered
    assert "PDX Translator" in rendered


def test_the_spec_points_at_a_real_icon_file() -> None:
    """The spec promises an `.ico` — the file is obliged to exist.

    Otherwise PyInstaller falls over at the release build, and we learn about it
    already on a tag, when the `build` job goes red in front of everyone.
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
    """The link to the archive in the release description holds the version — so it goes stale.

    Exactly like «15 built-in rules» in the README: the text stays right to the
    eye while it leads to the file of the past issue, and a human downloads the
    wrong thing.
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
    """A file without a link from the workflow is just text nobody will see."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "body_path: RELEASE_NOTES.md" in workflow


def test_the_installer_stays_out_of_program_files() -> None:
    """The installer is obliged to install for the user, not into Program Files.

    The application keeps `Bdd`, `Projects`, `backups`, `qa_rules.json` and the log
    next to itself (`settings.app_root`). An ordinary user must not write into
    Program Files, and all of that would break silently. Should somebody change
    `PrivilegesRequired` — the test will see it.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss


def test_the_installer_does_not_delete_translator_work() -> None:
    """Uninstalling must not carry off the folders with the translator's work.

    `[UninstallDelete]` must not be in the script at all: the memory databases, the
    projects and the backups of translations are months of somebody's labour, and
    there is nowhere to bring them back from.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "[UninstallDelete]" not in iss


def test_the_installer_version_comes_from_outside() -> None:
    """The version comes as a parameter, not as a third copy in the script."""
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


def test_the_uninstaller_speaks_up_about_kept_data() -> None:
    """A folder left behind looks like an unfinished uninstall — it has to be explained.

    We do not touch the data (see the test above), but keeping quiet about it will
    not do: a human sees the folder in place and does not understand whether the
    uninstall worked at all.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "CurUninstallStepChanged" in iss
    for lang in ("en", "ru"):
        assert f"{lang}.DataKept=" in iss, f"нет сообщения на {lang}"


def test_the_uninstaller_stays_silent_when_asked_to() -> None:
    """In silent mode a window must not be shown — there is nobody to close it.

    Without this proviso `/VERYSILENT` would hang forever, and that is exactly how
    uninstalling is done from scripts and at an update.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer.iss").read_text(encoding="utf-8")
    assert "not UninstallSilent" in iss
