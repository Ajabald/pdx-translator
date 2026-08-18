"""Смена языка перерисовывает окно, а не требует перезапуска.

Проверяется вся цепочка целиком: собирается настоящий `.qm`, подсовывается
вместо штатной папки переводов и включается через `language.apply`. Проверять
подменой `translate` было бы самообманом — мимо остались бы ровно те места, где
и ломается: загрузка QTranslator и пересборка меню.

Долгожителей шесть (меню, панель, экраны, шапка таблицы, чипы, полоса
контекста), и каждый обязан обновиться: диалоги создаются заново при открытии и
язык подхватывают сами, а эти — нет.
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
    """Собрать настоящий .qm из пар «контекст → {оригинал: перевод}»."""
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
    """Перевести указанные строки живого интерфейса выдуманными словами.

    Оригиналы берутся **из самого кода**, а не переписываются в тест: строки
    интерфейса ещё переезжают на английский, и захардкоженный список пришлось
    бы править вслед за каждым модулем — а он тихо перестал бы что-то
    проверять, оставшись синтаксически верным.
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
    """Диалоги пересоздаются сами; вот эти шестеро — нет."""
    win = window
    win.context_bar.set_project(None)

    # оригиналы снимаем с живых виджетов: сейчас язык исходный, значит на
    # экране ровно те строки, что написаны в коде
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
    """Панель — витрина реестра, своих копий текста у неё нет."""
    win = window
    translate_ui({"Actions": {actions_spec.BY_ID["scan"].text: "КОМАНДА"}})
    on_bar = [a.text() for a in win.toolbar.actions() if not a.isSeparator()]
    assert "КОМАНДА" in on_bar


def test_menu_rebuild_does_not_pile_up_actions(window, translate_ui) -> None:
    """Пункты радиогрупп создаются заново — они не должны копиться.

    Раньше они висели на самом окне, и каждое переключение языка оставляло
    ещё один невидимый набор «Показывать/Сортировка/Тема».
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
