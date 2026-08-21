"""A change of language redraws the window instead of demanding a restart.

The whole chain is checked as one: a real `.qm` is built, slipped in instead of
the regular translations folder and switched on through `language.apply`.
Checking by substituting `translate` would be self-deception — it would leave out
exactly the places where things break: the loading of the QTranslator and the
rebuilding of the menu.

There are six long-livers (the menu, the toolbar, the screens, the table header,
the chips, the context bar), and each is obliged to refresh: the dialogs are
created anew at opening and pick the language up themselves, while these do not.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import actions as actions_spec  # noqa: E402
from pdxloc.gui import language, units_model  # noqa: E402
from pdxloc.gui.units_model import COL_KEY  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'

def build_translations(root: Path, pairs: dict[str, dict[str, str]]) -> None:
    """Build a real .qm out of the pairs «context → {original: translation}»."""
    body = []
    for context, table in pairs.items():
        messages = "".join(
            f"<message><source>{escape(source)}</source>"
            f"<translation>{escape(target)}</translation></message>"
            for source, target in table.items())
        body.append(f"<context><name>{context}</name>{messages}</context>")
    ts = root / f"{language.PREFIX}ru.ts"
    ts.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>'
        f'<TS version="2.1" language="ru">{"".join(body)}</TS>',
        encoding="utf-8")
    lrelease = Path(settings.app_root()) / ".venv" / "Scripts" / "pyside6-lrelease.exe"
    tool = str(lrelease) if lrelease.exists() else "pyside6-lrelease"
    result = subprocess.run(
        [tool, str(ts), "-qm", str(root / f"{language.PREFIX}ru.qm")],
        capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip(f"pyside6-lrelease недоступен: {result.stderr}")


@pytest.fixture
def translate_ui(tmp_path, monkeypatch):
    """Translate the named strings of the live interface with made-up words.

    The originals are taken **from the code itself** and not copied into the test:
    the interface strings are still moving to English, and a hard-coded list would
    have to be mended after every module — and it would quietly stop checking
    something while staying syntactically right.
    """
    root = tmp_path / "translations"
    root.mkdir()
    monkeypatch.setattr(language, "_dir", lambda: root)

    def _apply(pairs: dict[str, dict[str, str]]):
        build_translations(root, pairs)
        language.apply(QApplication.instance(), "ru", save=False)

    return _apply


@pytest.fixture
def window(qtbot, tmp_path, make_tree, monkeypatch):
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    conn.close()

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.open_project(path)
    return win


def menu_titles(win) -> list[str]:
    return [a.text() for a in win.menuBar().actions()]


def test_menu_bar_follows_the_language(window, translate_ui) -> None:
    win = window
    file_menu = actions_spec.MENU[0][0]
    assert file_menu in menu_titles(win)

    translate_ui({"MainWindow": {file_menu: "ФАЙЛ-ПЕРЕВЕДЁН"}})
    assert "ФАЙЛ-ПЕРЕВЕДЁН" in menu_titles(win)

    language.apply(QApplication.instance(), language.SOURCE, save=False)
    assert file_menu in menu_titles(win)


def test_all_six_long_lived_places_are_retranslated(window, translate_ui) -> None:
    """The dialogs recreate themselves; these six do not."""
    win = window
    win.context_bar.set_project(None)

    # we take the originals off live widgets: the language is the source one now,
    # so on the screen are exactly the strings written in the code
    bar = win.editor_screen.filter_bar
    issues_src = bar.issues_check.text()
    create_src = win.start_screen._buttons["create"].text()
    tm_src = win.context_bar.tm_button.text()

    translate_ui({
        "MainWindow": {actions_spec.MENU[0][0]: "МЕНЮ"},
        "UnitsTable": {units_model.COLUMNS[COL_KEY]: "ШАПКА"},
        "Actions": {actions_spec.BY_ID["scan"].text: "КОМАНДА"},
        "Editor": {issues_src: "ФИЛЬТРЫ"},
        "StartScreen": {create_src: "СТАРТ"},
        "Toolbar": {tm_src: "КОНТЕКСТ"},
    })

    model = win.editor_screen.model
    assert model.headerData(COL_KEY, Qt.Horizontal, Qt.DisplayRole) == "ШАПКА", \
        "шапка таблицы"
    assert "МЕНЮ" in menu_titles(win), "меню"
    assert win.actions["scan"].text() == "КОМАНДА", "команды"
    assert bar.issues_check.text() == "ФИЛЬТРЫ", "панель фильтров"
    assert win.start_screen._buttons["create"].text() == "СТАРТ", "стартовый экран"
    assert win.context_bar.tm_button.text() == "КОНТЕКСТ", "полоса контекста"


def test_toolbar_shows_the_same_translated_objects(window, translate_ui) -> None:
    """The toolbar is a shop window of the registry, it has no copies of the text of its own."""
    win = window
    translate_ui({"Actions": {actions_spec.BY_ID["scan"].text: "КОМАНДА"}})
    on_bar = [a.text() for a in win.toolbar.actions() if not a.isSeparator()]
    assert "КОМАНДА" in on_bar


def test_menu_rebuild_does_not_pile_up_actions(window, translate_ui) -> None:
    """The items of the radio groups are created anew — they must not pile up.

    They used to hang on the window itself, and every switch of language left one
    more invisible set of «Show/Sort/Theme».
    """
    win = window
    app = QApplication.instance()
    translate_ui({"MainWindow": {actions_spec.MENU[0][0]: "МЕНЮ"}})
    before = len(win.findChildren(type(win.actions["scan"])))
    for _ in range(3):
        language.apply(app, "ru", save=False)
        language.apply(app, language.SOURCE, save=False)
    after = len(win.findChildren(type(win.actions["scan"])))
    assert after == before, f"пункты меню накопились: было {before}, стало {after}"


def test_language_choice_survives_in_settings(qtbot, translate_ui, monkeypatch) -> None:
    stored: dict[str, str] = {}

    class FakeSettings:
        def setValue(self, key, value):
            stored[key] = value

        def value(self, key, default=""):
            return stored.get(key, default)

    translate_ui({"MainWindow": {actions_spec.MENU[0][0]: "МЕНЮ"}})
    language.apply(QApplication.instance(), language.SOURCE, save=False)
    monkeypatch.setattr(settings, "qsettings", lambda: FakeSettings())
    language.apply(QApplication.instance(), "ru")
    assert stored["language"] == "ru"
    assert language.saved() == "ru"
