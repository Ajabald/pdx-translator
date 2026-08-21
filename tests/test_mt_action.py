"""The translation of one row: Ctrl+M from the press to the status.

The network is not opened here: a stub is put into the registry of providers.
What is checked is the whole coupling — the action, the thread, the write, the
status, the rollback — because it tears not in the core but at the joints.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                       # noqa: E402

from pdxloc import project, settings                # noqa: E402
from pdxloc.core import mt_providers, unit_ops      # noqa: E402
from pdxloc.core.scanner import scan_project        # noqa: E402
from pdxloc.core.statuses import Status             # noqa: E402
from pdxloc.gui import prefs                        # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "Gain [GetName]"\n'


class Shouty:
    """A stub of a service: translates into upper case, does not go into the network."""

    name = "shouty"
    label = "Shouty"
    char_limit = 1000

    def __init__(self, config=None):
        self.config = config

    def supports(self, src_locale, tgt_locale) -> bool:
        return True

    def translate_batch(self, texts, src_locale, tgt_locale):
        return [t.upper() for t in texts]


class Broken(Shouty):
    """A service that loses the markup placeholders."""

    name = "broken"

    def translate_batch(self, texts, src_locale, tgt_locale):
        return ["перевод без меток" for _ in texts]


class FakeSettings:
    def __init__(self):
        self.store: dict = {}

    def value(self, key, default=None, type=None):   # noqa: A002
        return self.store.get(key, default)

    def setValue(self, key, value):
        self.store[key] = value


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    # one store for the whole test: a new one per call would remember nothing
    fake = FakeSettings()
    monkeypatch.setattr(settings, "qsettings", lambda: fake)
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    monkeypatch.setitem(mt_providers.PROVIDERS, Shouty.name, Shouty)
    monkeypatch.setitem(mt_providers.PROVIDERS, Broken.name, Broken)

    en = make_tree({"m_l_english.yml": EN}, "en")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en,
                                  tgt_root=make_tree({}, "ru"))
    scan_project(conn, 1)
    conn.close()

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.open_project(path)
    return win


def select_key(win, key: str) -> int:
    """Put the cursor on the row with this key. Returns its unit_id."""
    unit_id = win.conn.execute(
        "SELECT id FROM units WHERE key = ?", (key,)).fetchone()[0]
    win.editor_screen.jump_to_unit(unit_id)
    return unit_id


def run_action(win, qtbot, key: str, provider: str) -> int:
    prefs.set("mt/provider", provider)
    unit_id = select_key(win, key)
    win.actions["mt"].trigger()
    qtbot.waitUntil(lambda: getattr(win.editor_screen, "_mt_thread", None) is None,
                    timeout=5000)
    return unit_id


def status_of(win, unit_id: int) -> str:
    return win.conn.execute(
        "SELECT status FROM units WHERE id = ?", (unit_id,)).fetchone()[0]


# --- the happy path ---

def test_row_is_translated_and_marked_machine(window, qtbot) -> None:
    unit_id = run_action(window, qtbot, "a", Shouty.name)
    row = window.conn.execute(
        "SELECT ru_text, status FROM units WHERE id = ?", (unit_id,)).fetchone()
    assert row["ru_text"] == "HELLO"
    assert row["status"] == Status.MACHINE.value


def test_the_row_can_be_undone(window, qtbot) -> None:
    unit_id = run_action(window, qtbot, "a", Shouty.name)
    batch_id, origin, count = unit_ops.last_batch(window.conn)
    assert (origin, count) == ("machine", 1)
    unit_ops.undo_batch(window.conn, batch_id)
    assert status_of(window, unit_id) == Status.UNTRANSLATED.value


def test_markup_survives(window, qtbot) -> None:
    unit_id = run_action(window, qtbot, "b", Shouty.name)
    assert window.conn.execute(
        "SELECT ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()[0] \
        == "GAIN [GetName]"


def test_machine_row_stays_out_of_the_memory(window, qtbot) -> None:
    run_action(window, qtbot, "a", Shouty.name)
    assert window.conn.execute(
        "SELECT COUNT(*) FROM tm_entries").fetchone()[0] == 0


# --- a refusal and a broken answer ---

def test_a_broken_answer_is_still_written_and_flagged(window, qtbot) -> None:
    """The row has to be shown to a human — so it has to exist."""
    unit_id = run_action(window, qtbot, "b", Broken.name)
    assert window.conn.execute(
        "SELECT ru_text FROM units WHERE id = ?", (unit_id,)).fetchone()[0] \
        == "перевод без меток"
    assert "placeholder" in window.statusBar().currentMessage().lower() or \
        "подстановк" in window.statusBar().currentMessage().lower()


def test_without_a_service_nothing_happens_but_it_is_said(window, qtbot) -> None:
    prefs.set("mt/provider", "none")
    unit_id = select_key(window, "a")
    window.actions["mt"].trigger()
    assert status_of(window, unit_id) == Status.UNTRANSLATED.value
    assert window.statusBar().currentMessage()
