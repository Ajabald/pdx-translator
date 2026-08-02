"""Счётчик прогресса не должен пропадать из-за временных уведомлений."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ck3loc import project, settings  # noqa: E402
from ck3loc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    monkeypatch.setattr(settings, "recent_projects", lambda: [{"path": "x", "name": "x"}])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.ck3proj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    conn.close()

    from ck3loc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.open_project(path)
    return win


def test_progress_visible_after_open(window):
    text = window.stats_label.text()
    assert "Переведено 1 / 2" in text and "50.0%" in text
    # приглашение выбрать проект больше не висит
    assert window.statusBar().currentMessage() == ""


def test_progress_survives_temporary_message(window):
    before = window.stats_label.text()
    window.statusBar().showMessage("временное уведомление", 100)
    assert window.stats_label.text() == before      # постоянный виджет не затирается
    window.statusBar().clearMessage()
    assert window.stats_label.text() == before


def test_progress_updates_after_edit(window):
    from ck3loc.core import unit_ops

    unit_id = window.conn.execute("SELECT id FROM units WHERE key='b'").fetchone()[0]
    unit_ops.save_ru_text(window.conn, unit_id, "Мир")
    window._update_status_bar()
    assert "Переведено 2 / 2" in window.stats_label.text()
    assert "100.0%" in window.stats_label.text()
