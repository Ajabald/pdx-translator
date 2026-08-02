"""Панель инструментов, меню «Вид» и полоса контекста проекта."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ck3loc import project, settings  # noqa: E402
from ck3loc.core.scanner import scan_project  # noqa: E402
from ck3loc.gui import theme  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "default_db_path", lambda: tmp_path / "нет-такой.sqlite3")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)      # иначе открытие проекта позовёт модальный скан
    conn.close()

    from ck3loc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.project_path = path      # без него скан не запустится
    return win, path


def test_project_actions_disabled_without_project(window):
    win, _ = window
    assert not win.act_export.isEnabled()
    assert not win.act_validate.isEnabled()
    assert win.toolbar.actions()          # панель собрана


def test_context_bar_shows_langs_and_bases(window):
    win, path = window
    win.open_project(path)
    assert win.act_export.isEnabled()
    assert win.context_bar.langs.text() == "english → russian"
    assert "Базы памяти" in win.context_bar.tm_button.text()


def test_context_bar_cleared_on_close(window):
    win, path = window
    win.open_project(path)
    win._close_project()
    assert win.context_bar.langs.text() == ""
    assert not win.act_export.isEnabled()      # действия проекта снова выключены
    assert not win.stats_label.text()


def test_selection_count_shown(window):
    win, path = window
    win.open_project(path)
    win.editor_screen.table.selectAll()
    assert "Выбрано строк: 2" in win.selection_label.text()
    # одна строка — счётчик не нужен, он только шумит
    win._on_selection_changed(1)
    assert win.selection_label.text() == ""


def test_theme_switch(window, monkeypatch):
    win, _ = window
    monkeypatch.setattr(settings, "qsettings", lambda: _FakeSettings())
    try:
        win._set_theme(theme.DARK)
        assert theme.is_dark()
        assert theme.color("text") == "#e8e8e8"
        win._set_theme(theme.LIGHT)
        assert not theme.is_dark()
    finally:
        theme.apply_theme(None, theme.LIGHT, save=False)


def test_view_toggles_hide_widgets(window, monkeypatch):
    win, path = window
    monkeypatch.setattr(settings, "qsettings", lambda: _FakeSettings())
    win.open_project(path)
    win.act_show_tree.setChecked(False)
    assert not win.editor_screen.file_tree.isVisibleTo(win.editor_screen)
    win.act_show_tree.setChecked(True)
    assert win.editor_screen.file_tree.isVisibleTo(win.editor_screen)


class _FakeSettings:
    """QSettings без записи в реестр пользователя."""

    _store: dict = {}

    def value(self, key, default=None, type=None):   # noqa: A002
        return self._store.get(key, default)

    def setValue(self, key, value):
        self._store[key] = value
