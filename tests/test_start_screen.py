"""Экран проектов: возврат к списку, удаление, показ в проводнике.

Повод: файл проекта нельзя было удалить, «пока просто смотришь список». Причина
— приложение при запуске само открывает последний проект, а «Проекты» только
переключали экран, не отпуская соединение. В режиме WAL это держит файл.
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


# --- возврат к списку отпускает файл ------------------------------------


def test_returning_to_the_list_closes_the_project(window) -> None:
    win, path, _ = window
    win.open_project(path)
    assert win.conn is not None

    win.show_start()
    assert win.conn is None, "проект остался открытым — файл будет занят"
    assert win.project_path is None
    assert win.stack.currentWidget() is win.start_screen


def test_file_is_free_after_returning_to_the_list(window) -> None:
    """Тот самый сценарий: открыли, вернулись к списку, удаляем."""
    win, path, _ = window
    win.open_project(path)
    win.show_start()
    project.delete_project_file(path)          # не должно поднять OSError
    assert not path.exists()


# --- удаление -----------------------------------------------------------


def press(monkeypatch, role) -> list:
    """Ответить на модальное окно нажатием кнопки с такой ролью.

    По роли, а не по подписи: подписи переводятся, и тест, ищущий кнопку по
    тексту, молча перестал бы что-либо нажимать, оставшись зелёным ровно до
    первой смены языка.
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
    """Открытый проект удаляется только после закрытия соединения."""
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
    """Опасное действие не должно срабатывать по Enter."""
    win, path, _ = window
    seen = press(monkeypatch, QMessageBox.RejectRole)
    win.start_screen.deleteRequested.emit(str(path))
    assert seen and seen[0].buttonRole(
        seen[0].defaultButton()) == QMessageBox.RejectRole


def test_deleting_the_last_project_clears_the_autoopen(window, monkeypatch) -> None:
    """Иначе приложение при следующем запуске полезет за удалённым файлом."""
    win, path, stored = window
    stored["last"] = path
    press(monkeypatch, QMessageBox.DestructiveRole)
    win.start_screen.deleteRequested.emit(str(path))
    assert stored["last"] is None


# --- пропавший файл проекта ---------------------------------------------


def test_a_missing_project_stays_in_the_list_but_is_marked(window) -> None:
    """Файл удалили мимо приложения — запись остаётся, но видно, что её нет.

    Молча выбрасывать нельзя: проект мог лежать на флешке или сетевой папке, а
    вместе с записью пропали бы имя и прогресс. Поэтому строка гаснет и вместо
    процента показывает «файл не найден», а убрать её — отдельное решение
    человека (`Delete`).
    """
    win, path, _ = window
    path.unlink()
    win.start_screen.reload()

    items = [win.start_screen.list.item(i)
             for i in range(win.start_screen.list.count())]
    entry = next(i for i in items if i.data(Qt.UserRole) == str(path))

    assert "Мой мод" in entry.text()
    assert "1/2" not in entry.text()            # процент подменён пометкой
    assert entry.foreground().color() == theme.qcolor("text.disabled")


def test_a_missing_project_refuses_to_open(window, monkeypatch) -> None:
    """Открыть пропавший файл нельзя — иначе SQLite заведёт пустую базу на его месте."""
    win, path, _ = window
    path.unlink()
    win.start_screen.reload()
    warned: list = []
    # предупреждение модальное: без заглушки тест встал бы на exec() насмерть
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


# --- проводник ----------------------------------------------------------


def test_reveal_passes_a_single_string(tmp_path, monkeypatch) -> None:
    """Список аргументов ломает /select, — Python вставит пробел после запятой."""
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
    """Нажали кнопку — что-то обязано открыться, даже если файла уже нет."""
    calls = []
    monkeypatch.setattr("pdxloc.gui.shell.subprocess.Popen", calls.append)
    shell.reveal(tmp_path / "нет.pdxproj")
    assert calls and calls[0][0] == "explorer"
