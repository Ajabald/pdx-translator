"""Единое состояние фильтров: все витрины показывают одно и то же.

Фильтр ставится из пяти мест — панель, чипы статус-бара, дерево файлов, сводка
сканирования и меню «Фильтры». Раньше каждое знало только про себя: чип
загорался, лишь когда кликнули по самому чипу, а кнопка «Показать» в сводке
двигала комбобокс мимо чипов и мимо меню.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.core.statuses import Status  # noqa: E402
from pdxloc.gui.sorting import FIRST, SECOND  # noqa: E402
from pdxloc.gui.units_model import COL_ISSUES, COL_KEY  # noqa: E402
from pdxloc.gui.view_state import ViewState  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n c:0 "Third"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


# --- само состояние, без окна -------------------------------------------


def test_only_issues_is_derived_from_the_column_not_stored_twice() -> None:
    """У фильтра «с замечаниями» нет собственного поля — иначе они разъедутся."""
    s = ViewState()
    assert not s.only_issues
    s.click_column(COL_ISSUES)                 # первый клик — только порядок
    assert not s.only_issues
    assert s.sort_spec == (COL_ISSUES, False)
    s.click_column(COL_ISSUES)                 # второй — ещё и фильтр
    assert s.only_issues
    assert s.filters().only_issues
    s.click_column(COL_ISSUES)                 # третий — сброс
    assert not s.only_issues
    assert s.sort_spec is None


def test_issues_column_never_reverses_order() -> None:
    """Показывать проблемные снизу бессмысленно — второй шаг сужает выборку."""
    s = ViewState()
    s.click_column(COL_ISSUES)
    s.click_column(COL_ISSUES)
    assert s.sort_spec == (COL_ISSUES, False)


def test_checkbox_and_column_are_the_same_switch() -> None:
    s = ViewState()
    s.set_only_issues(True)
    assert s.sort.column == COL_ISSUES and s.sort.step == SECOND
    s.set_only_issues(False)
    # фильтр снят, но порядок «проблемные сверху» остаётся: выборка
    # расширяется, а строки не прыгают
    assert not s.only_issues
    assert s.sort_spec == (COL_ISSUES, False)


def test_click_on_another_column_drops_the_issues_filter() -> None:
    s = ViewState()
    s.set_only_issues(True)
    s.click_column(COL_KEY)
    assert not s.only_issues
    assert s.sort_spec == (COL_KEY, False)


def test_sort_click_and_filter_change_use_different_signals() -> None:
    """Перестановка строк не должна стоить SQL-запроса с пересчётом проверок."""
    s = ViewState()
    changed, sorted_ = [], []
    s.changed.connect(lambda: changed.append(1))
    s.sortChanged.connect(lambda: sorted_.append(1))

    s.click_column(COL_KEY)
    assert (changed, sorted_) == ([], [1])

    s.set_status(Status.UNTRANSLATED.value)
    assert changed == [1]

    s.click_column(COL_ISSUES)          # порядок
    s.click_column(COL_ISSUES)          # + фильтр: состав строк меняется
    assert changed == [1, 1]


def test_reset_filters_keeps_the_sort_order() -> None:
    s = ViewState()
    s.click_column(COL_KEY)
    s.set_status(Status.STALE.value)
    s.set_search("hello")
    s.set_file("a.yml", None)
    s.reset_filters()
    assert (s.status, s.search, s.file_rel) == (None, "", None)
    assert s.sort_spec == (COL_KEY, False)


def test_reset_filters_lifts_the_issues_filter_but_keeps_its_order() -> None:
    s = ViewState()
    s.set_only_issues(True)
    s.reset_filters()
    assert not s.only_issues
    assert s.sort.step == FIRST


# --- живое окно: витрины ------------------------------------------------


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
    scan_project(conn, 1)
    conn.close()

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.project_path = path
    win.open_project(path)
    return win


def checked_status(win) -> str | None:
    return next(v for v, a in win.status_actions.items() if a.isChecked())


def test_combo_lights_the_chip_and_the_menu(window) -> None:
    """Раньше чип загорался только от клика по самому чипу."""
    window.editor_screen.filter_bar.status_combo.setCurrentIndex(
        window.editor_screen.filter_bar.status_combo.findData(Status.TRANSLATED.value))
    assert window.chips._active == Status.TRANSLATED.value
    assert checked_status(window) == Status.TRANSLATED.value


def test_chip_click_moves_the_combo_and_the_menu(window) -> None:
    window.chips._on_chip(Status.UNTRANSLATED.value)
    assert window.editor_screen.state.status == Status.UNTRANSLATED.value
    assert window.editor_screen.filter_bar.status() == Status.UNTRANSLATED.value
    assert checked_status(window) == Status.UNTRANSLATED.value


def test_second_chip_click_clears_every_view(window) -> None:
    window.chips._on_chip(Status.UNTRANSLATED.value)
    window.chips._on_chip(Status.UNTRANSLATED.value)
    assert window.editor_screen.state.status is None
    assert window.chips._active is None
    assert checked_status(window) is None


def test_scan_summary_button_lights_the_chip(window) -> None:
    """Кнопка «Показать» в сводке сканирования — пятая витрина того же фильтра."""
    window.editor_screen.set_status_filter(Status.UNTRANSLATED.value)
    assert window.chips._active == Status.UNTRANSLATED.value
    assert window.editor_screen.filter_bar.status() == Status.UNTRANSLATED.value


def test_issues_column_ticks_the_checkbox_and_the_menu(window) -> None:
    screen = window.editor_screen
    screen._on_header_clicked(COL_ISSUES)
    screen._on_header_clicked(COL_ISSUES)
    assert screen.filter_bar.issues_check.isChecked()
    assert window.actions["only_issues"].isChecked()


def test_checkbox_clears_the_column_filter(window) -> None:
    screen = window.editor_screen
    screen._on_header_clicked(COL_ISSUES)
    screen._on_header_clicked(COL_ISSUES)
    screen.filter_bar.issues_check.setChecked(False)
    assert not screen.state.only_issues
    assert not window.actions["only_issues"].isChecked()


def test_menu_action_drives_the_same_filter(window) -> None:
    window.actions["only_issues"].setChecked(True)
    assert window.editor_screen.state.only_issues
    assert window.editor_screen.filter_bar.issues_check.isChecked()


def test_reset_filters_action_clears_everything_but_the_order(window) -> None:
    screen = window.editor_screen
    screen.set_status_filter(Status.TRANSLATED.value)
    screen._on_header_clicked(COL_KEY)
    window.actions["reset_filters"].trigger()
    assert screen.state.status is None
    assert window.chips._active is None
    assert screen.state.sort_spec == (COL_KEY, False)
