"""Панель инструментов, меню «Вид» и полоса контекста проекта."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import theme  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)      # иначе открытие проекта позовёт модальный скан
    conn.close()

    from pdxloc.gui.main_window import MainWindow

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
    # игра впереди языков: у человека с проектами двух игр это единственный
    # способ заметить, что он правит не тот
    assert win.context_bar.langs.text() == "Crusader Kings III · english → russian"
    assert "Memory databases" in win.context_bar.tm_button.text()


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
    assert "2" in win.selection_label.text()
    # одна строка — счётчик не нужен, он только шумит
    win._on_selection_changed(1)
    assert win.selection_label.text() == ""


def test_theme_switch(window):
    win, _ = window
    try:
        win._set_theme(theme.DARK)
        assert theme.is_dark()
        assert theme.color("text") == "#e8e8e8"
        win._set_theme(theme.LIGHT)
        assert not theme.is_dark()
    finally:
        theme.apply_theme(None, theme.LIGHT, save=False)


def test_view_toggles_hide_widgets(window):
    win, path = window
    win.open_project(path)
    win.act_show_tree.setChecked(False)
    assert not win.editor_screen.file_tree.isVisibleTo(win.editor_screen)
    win.act_show_tree.setChecked(True)
    assert win.editor_screen.file_tree.isVisibleTo(win.editor_screen)


# --- «Вид → Колонки» и «Вид → Кнопки статуса» ---------------------------


@pytest.fixture
def opened(window, monkeypatch):
    """Окно с проектом и с QSettings, не уезжающими в реестр пользователя."""
    win, path = window
    store: dict = {}
    monkeypatch.setattr(settings, "qsettings", lambda: _Store(store))
    win.open_project(path)
    return win, store


class _Store:
    """QSettings поверх обычного словаря — свой на каждый тест."""

    def __init__(self, store: dict):
        self._store = store

    def value(self, key, default=None, type=None):   # noqa: A002
        return self._store.get(key, default)

    def setValue(self, key, value):
        self._store[key] = value


def test_column_can_be_hidden_and_shown_again(opened):
    from pdxloc.gui.units_model import COL_FILE

    win, _ = opened
    win.column_actions[COL_FILE].setChecked(False)
    assert win.editor_screen.table.isColumnHidden(COL_FILE)
    win.column_actions[COL_FILE].setChecked(True)
    assert not win.editor_screen.table.isColumnHidden(COL_FILE)


def forget(action, checked: bool) -> None:
    """Вернуть пункт в исходное состояние, не тронув настройку.

    Так выглядит только что собранное окно: галки стоят, настройка ещё не
    прочитана. Обычный `setChecked` тут не годится — он сам пишет в настройку и
    стёр бы то, что мы собираемся проверить.
    """
    action.blockSignals(True)
    action.setChecked(checked)
    action.blockSignals(False)


def test_hidden_column_is_remembered_by_name_not_by_number(opened):
    """Вставь кто-нибудь колонку в середину — номера сдвинулись бы молча."""
    from pdxloc.gui.units_model import COL_FILE

    win, store = opened
    win.column_actions[COL_FILE].setChecked(False)
    assert "File" in store["view/hidden_columns"]

    forget(win.column_actions[COL_FILE], True)
    win.editor_screen.table.setColumnHidden(COL_FILE, False)
    win._restore_view_settings()
    assert win.editor_screen.table.isColumnHidden(COL_FILE)
    assert not win.column_actions[COL_FILE].isChecked()


def test_the_last_column_cannot_be_hidden(opened):
    """Спрятать таблицу целиком — не настройка, а поломка."""
    from pdxloc.gui.units_model import DATA_COLUMNS

    win, _ = opened
    columns = [col for col, _ in DATA_COLUMNS]
    for col in columns[:-1]:
        win.column_actions[col].setChecked(False)
    last = columns[-1]
    win.column_actions[last].setChecked(False)
    assert not win.editor_screen.table.isColumnHidden(last)
    assert win.column_actions[last].isChecked()


def test_status_button_hides_only_the_toolbar_button(opened):
    """Прятать сам QAction нельзя: он же в меню «Перевод» и в контекстном."""
    win, _ = opened
    button = win.toolbar.widgetForAction(win.act_validate)
    win.button_actions["validate"].setChecked(False)
    assert not button.isVisibleTo(win.toolbar)
    assert win.act_validate.isVisible()
    assert win.act_validate.isEnabled()
    assert win.act_validate.shortcuts()

    win.button_actions["validate"].setChecked(True)
    assert button.isVisibleTo(win.toolbar)


def test_hidden_status_button_is_remembered(opened):
    win, store = opened
    win.button_actions["ignore"].setChecked(False)
    assert store["view/button_ignore"] is False

    forget(win.button_actions["ignore"], True)
    win.toolbar.widgetForAction(win.act_ignore).setVisible(True)
    win._restore_view_settings()
    assert not win.button_actions["ignore"].isChecked()
    assert not win.toolbar.widgetForAction(win.act_ignore).isVisibleTo(win.toolbar)
