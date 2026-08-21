"""The progress counter must not vanish because of temporary notifications."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
# «Привет » — an edge space that is not in the original: the row is translated, but
# with a remark. That does not affect the progress counter, while the «!» chip has something to count.
RU = 'l_russian:\n a:0 "Привет "\n'


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    monkeypatch.setattr(settings, "recent_projects", lambda: [{"path": "x", "name": "x"}])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)

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


def test_progress_visible_after_open(window):
    text = window.stats_label.text()
    assert "Translated 1 / 2" in text and "50.0%" in text
    # the invitation to choose a project no longer hangs there
    assert window.statusBar().currentMessage() == ""


def test_progress_survives_temporary_message(window):
    before = window.stats_label.text()
    window.statusBar().showMessage("временное уведомление", 100)
    assert window.stats_label.text() == before      # the permanent widget is not overwritten
    window.statusBar().clearMessage()
    assert window.stats_label.text() == before


def test_progress_updates_after_edit(window):
    from pdxloc.core import unit_ops

    unit_id = window.conn.execute("SELECT id FROM units WHERE key='b'").fetchone()[0]
    unit_ops.save_ru_text(window.conn, unit_id, "Мир")
    window._update_status_bar()
    assert "Translated 2 / 2" in window.stats_label.text()
    assert "100.0%" in window.stats_label.text()


# --- the «!» chip -------------------------------------------------------


def test_issue_chip_counts_rows_with_issues(window):
    assert window.chips.issues_chip.count == 1      # «Привет » with the edge space
    assert "1" in window.chips.issues_chip.text()


def test_issue_chip_switches_the_filter_and_its_other_views(window):
    """The chip is a shop window of the same action as the toolbar tick and the menu item.

    That is how the status chips used to come apart: a chip lit up only when the
    chip itself was clicked, while a filter set from the menu did not touch it.
    """
    window.chips.issuesClicked.emit()
    assert window.editor_screen.state.only_issues
    assert window.act_only_issues.isChecked()
    assert window.chips.issues_chip.active

    window.chips.issuesClicked.emit()
    assert not window.editor_screen.state.only_issues
    assert not window.chips.issues_chip.active


def test_issue_chip_follows_the_filter_set_elsewhere(window):
    window.act_only_issues.setChecked(True)
    assert window.chips.issues_chip.active


def test_issue_chip_updates_after_the_issue_is_fixed(window):
    from pdxloc.core import unit_ops

    unit_id = window.conn.execute("SELECT id FROM units WHERE key='a'").fetchone()[0]
    unit_ops.save_ru_text(window.conn, unit_id, "Привет")
    window.editor_screen.model.recheck_unit(unit_id)
    window._update_status_bar()
    assert window.chips.issues_chip.count == 0
