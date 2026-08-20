"""Мастер первого запуска и напоминания с постоянным выходом.

Оба показываются модально, поэтому в `conftest.py` они по умолчанию отключены
на весь набор: без этого каждый тест с главным окном вставал бы на `exec()`.
Здесь фикстуры отключаются явно — иначе проверять было бы нечего.

Главное, за чем следим: мастер обязан показаться **один раз**, а «Пропустить»
и крестик обязаны считаться ответом. Иначе он встречал бы при каждом запуске, а
такое закрывают не глядя.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.gui import ask, prefs, welcome_dialog  # noqa: E402
from pdxloc.gui.welcome_dialog import DONE_KEY, WelcomeDialog  # noqa: E402


class FakeSettings:
    """QSettings без записи в реестр пользователя."""

    def __init__(self):
        self.store: dict = {}

    def value(self, key, default=None, type=None):   # noqa: A002
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


@pytest.fixture
def store(monkeypatch):
    fake = FakeSettings()
    monkeypatch.setattr(settings, "qsettings", lambda: fake)
    return fake


@pytest.fixture
def no_first_start_wizard():
    """Отключить общую заглушку: здесь проверяется сам мастер."""
    return None


@pytest.fixture
def no_reminders():
    """Отключить общую заглушку: здесь проверяется сам `ask_once`."""
    return None


@pytest.fixture
def shown(monkeypatch):
    """Считать показы мастера, не открывая его по-настоящему.

    `exec()` модален и в offscreen-режиме тоже блокирует. Подменяем именно его,
    а не `needed`: проверять надо всю цепочку «нужен ли → показали → отметили»,
    а с подменённым `needed` от неё осталась бы половина.
    """
    calls: list[WelcomeDialog] = []

    def fake_exec(self):
        calls.append(self)
        self.done(0)
        return 0

    monkeypatch.setattr(WelcomeDialog, "exec", fake_exec)
    return calls


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch, store):
    """Главное окно без открытия проекта — мастер идёт до него."""
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")

    def _make():
        from pdxloc.gui.main_window import MainWindow

        win = MainWindow()
        qtbot.addWidget(win)
        return win

    return _make


# --- мастер показывается один раз ---

def test_wizard_shows_on_a_fresh_install(window, shown, store) -> None:
    window()
    assert len(shown) == 1
    assert store.value(DONE_KEY) is True


def test_wizard_does_not_come_back(window, shown) -> None:
    """Второй запуск обязан пройти мимо: отметка ставится показом, не ответом."""
    window()
    window()
    assert len(shown) == 1


def test_wizard_is_not_needed_once_marked(store) -> None:
    assert welcome_dialog.needed()
    welcome_dialog.mark_done()
    assert not welcome_dialog.needed()


# --- «Пропустить» и крестик — полноправные ответы ---

def test_skip_marks_the_wizard_done(qtbot, store) -> None:
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    assert welcome_dialog.needed()
    dlg.skip_btn.click()
    assert not welcome_dialog.needed()


def test_closing_with_the_cross_marks_the_wizard_done(qtbot, store) -> None:
    """Крестик — тот же ответ, что «Пропустить».

    Если бы он отметки не ставил, мастер встречал бы при каждом запуске всех,
    кто закрывает окна крестиком, — а таких большинство.
    """
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    dlg.reject()                      # то же, что нажать крестик
    assert not welcome_dialog.needed()


def test_the_last_step_finishes_the_wizard(qtbot, store) -> None:
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    for _ in range(dlg.pages.count() - 1):
        dlg.next_btn.click()
    assert dlg.pages.currentIndex() == dlg.pages.count() - 1
    dlg.next_btn.click()              # «Готово»
    assert not welcome_dialog.needed()


def test_database_step_tells_the_truth_about_what_is_there(qtbot, store,
                                                           monkeypatch) -> None:
    """Текст шага зависит от того, есть ли базы: врать нельзя ни в одну сторону."""
    monkeypatch.setattr(project, "all_tm_databases", lambda: [])
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    dlg._go(1)
    assert "no translation memory databases" in dlg.db_text.text().lower()

    monkeypatch.setattr(project, "all_tm_databases", lambda: ["a", "b"])
    dlg._go(1)
    assert "2" in dlg.db_text.text()


# --- «Собрать базу…» доводит до окна сборки ---

def test_building_the_first_database_needs_no_project(window, shown,
                                                      monkeypatch) -> None:
    """Главная жалоба на 0.1.0: кнопка мастера не делала ровно ничего.

    Окно памяти требовало открытого проекта, а на первом запуске его нет ни
    одного, и `languages(None)` падал прямо в слоте. У собранного приложения
    консоли нет, поэтому наружу не выходило даже сообщения об ошибке.

    Проверяем путь целиком, от главного окна: подменяется только `exec()` —
    он модален и в offscreen-режиме тоже блокирует.
    """
    from pdxloc.gui.tm_window import TmWindow

    opened: list[TmWindow] = []
    monkeypatch.setattr(TmWindow, "exec", lambda self: (opened.append(self), 0)[1])

    win = window()
    assert win.conn is None                 # проекта нет — за этим сюда и шли
    win._build_tm_database()

    assert len(opened) == 1
    tabs = opened[0].tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Build a database"]


def test_the_database_step_notices_the_database_it_just_built(
        qtbot, store, monkeypatch) -> None:
    """Иначе мастер уверял бы, что баз нет, сразу после сборки одной."""
    built: list[str] = []
    monkeypatch.setattr(project, "all_tm_databases", lambda: built)

    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    dlg.buildDatabaseRequested.connect(lambda: built.append("ck3.pdxtm"))
    dlg._go(1)
    assert "no translation memory databases" in dlg.db_text.text().lower()

    dlg.db_btn.click()
    assert built == ["ck3.pdxtm"]
    assert "1" in dlg.db_text.text()
    assert dlg.db_btn.text() == "Build one more…"


# --- напоминания замолкают навсегда и отвечают «нет» ---

def _answer(monkeypatch, checked: bool, button=QMessageBox.Yes):
    """Показать напоминание, поставив (или нет) галку «больше не спрашивать»."""
    def fake_exec(self):
        self.checkBox().setChecked(checked)
        return button

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)


def test_reminder_asks_while_it_is_not_muted(qtbot, store, monkeypatch) -> None:
    _answer(monkeypatch, checked=False)
    answer = ask.ask_once(None, ask.NO_TM_DATABASES, "Заголовок", "Текст")
    assert answer == QMessageBox.Yes
    assert not ask.muted(ask.NO_TM_DATABASES)


def test_reminder_stops_asking_after_the_checkbox(qtbot, store, monkeypatch) -> None:
    _answer(monkeypatch, checked=True)
    ask.ask_once(None, ask.NO_TM_DATABASES, "Заголовок", "Текст")
    assert ask.muted(ask.NO_TM_DATABASES)

    def never(self):
        raise AssertionError("заглушённое напоминание всё-таки показалось")

    monkeypatch.setattr(QMessageBox, "exec", never)
    assert ask.ask_once(None, ask.NO_TM_DATABASES, "Заголовок",
                        "Текст") == QMessageBox.No


def test_muted_reminder_answers_no(qtbot, store) -> None:
    """Умолчание осторожное: галка отвязывается от вопроса, а не соглашается.

    Ответь заглушённый вопрос «да» — и предложение начало бы исполняться само,
    молча и при каждом запуске.
    """
    prefs.set_flag(f"{ask.PREFIX}{ask.NO_TM_DATABASES}", True)
    assert ask.ask_once(None, ask.NO_TM_DATABASES, "Заголовок",
                        "Текст") == QMessageBox.No


def test_every_reminder_can_be_brought_back(qtbot, store, monkeypatch) -> None:
    """Настройка, которую невозможно отменить, — ловушка."""
    _answer(monkeypatch, checked=True)
    for name in ask.KNOWN:
        ask.ask_once(None, name, "Заголовок", "Текст")
        assert ask.muted(name), name

    ask.unmute_all()
    for name in ask.KNOWN:
        assert not ask.muted(name), name
