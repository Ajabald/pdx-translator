"""The projects screen: the return to the list, deleting, revealing in the explorer.

The reason: a project file could not be deleted «while you are merely looking at
the list». The cause — at start-up the application opens the last project itself,
while «Projects» only switched the screen without letting the connection go. In
WAL mode that holds the file.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import trash  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import shell, theme  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    remembered: list = [{"path": "", "name": ""}]
    monkeypatch.setattr(settings, "recent_projects", lambda: (remembered[0]["path"] and
                        [dict(remembered[0])]) or [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    monkeypatch.setattr(trash, "available", lambda: False)

    stored: dict = {"last": None, "forgotten": []}
    monkeypatch.setattr(settings, "last_project_path", lambda: stored["last"])
    monkeypatch.setattr(settings, "set_last_project_path",
                        lambda p: stored.update(last=p))
    monkeypatch.setattr(settings, "forget_project",
                        lambda p: stored["forgotten"].append(p))

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="Мой мод", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    conn.close()
    remembered[0] = {"path": str(path), "name": "Мой мод", "done": 1, "total": 2}

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    return win, path, stored


# --- the return to the list lets the file go ----------------------------


def test_returning_to_the_list_closes_the_project(window) -> None:
    win, path, _ = window
    win.open_project(path)
    assert win.conn is not None

    win.show_start()
    assert win.conn is None, "проект остался открытым — файл будет занят"
    assert win.project_path is None
    assert win.stack.currentWidget() is win.start_screen


def test_file_is_free_after_returning_to_the_list(window) -> None:
    """That very scenario: opened, returned to the list, deleting."""
    win, path, _ = window
    win.open_project(path)
    win.show_start()
    project.delete_project_file(path)          # must not raise OSError
    assert not path.exists()


# --- deleting -----------------------------------------------------------


def press(monkeypatch, role) -> list:
    """Answer a modal window by pressing the button with such a role.

    By role and not by label: labels are translated, and a test that looks for a
    button by text would silently stop pressing anything, staying green right up
    to the first change of language.
    """
    seen = []

    def fake_exec(self):
        seen.append(self)
        for btn in self.buttons():
            if self.buttonRole(btn) == role:
                self.setResult(0)
                self._picked = btn
                return 0
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: getattr(self, "_picked", None))
    return seen


def test_delete_removes_file_and_forgets_project(window, monkeypatch) -> None:
    win, path, stored = window
    press(monkeypatch, QMessageBox.DestructiveRole)
    win.start_screen.deleteRequested.emit(str(path))

    assert not path.exists()
    assert stored["forgotten"] == [path]


def test_delete_closes_the_project_first(window, monkeypatch) -> None:
    """An open project is deleted only after the connection is closed."""
    win, path, _ = window
    win.open_project(path)
    press(monkeypatch, QMessageBox.DestructiveRole)
    win.start_screen.deleteRequested.emit(str(path))

    assert win.conn is None
    assert not path.exists()


def test_cancel_keeps_everything(window, monkeypatch) -> None:
    win, path, stored = window
    press(monkeypatch, QMessageBox.RejectRole)
    win.start_screen.deleteRequested.emit(str(path))

    assert path.exists()
    assert stored["forgotten"] == []


def test_cancel_is_the_default_button(window, monkeypatch) -> None:
    """A dangerous action must not fire on Enter."""
    win, path, _ = window
    seen = press(monkeypatch, QMessageBox.RejectRole)
    win.start_screen.deleteRequested.emit(str(path))
    assert seen and seen[0].buttonRole(
        seen[0].defaultButton()) == QMessageBox.RejectRole


def test_deleting_the_last_project_clears_the_autoopen(window, monkeypatch) -> None:
    """Otherwise at the next start the application goes after a deleted file."""
    win, path, stored = window
    stored["last"] = path
    press(monkeypatch, QMessageBox.DestructiveRole)
    win.start_screen.deleteRequested.emit(str(path))
    assert stored["last"] is None


# --- a project file gone missing ----------------------------------------


def test_a_missing_project_stays_in_the_list_but_is_marked(window) -> None:
    """The file was deleted past the application — the record stays, but its absence shows.

    Throwing it out silently will not do: the project may have lain on a flash
    drive or a network folder, and the name and the progress would go with the
    record. That is why the row goes dim and shows «file not found» instead of a
    percentage, while taking it away is a decision of the human's own (`Delete`).
    """
    win, path, _ = window
    path.unlink()
    win.start_screen.reload()

    items = [win.start_screen.list.item(i)
             for i in range(win.start_screen.list.count())]
    entry = next(i for i in items if i.data(Qt.UserRole) == str(path))

    assert "Мой мод" in entry.text()
    assert "1/2" not in entry.text()            # the percentage is replaced by the mark
    assert entry.foreground().color() == theme.qcolor("text.disabled")


def test_a_missing_project_refuses_to_open(window, monkeypatch) -> None:
    """A file gone missing must not be opened — otherwise SQLite sets up an empty database in its place."""
    win, path, _ = window
    path.unlink()
    win.start_screen.reload()
    warned: list = []
    # the warning is modal: without a stub the test would stand dead on exec()
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a)))
    opened: list = []
    win.start_screen.projectOpened.connect(opened.append)

    for i in range(win.start_screen.list.count()):
        item = win.start_screen.list.item(i)
        if item.data(Qt.UserRole) == str(path):
            win.start_screen.list.setCurrentItem(item)
    win.start_screen._open()

    assert opened == []
    assert warned, "молчать в ответ на нажатие нельзя — человек не поймёт, что случилось"


# --- the explorer -------------------------------------------------------


def test_reveal_passes_a_single_string(tmp_path, monkeypatch) -> None:
    """A list of arguments breaks /select, — Python inserts a space after the comma."""
    calls = []
    monkeypatch.setattr("pdxloc.gui.shell.subprocess.Popen", calls.append)
    target = tmp_path / "проект.pdxproj"
    target.touch()

    shell.reveal(target)

    assert len(calls) == 1
    command = calls[0]
    assert isinstance(command, str), "аргументы списком проводник не разберёт"
    assert command.startswith("explorer /select,\"")
    assert "/select, " not in command


def test_reveal_falls_back_to_the_folder(tmp_path, monkeypatch) -> None:
    """The button was pressed — something is obliged to open, even if the file is already gone."""
    calls = []
    monkeypatch.setattr("pdxloc.gui.shell.subprocess.Popen", calls.append)
    shell.reveal(tmp_path / "нет.pdxproj")
    assert calls and calls[0][0] == "explorer"
