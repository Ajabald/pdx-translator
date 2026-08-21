"""Common fixtures: a generator of synthetic localisation trees and an in-memory DB."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# The acceptance tests go over real localisation trees. The path is set by the
# variable PDXT_REALDATA; by default it is the folder above the repository, which
# is where those trees lie for the author. Writing a particular disk in here will
# not do: the file travels to a public repository.
REALDATA_ROOT = Path(os.environ.get("PDXT_REALDATA") or Path(__file__).parents[2])
REALDATA_EN = REALDATA_ROOT / "localization en" / "replace" / "english"
REALDATA_RU = REALDATA_ROOT / "localization ru" / "replace" / "russian"


# The vanilla HOI4 tree — the second live tree, and no longer CK3: the tokens
# §…§! and £icon were checked on it and the preset «HOI4 · Русский» was set up.
# The path comes only from the variable PDXT_REALDATA_HOI4 (the `localisation`
# folder of the installed game): guessing where Steam stands is not our business,
# and without the variable the test is skipped.
REALDATA_HOI4 = Path(os.environ["PDXT_REALDATA_HOI4"]) \
    if os.environ.get("PDXT_REALDATA_HOI4") else None


def realdata_available() -> bool:
    return REALDATA_EN.is_dir() and REALDATA_RU.is_dir()


def hoi4_realdata_available() -> bool:
    return (REALDATA_HOI4 is not None
            and (REALDATA_HOI4 / "english").is_dir()
            and (REALDATA_HOI4 / "russian").is_dir())


# Vanilla CK2 — the only live tree of the former format (CSV). The second variable
# points at the unpacked Russian pack: with it the pair «source ↔ translation» is
# checked, without it only the parsing and rewriting of the source.
REALDATA_CK2 = Path(os.environ["PDXT_REALDATA_CK2"]) \
    if os.environ.get("PDXT_REALDATA_CK2") else None
REALDATA_CK2_RU = Path(os.environ["PDXT_REALDATA_CK2_RU"]) \
    if os.environ.get("PDXT_REALDATA_CK2_RU") else None


# Stellaris — the third live game. The folder `localisation` (through an «s»),
# with the language folders inside; the grammar system of 3.6 (the tags and the
# variants) was checked on it.
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
    """Create a tree of localisation files with a BOM.

    spec: dict relative_path -> the text of the file (without the BOM, it gets
    added). Returns the root of the tree.
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
    """A fence around the registry: not one `QSettings` writes into the user's hive.

    A run used to leave the window geometry, the theme and the list of recent
    projects with `pytest-of-*` paths under `HKCU\\Software\\pdx-translator` —
    rubbish in the settings of the live application, which a human then sees in
    "File → Preferences".

    The two calls cannot be avoided: `setPath` for the native format on Windows
    is ignored (native is the registry itself), so the default format is changed
    to ini first, and only then does the path make sense.

    This is a fence and not a road: the whole application goes through
    `settings.qsettings()`, which `isolated_qsettings` substitutes. Only what got
    round the substitution lands here — a `QSettings(ORG, APP)` built directly.
    The folder is obliged to stay empty; if a file appeared, code has grown up
    past `settings.qsettings()`, and it is the code that has to be mended, not
    the fence admired.
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
    """The application settings — into an ini of their own for every test.

    The road the whole code walks: `settings.qsettings()` is called by the
    settings module itself, and by the windows, and by `core/mt` with the keys to
    the translation services. Ini instead of the registry is taken not for the
    sake of the format but for the sake of `tmp_path`: a file of one's own per
    test means that the theme or the `mt/provider` written by a neighbour will
    not reach the next one. And a key to a paid service does not outlive the run.

    `previous_qsettings` is substituted by the same thing:
    `adopt_previous_settings` reads the former hive at every start of the
    application, and without the substitution a test would drag the real settings
    of the user over to itself — keys and all.

    The tests that need to see what was written (`test_toolbar`,
    `test_prefs_dialog`, `test_welcome_dialog` and others) put a stub of their
    own on top — their `monkeypatch` comes after this one and rolls back earlier.
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
    """The backups of a translation write — into a temporary folder.

    Otherwise any test that exports over existing files leaves snapshots in the
    working backups folder of the application.
    """
    from pdxloc import settings

    monkeypatch.setattr(settings, "backups_dir", lambda: tmp_path / "backups")


@pytest.fixture(autouse=True)
def source_language():
    """The tests run in the language of the original — English, no translators.

    The expectations in the tests are checked against the text written in the
    code. Leave a test to set a translator globally on the QApplication — and a
    neighbouring test would start getting a translation depending on the order of
    the run. Such failures float and are the hardest of all to catch, so the
    language is taken off by force after every one.
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
    """The first-start wizard is not shown in the tests.

    It is modal: without this every test that creates the main window would stand
    dead on `exec()`. The wizard itself is checked by `test_welcome_dialog.py` —
    there the fixture is switched off explicitly.
    """
    from pdxloc.gui import welcome_dialog

    monkeypatch.setattr(welcome_dialog, "needed", lambda: False)


@pytest.fixture(autouse=True)
def no_reminders(monkeypatch):
    """The `ask_once` reminders keep quiet in the tests and answer "no".

    They are modal too, and they always have a reason to show up: a test project
    is created without a single memory database, so the reminder about databases
    stood dead in every test that opens a project. The answer "no" coincides with
    what `ask_once` returns for a silenced question — the tests see the behaviour
    of a user who once asked not to be bothered. The behaviour itself is checked
    by `test_welcome_dialog.py`, where the fixture is switched off explicitly.
    """
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import ask

    monkeypatch.setattr(ask, "ask_once", lambda *a, **k: QMessageBox.No)


@pytest.fixture(autouse=True)
def isolated_qa_rules(tmp_path, monkeypatch):
    """The check setup — into a temporary folder, and the set is reset.

    The file of global rules lies next to the application, that is, right in the
    working copy: without isolation a test that opens the rules window would
    overwrite the developer's setting. And `gui.rules_state` keeps the set in
    force in module variables — they would outlive the test and substitute the
    rules for the next one.
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
