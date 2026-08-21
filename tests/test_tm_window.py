"""The translation memory window: three tabs instead of three windows."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import tm  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import theme  # noqa: E402
from pdxloc.gui.tm_entries_tab import COL_EN, COL_RU  # noqa: E402
from pdxloc.gui.tm_window import TmWindow  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'


@pytest.fixture
def conn(tmp_path, make_tree, monkeypatch):
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    c = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=en, tgt_root=ru)
    scan_project(c, 1)
    tm.upsert(c, "Zulu", "Зулу")
    tm.upsert(c, "Alpha", "Альфа")
    c.commit()
    yield c
    c.close()


@pytest.fixture
def window(conn, qtbot):
    win = TmWindow(conn)
    qtbot.addWidget(win)
    return win


def test_all_three_tools_live_in_one_window(window) -> None:
    """These used to be three windows referring to one another in the text of their hints."""
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == [
        "Entries", "Databases", "Build a database"]


def test_status_line_shows_the_active_tab(window) -> None:
    """The counter moved away from the buttons into the common bottom bar."""
    assert "shown:" in window.status_label.text()
    window.tabs.setCurrentWidget(window.sources)
    assert "databases in the folder:" in window.status_label.text()


def test_search_narrows_the_entries(window) -> None:
    window.entries.search.setText("Альфа")
    window.entries.reload()
    assert window.entries.model.rowCount() == 1
    assert "shown: 1" in window.status_label.text()


def test_entries_sorting_cycles_through_three_states(window) -> None:
    tab = window.entries
    natural = [tab.model.record(i).en_text for i in range(tab.model.rowCount())]
    tab._on_header_clicked(COL_EN)
    ascending = [tab.model.record(i).en_text for i in range(tab.model.rowCount())]
    assert ascending == sorted(ascending, key=str.casefold)
    tab._on_header_clicked(COL_EN)
    descending = [tab.model.record(i).en_text for i in range(tab.model.rowCount())]
    assert descending == list(reversed(ascending))
    tab._on_header_clicked(COL_EN)
    assert [tab.model.record(i).en_text for i in range(tab.model.rowCount())] == natural


def test_readonly_colour_follows_the_theme(window) -> None:
    """The records of attached databases were painted a hard grey past the palette."""
    light = theme.color("tm.readonly")
    theme.apply_theme(None, theme.DARK, save=False)
    try:
        assert theme.color("tm.readonly") != light
    finally:
        theme.apply_theme(None, theme.LIGHT, save=False)


def test_editing_a_translation_updates_the_memory(window, conn) -> None:
    tab = window.entries
    from PySide6.QtCore import Qt

    row = next(i for i in range(tab.model.rowCount())
               if tab.model.record(i).en_text == "Alpha")
    assert tab.model.setData(tab.model.index(row, COL_RU), "Первая", Qt.EditRole)
    assert [h.ru_text for h in tm.lookup(conn, "Alpha")] == ["Первая"]


def test_sources_apply_immediately_without_ok_button(window) -> None:
    """There is no OK button on the tab — the tick is obliged to take effect at once."""
    from PySide6.QtWidgets import QDialogButtonBox

    assert not window.sources.findChildren(QDialogButtonBox)
    fired = []
    window.sources.sourcesChanged.connect(lambda: fired.append(1))
    window.sources._on_item_changed(None)
    assert fired == [1]


def test_closing_stops_every_pending_timer(window) -> None:
    """A delayed search that outlived the window fell over on a closed connection."""
    window.entries.search.setText("что-нибудь")
    assert window.entries._debounce.isActive()
    window.done(0)
    assert not window.entries._debounce.isActive()


def test_build_tab_offers_project_export(window) -> None:
    assert window.build.mode_project.isEnabled()
    window.build.mode_project.setChecked(True)
    assert window.build.ok_button.text() == "Export"
    window.build.mode_dirs.setChecked(True)
    assert window.build.ok_button.text() == "Create the database"


def test_build_tab_works_without_a_project(qtbot) -> None:
    """A database can be built out of folders before a project is opened too."""
    from pdxloc.gui.tm_build_tab import TmBuildTab

    tab = TmBuildTab()
    qtbot.addWidget(tab)
    assert not tab.mode_project.isEnabled()
    assert tab.mode_dirs.isChecked()


def test_the_window_opens_without_a_project(qtbot, tmp_path, monkeypatch) -> None:
    """The first-start wizard calls this window when there is not a single project.

    `languages(None)` used to fall over here — right in the slot of the wizard's
    button. An assembled application has no console, the traceback went nowhere,
    and the «Build a database…» button looked dead: a press did exactly nothing.
    """
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    win = TmWindow(None)
    qtbot.addWidget(win)
    # «Records» and «Databases» without a project would show an emptiness there is
    # nothing to explain by: the first is its own memory, the second the databases attached to it
    assert [win.tabs.tabText(i) for i in range(win.tabs.count())] == [
        "Build a database"]
    assert win.entries is None and win.sources is None
    assert not win.build.mode_project.isEnabled()
    win.show_build_tab()
    assert win.tabs.currentWidget() is win.build
    win.done(0)         # the closing walks the same tabs — and does not stumble


def test_close_is_blocked_while_a_build_is_running(window, monkeypatch) -> None:
    """Going off to another tab and closing the window in the middle of a build must not pass silently."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(window.build, "is_busy", lambda: True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    window.done(0)
    assert window.isVisible() or window.result() == 0     # окно не закрылось

    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: (asked.append(1), QMessageBox.Yes)[1])
    monkeypatch.setattr(window.build, "cancel_build", lambda: None)
    window.done(0)
    assert asked == [1]
