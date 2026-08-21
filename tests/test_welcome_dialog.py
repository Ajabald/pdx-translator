"""The first-start wizard and the reminders with a permanent way out.

Both are shown modally, so in `conftest.py` they are switched off by default for
the whole suite: without that every test with the main window would stand dead on
`exec()`. Here the fixtures are switched off explicitly — otherwise there would
be nothing to check.

The main thing watched for: the wizard is obliged to show **once**, and «Skip»
and the cross are obliged to count as an answer. Otherwise it would meet the user
at every start, and such a thing gets closed unread.
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
    """QSettings without a write into the user's registry."""

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
    """Switch the common stub off: what is checked here is the wizard itself."""
    return None


@pytest.fixture
def no_reminders():
    """Switch the common stub off: what is checked here is `ask_once` itself."""
    return None


@pytest.fixture
def shown(monkeypatch):
    """Count the showings of the wizard without really opening it.

    `exec()` is modal and blocks in the offscreen mode too. We substitute exactly
    that and not `needed`: what has to be checked is the whole chain "is it needed
    → was it shown → was it marked", and with `needed` substituted half of it
    would be gone.
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
    """The main window without opening a project — the wizard comes before it."""
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


# --- the wizard shows once ---

def test_wizard_shows_on_a_fresh_install(window, shown, store) -> None:
    window()
    assert len(shown) == 1
    assert store.value(DONE_KEY) is True


def test_wizard_does_not_come_back(window, shown) -> None:
    """A second start is obliged to go past: the mark is set by the showing, not the answer."""
    window()
    window()
    assert len(shown) == 1


def test_wizard_is_not_needed_once_marked(store) -> None:
    assert welcome_dialog.needed()
    welcome_dialog.mark_done()
    assert not welcome_dialog.needed()


# --- «Skip» and the cross are answers in their own right ---

def test_skip_marks_the_wizard_done(qtbot, store) -> None:
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    assert welcome_dialog.needed()
    dlg.skip_btn.click()
    assert not welcome_dialog.needed()


def test_closing_with_the_cross_marks_the_wizard_done(qtbot, store) -> None:
    """The cross is the same answer as «Skip».

    Were it to set no mark, the wizard would meet at every start everyone who
    closes windows by the cross — and that is most people.
    """
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    dlg.reject()                      # the same as pressing the cross
    assert not welcome_dialog.needed()


def test_the_last_step_finishes_the_wizard(qtbot, store) -> None:
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    for _ in range(dlg.pages.count() - 1):
        dlg.next_btn.click()
    assert dlg.pages.currentIndex() == dlg.pages.count() - 1
    dlg.next_btn.click()              # «Done»
    assert not welcome_dialog.needed()


def test_database_step_tells_the_truth_about_what_is_there(qtbot, store,
                                                           monkeypatch) -> None:
    """The text of the step depends on whether there are databases: lying either way will not do."""
    monkeypatch.setattr(project, "all_tm_databases", lambda: [])
    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    dlg._go(1)
    assert "no translation memory databases" in dlg.db_text.text().lower()

    monkeypatch.setattr(project, "all_tm_databases", lambda: ["a", "b"])
    dlg._go(1)
    assert "2" in dlg.db_text.text()


# --- the wizard does not contradict itself ---

def test_the_language_list_shows_the_language_in_effect(qtbot, store,
                                                        monkeypatch) -> None:
    """The list is obliged to stand in the language the window is drawn in.

    It stood in the language of the system, while the window is drawn in the
    language from `apply_saved`. Let those two diverge — and the first thing the
    wizard does is lie about what it is showing: the headings in Chinese over a
    list where «Русский» is chosen. Reachable without any rigging: the hive of the
    former application name brings the language over through
    `adopt_previous_settings`, while `first_run_done` is by definition not in the
    new hive.

    Only `current` is substituted: substitute `system_default` as well, and the
    test would stop failing on the old code wherever the locale of the machine
    happened to match.
    """
    from pdxloc.gui import language

    others = [code for code in language.available()
              if code != language.system_default()]
    assert others, "не с чем сравнивать: в сборке один язык"
    in_effect = others[0]
    monkeypatch.setattr(language, "current", lambda: in_effect)

    dlg = WelcomeDialog()
    qtbot.addWidget(dlg)
    assert dlg.language_combo.currentData() == in_effect


# --- «Build a database…» leads through to the building window ---

def test_building_the_first_database_needs_no_project(window, shown,
                                                      monkeypatch) -> None:
    """The main complaint about 0.1.0: the button of the wizard did exactly nothing.

    The memory window demanded an open project, and at the first start there is
    not a single one, and `languages(None)` fell over right in the slot. An
    assembled application has no console, so not even an error message came out.

    We check the path whole, from the main window: only `exec()` is substituted —
    it is modal and blocks in the offscreen mode too.
    """
    from pdxloc.gui.tm_window import TmWindow

    opened: list[TmWindow] = []
    monkeypatch.setattr(TmWindow, "exec", lambda self: (opened.append(self), 0)[1])

    win = window()
    assert win.conn is None                 # there is no project — that is what we came here for
    win._build_tm_database()

    assert len(opened) == 1
    tabs = opened[0].tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["Build a database"]


def test_the_database_step_notices_the_database_it_just_built(
        qtbot, store, monkeypatch) -> None:
    """Otherwise the wizard would assure that there are no databases right after building one."""
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


# --- the reminders fall silent forever and answer «no» ---

def _answer(monkeypatch, checked: bool, button=QMessageBox.Yes):
    """Show a reminder, with the «do not ask again» tick set (or not)."""
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
    """The default is a careful one: the tick unties from the question, it does not agree.

    Answer a silenced question «yes» — and the offer would start carrying itself
    out, silently and at every start.
    """
    prefs.set_flag(f"{ask.PREFIX}{ask.NO_TM_DATABASES}", True)
    assert ask.ask_once(None, ask.NO_TM_DATABASES, "Заголовок",
                        "Текст") == QMessageBox.No


def test_every_reminder_can_be_brought_back(qtbot, store, monkeypatch) -> None:
    """A setting that cannot be undone is a trap."""
    _answer(monkeypatch, checked=True)
    for name in ask.KNOWN:
        ask.ask_once(None, name, "Заголовок", "Текст")
        assert ask.muted(name), name

    ask.unmute_all()
    for name in ask.KNOWN:
        assert not ask.muted(name), name
