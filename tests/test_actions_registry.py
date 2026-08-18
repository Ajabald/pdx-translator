"""Реестр команд: у каждой ровно один дом, витрины показывают те же объекты.

Раньше «Подтвердить» существовало тремя независимыми объектами (кнопка
тулбара, пункт контекстного меню, колонка «✓»), четыре кнопки панели не имели
пункта меню вообще, а тринадцать операций над строками не показывались нигде,
кроме контекстного меню. Эти проверки не дают дублям вернуться.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import actions, shell  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n c:0 "Third"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


def menu_ids() -> list[str]:
    """Идентификаторы действий в меню; порождаемые подменю («@…») пропускаем."""
    return [
        action_id
        for _, ids in actions.MENU
        for action_id in ids
        if action_id is not actions.SEP and not action_id.startswith("@")
    ]


# --- инварианты спеки: без Qt и без окна --------------------------------


def test_every_action_has_exactly_one_menu_home() -> None:
    ids = menu_ids()
    duplicated = {i for i in ids if ids.count(i) > 1}
    assert not duplicated, f"действие встречается в меню дважды: {duplicated}"
    homeless = {a.id for a in actions.ACTIONS} - set(ids)
    assert not homeless, f"действие без пункта меню: {homeless}"


def test_toolbar_has_no_action_outside_menu() -> None:
    """Панель — витрина меню. Кнопка без пункта меню недостижима с клавиатуры."""
    on_bar = {i for i in actions.TOOLBAR if i is not actions.SEP}
    assert on_bar <= set(menu_ids())


def test_context_menu_has_no_action_outside_menu() -> None:
    in_context = {i for i in actions.CONTEXT if i is not actions.SEP}
    assert in_context <= set(menu_ids())


def test_menu_refers_only_to_declared_actions() -> None:
    assert set(menu_ids()) <= set(actions.BY_ID)


def test_no_duplicate_shortcuts() -> None:
    """Одна клавиша — одно действие: иначе Qt объявляет конфликт и молчит."""
    seen: dict[str, str] = {}
    clashes = []
    for spec in actions.ACTIONS:
        for key in spec.keys:
            portable = QKeySequence(key).toString()
            if portable in seen:
                clashes.append(f"{portable}: {seen[portable]} и {spec.id}")
            seen[portable] = spec.id
    assert not clashes, "\n".join(clashes)


def test_clipboard_keys_belong_to_the_table() -> None:
    """Ctrl+C/V/Z в поле перевода должны означать правку текста, а не строки.

    QAction главного окна перехватил бы их раньше: карта шорткатов Qt
    опрашивается до доставки события виджету с фокусом.
    """
    for action_id in ("copy_cell", "paste_ru", "undo"):
        assert actions.BY_ID[action_id].owner == actions.TABLE, action_id


# --- живое окно ---------------------------------------------------------


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
    return win, path


def test_toolbar_shows_the_same_objects(window) -> None:
    """Кнопка «Подтвердить» и пункт таблицы — один объект, а не два похожих."""
    win, _ = window
    on_bar = [a for a in win.toolbar.actions() if not a.isSeparator()]
    assert win.actions["validate"] in on_bar
    assert win.actions["unvalidate"] in on_bar
    # тот же объект знает свою клавишу — раньше у тулбарного дубля её не было
    assert win.actions["validate"].shortcut() == QKeySequence("F10")


def test_context_menu_shows_the_same_objects(window) -> None:
    win, _ = window
    shown = win.editor_screen.context_menu().actions()
    assert win.actions["validate"] in shown
    assert win.actions["from_tm"] in shown


def test_selection_count_does_not_stick_to_action_text(window) -> None:
    """Охват массовой операции — заголовок меню, а не хвост в тексте действия."""
    win, path = window
    win.open_project(path)
    win.editor_screen.table.selectAll()
    titles = [a.text() for a in win.editor_screen.context_menu().actions()]

    assert any(t.startswith("Rows selected:") for t in titles)
    assert win.actions["validate"].text() == "Validate"
    assert not any("строк)" in t for t in titles)


def test_undo_is_scoped_to_the_table(window) -> None:
    win, _ = window
    assert win.actions["undo"].shortcutContext() == Qt.WidgetWithChildrenShortcut


def test_row_actions_disabled_without_project(window) -> None:
    win, path = window
    for action_id in ("validate", "from_tm", "ru_eq_en", "reset", "concordance"):
        assert not win.actions[action_id].isEnabled(), action_id
    win.open_project(path)
    for action_id in ("validate", "from_tm", "ru_eq_en", "reset", "concordance"):
        assert win.actions[action_id].isEnabled(), action_id


def test_machine_translation_is_a_project_action(window) -> None:
    """Перевод строки живёт там же, где остальные способы её заполнить."""
    win, path = window
    assert not win.actions["mt"].isEnabled()      # без проекта заполнять нечего
    win.open_project(path)
    assert win.actions["mt"].isEnabled()
    assert win.actions["mt_batch"].isEnabled()


def test_machine_translation_is_not_on_the_toolbar() -> None:
    """Панель — место, куда попадают мимо, а действие стоит денег и идёт в сеть."""
    assert "mt" not in actions.TOOLBAR
    assert "mt_batch" not in actions.TOOLBAR


def test_legacy_action_names_still_point_at_the_registry(window) -> None:
    """Старые имена (win.act_export и соседи) — те же объекты, не копии."""
    win, _ = window
    assert win.act_export is win.actions["export"]
    assert win.act_validate is win.actions["validate"]
    assert win.act_show_tree is win.actions["show_tree"]


def test_open_databases_folder_actually_opens_it(window, monkeypatch) -> None:
    """«Открыть папку баз» звало проводник через незаведённое имя.

    Обработчик обращался к `shell`, не импортированному в модуле, — нажатие
    падало с NameError. Такое ловится только вызовом: действие есть, к слоту
    привязано, но слот разваливается на первой же строке.
    """
    win, _ = window
    opened: list = []
    monkeypatch.setattr(shell, "open_dir", opened.append)

    win.actions["open_bdd"].trigger()

    assert opened == [settings.bdd_dir()]
