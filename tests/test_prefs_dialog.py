"""Окно «Параметры»: у каждой настройки есть живая точка применения.

Мёртвая галка хуже отсутствующей — она обещает то, чего не делает. Поэтому
проверяем не «диалог открылся», а что значение доезжает до виджета, который
за него отвечает, и без перезапуска приложения.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import exporter  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import ask, prefs  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


class FakeSettings:
    """QSettings без записи в реестр пользователя."""

    def __init__(self):
        self.store: dict = {}
        self.writes = 0

    def value(self, key, default=None, type=None):   # noqa: A002
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value
        self.writes += 1


@pytest.fixture
def store(monkeypatch):
    fake = FakeSettings()
    monkeypatch.setattr(settings, "qsettings", lambda: fake)
    return fake


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch, store):
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


def dialog(win, qtbot):
    from pdxloc.gui.prefs_dialog import PreferencesDialog

    dlg = PreferencesDialog(win)
    qtbot.addWidget(dlg)
    return dlg


def test_opening_the_dialog_writes_nothing(window, qtbot, store) -> None:
    """Иначе каждый запуск теста гадил бы в настройки пользователя."""
    before = store.writes
    dialog(window, qtbot)
    assert store.writes == before


def test_row_height_reaches_the_table(window, qtbot) -> None:
    dlg = dialog(window, qtbot)
    dlg.row_height.setValue(31)
    dlg.apply()
    assert window.editor_screen.table.verticalHeader().defaultSectionSize() == 31


def test_grid_toggle_reaches_the_table(window, qtbot) -> None:
    dlg = dialog(window, qtbot)
    dlg.show_grid.setChecked(True)
    dlg.apply()
    assert window.editor_screen.table.showGrid()


def test_font_reaches_the_editor_fields(window, qtbot) -> None:
    dlg = dialog(window, qtbot)
    dlg.font_size.setValue(14)
    dlg.apply()
    detail = window.editor_screen.detail
    assert detail.ru_edit.font().pointSize() == 14
    assert detail.en_view.font().pointSize() == 14


def test_editor_heads_stay_aligned_after_a_font_change(window, qtbot) -> None:
    """Шапки EN и RU обязаны остаться одной высоты — иначе поля разъезжаются."""
    dlg = dialog(window, qtbot)
    dlg.font_size.setValue(16)
    dlg.apply()
    detail = window.editor_screen.detail
    assert detail.en_view.y() == detail.ru_edit.y() or (
        detail._head_bars[0].height() == detail._head_bars[1].height())


def test_cell_limit_reaches_the_model(window, qtbot) -> None:
    from pdxloc.gui import units_model

    dlg = dialog(window, qtbot)
    dlg.cell_limit.setValue(42)
    dlg.apply()
    assert units_model.MAX_CELL == 42


def test_highlight_checkbox_and_preference_are_one_switch(window, qtbot) -> None:
    dlg = dialog(window, qtbot)
    dlg.highlight_changes.setChecked(False)
    dlg.apply()
    assert not window.editor_screen.detail.highlight_check.isChecked()


def test_backup_keep_is_read_at_call_time(store, tmp_path) -> None:
    """Раньше значение вычислялось на импорте exporter и не менялось до перезапуска."""
    store.store["backup/keep"] = 2
    assert settings.backup_keep() == 2

    project_dir = tmp_path / "backups" / "P"
    for stamp in ("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"):
        (project_dir / stamp).mkdir(parents=True)
    exporter._prune_backups(project_dir)
    assert sorted(p.name for p in project_dir.iterdir()) == ["2026-08-03", "2026-08-04"]


def test_folders_are_saved(window, qtbot, tmp_path, store) -> None:
    dlg = dialog(window, qtbot)
    target = tmp_path / "СвояПапка"
    dlg.projects_row.set_value(target)
    dlg.apply()
    assert store.store["projects_dir"] == str(target)


def test_theme_change_ticks_the_view_menu(window, qtbot) -> None:
    from pdxloc.gui import theme

    dlg = dialog(window, qtbot)
    try:
        dlg.theme_combo.setCurrentIndex(dlg.theme_combo.findData(theme.DARK))
        dlg.apply()
        assert theme.is_dark()
        assert window.theme_actions[theme.DARK].isChecked()
    finally:
        theme.apply_theme(None, theme.LIGHT, save=False)


def test_muted_reminders_can_be_brought_back(window, qtbot, store) -> None:
    """«Больше не спрашивать» обязано иметь путь назад.

    Заглушить напоминание можно из него самого, а вернуть — только отсюда.
    Настройка, которую невозможно отменить, — ловушка.
    """
    from pdxloc.gui import ask

    for name in ask.KNOWN:
        prefs.set_flag(f"{ask.PREFIX}{name}", True)
    assert ask.any_muted()

    dlg = dialog(window, qtbot)
    assert dlg.unmute_reminders.isEnabled()
    dlg.unmute_reminders.setChecked(True)
    dlg.apply()

    assert not ask.any_muted()
    # Возвращать больше нечего — и галка это показывает, а не обещает впустую
    assert not dlg.unmute_reminders.isEnabled()
    assert not dlg.unmute_reminders.isChecked()


def test_the_unmute_checkbox_is_dead_while_nothing_is_hidden(window, qtbot,
                                                             store) -> None:
    dlg = dialog(window, qtbot)
    assert not ask.any_muted()
    assert not dlg.unmute_reminders.isEnabled()


# --- машинный перевод ---

def test_mt_limits_reach_the_preferences(window, qtbot, store) -> None:
    dlg = dialog(window, qtbot)
    dlg.mt_budget.setValue(2000)
    dlg.mt_throttle.setValue(400)
    dlg.mt_retries.setValue(1)
    dlg.apply()
    assert prefs.get("mt/char_budget") == 2000
    assert prefs.get("mt/throttle_ms") == 400
    assert prefs.get("mt/retries") == 1


def test_mt_key_is_stored_per_provider(window, qtbot, store) -> None:
    """Ключей несколько, и один не должен затирать другой."""
    from pdxloc.core import mt

    dlg = dialog(window, qtbot)
    dlg.mt_provider.setCurrentIndex(dlg.mt_provider.findData("none"))
    mt.save_api_key("deepl", "ключ-deepl")
    mt.save_api_key("openai", "ключ-openai")
    assert mt.api_key("deepl") == "ключ-deepl"
    assert mt.api_key("openai") == "ключ-openai"


def test_mt_key_is_not_a_preference(window, qtbot, store) -> None:
    """`prefs.get` вернул бы защищённую строку вместо ключа."""
    assert not any(key.startswith("mt/key") for key in prefs.DEFAULTS)


def test_mt_key_field_hides_the_key(window, qtbot, store) -> None:
    from PySide6.QtWidgets import QLineEdit

    dlg = dialog(window, qtbot)
    assert dlg.mt_key.echoMode() == QLineEdit.Password
    dlg.mt_key_show.setChecked(True)
    assert dlg.mt_key.echoMode() == QLineEdit.Normal


def test_key_field_is_dead_while_no_service_is_chosen(window, qtbot, store) -> None:
    """Поле ключа при выключенном переводе — обещание, которому нечего делать."""
    dlg = dialog(window, qtbot)
    dlg.mt_provider.setCurrentIndex(dlg.mt_provider.findData("none"))
    assert not dlg.mt_key.isEnabled()
    assert not dlg.mt_key_check.isEnabled()


def test_opening_the_dialog_does_not_touch_the_stored_key(window, qtbot, store) -> None:
    """Открыли «Параметры» и закрыли — ключ обязан остаться прежним."""
    from pdxloc.core import mt

    mt.save_api_key("deepl", "ключ")
    before = dict(store.store)
    dialog(window, qtbot)
    assert store.store == before


def test_every_control_maps_to_a_stored_key(window, qtbot) -> None:
    """Настройка без ключа — настройка, которую никто не читает."""
    dlg = dialog(window, qtbot)
    dlg.apply()
    for key in prefs.DEFAULTS:
        assert prefs.get(key) is not None, key
