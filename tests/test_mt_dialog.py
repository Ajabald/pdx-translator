"""Bulk machine translation: the reach, the run, the rollback.

There is no network here: a stub is put into the registry of providers. What is
checked is what tears at the joints — which rows get into the reach, that the run
writes in one batch, and that broken rows show in the summary instead of getting
lost.

The main thing watched over in the reach: **the reviewed and the custom we never
touch**. There a decision has already been made by a human, and overwriting it by
machine is the worst this operation can do.
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
from pdxloc.gui.mt_dialog import MtDialog, collect_rows   # noqa: E402

EN = ('l_english:\n'
      ' a:0 "Hello"\n'
      ' b:0 "World"\n'
      ' c:0 "Gold"\n'
      ' d:0 "[GetName]"\n'
      ' e:0 "Fire"\n')


class Shouty:
    name = "shouty"
    label = "Shouty"
    char_limit = 1000

    def __init__(self, config=None):
        self.config = config

    def supports(self, src_locale, tgt_locale) -> bool:
        return True

    def translate_batch(self, texts, src_locale, tgt_locale):
        return [t.upper() for t in texts]


class Dropper(Shouty):
    """Loses substitutions — we write the row, but we mark it."""

    name = "dropper"

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
def session(tmp_path, make_tree, qtbot, monkeypatch):
    fake = FakeSettings()
    monkeypatch.setattr(settings, "qsettings", lambda: fake)
    monkeypatch.setitem(mt_providers.PROVIDERS, Shouty.name, Shouty)
    monkeypatch.setitem(mt_providers.PROVIDERS, Dropper.name, Dropper)

    en = make_tree({"m_l_english.yml": EN}, "en")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en,
                                  tgt_root=make_tree({}, "ru"))
    scan_project(conn, 1)
    # we lay the statuses out: b is reviewed, c is custom, e is stale with a translation
    conn.execute("UPDATE units SET ru_text='Мир', status=? WHERE key='b'",
                 (Status.REVIEWED.value,))
    conn.execute("UPDATE units SET ru_text='Золото', status=? WHERE key='c'",
                 (Status.CUSTOM.value,))
    conn.execute("UPDATE units SET ru_text='Огонь', status=? WHERE key='e'",
                 (Status.STALE.value,))
    conn.commit()
    prefs.set("mt/provider", Shouty.name)
    prefs.set("mt/throttle_ms", 0)
    return conn, path


def keys(rows) -> set[str]:
    return {r.key for r in rows}


# --- the reach ---

def test_untranslated_scope_skips_what_a_human_decided(session) -> None:
    conn, _ = session
    rows = collect_rows(conn, 1, "untranslated")
    assert keys(rows) == {"a"}          # b/c are decided by a human, d is markup, e is stale


def test_markup_only_rows_are_never_sent(session) -> None:
    """A bare [GetName] in a paid service is money for nothing."""
    conn, _ = session
    for scope in ("untranslated", "untranslated_auto", "all"):
        assert "d" not in keys(collect_rows(conn, 1, scope))


def test_whole_project_still_spares_reviewed_and_custom(session) -> None:
    conn, _ = session
    assert keys(collect_rows(conn, 1, "all")) == {"a"}


def test_outdated_rows_join_only_by_an_explicit_tick(session) -> None:
    """A human's labour is invested in them — overwriting silently will not do."""
    conn, _ = session
    assert "e" not in keys(collect_rows(conn, 1, "all"))
    assert "e" in keys(collect_rows(conn, 1, "all", include_stale=True))


def test_selection_scope_is_exactly_the_selection(session) -> None:
    conn, _ = session
    unit_id = conn.execute("SELECT id FROM units WHERE key='a'").fetchone()[0]
    rows = collect_rows(conn, 1, "selected", selected_ids=[unit_id])
    assert keys(rows) == {"a"}
    assert collect_rows(conn, 1, "selected", selected_ids=[]) == []


# --- the run ---

def run_dialog(session, qtbot, provider: str, scope: str = "all"):
    conn, path = session
    prefs.set("mt/provider", provider)
    dialog = MtDialog(conn, 1, path)
    qtbot.addWidget(dialog)
    dialog.scope_buttons[scope].setChecked(True)
    dialog._start()
    qtbot.waitUntil(lambda: dialog.report is not None, timeout=10000)
    return dialog


def test_a_run_writes_machine_rows_in_one_batch(session, qtbot) -> None:
    conn, _ = session
    dialog = run_dialog(session, qtbot, Shouty.name)
    assert dialog.report.rows_translated == 1

    row = conn.execute(
        "SELECT ru_text, status FROM units WHERE key='a'").fetchone()
    assert row["ru_text"] == "HELLO"
    assert row["status"] == Status.MACHINE.value

    batch_id, origin, count = unit_ops.last_batch(conn)
    assert (origin, count) == ("machine", 1)
    assert unit_ops.undo_batch(conn, batch_id) == 1
    assert conn.execute(
        "SELECT status FROM units WHERE key='a'").fetchone()[0] \
        == Status.UNTRANSLATED.value


def test_a_broken_row_is_written_and_shown(session, qtbot) -> None:
    """A human has to see it — so it has to exist."""
    conn, _ = session
    dialog = run_dialog(session, qtbot, Dropper.name)
    assert dialog.report.rows_translated == 1
    assert len(dialog.report.placeholders_lost) == 0     # «Hello» has no placeholders

    # a row with markup gets into the reach only if it is not markup alone
    conn.execute("UPDATE units SET en_text='Gain [GetName]' WHERE key='a'")
    conn.execute("UPDATE units SET ru_text=NULL, status=? WHERE key='a'",
                 (Status.UNTRANSLATED.value,))
    conn.commit()
    dialog = run_dialog(session, qtbot, Dropper.name)
    assert len(dialog.report.placeholders_lost) == 1
    assert "a" in dialog.summary.text()


def test_the_dialog_refuses_to_start_without_a_service(session, qtbot) -> None:
    conn, path = session
    prefs.set("mt/provider", "none")
    dialog = MtDialog(conn, 1, path)
    qtbot.addWidget(dialog)
    assert not dialog.start_button.isEnabled()


# --- the manual web mode ---

def manual_dialog(session, qtbot):
    conn, path = session
    dialog = MtDialog(conn, 1, path)
    qtbot.addWidget(dialog)
    dialog.scope_buttons["all"].setChecked(True)
    dialog.tabs.setCurrentIndex(1)
    return dialog


def test_manual_mode_hides_the_markup_and_writes_the_result(session, qtbot) -> None:
    conn, _ = session
    conn.execute("UPDATE units SET en_text='Gain [GetName]' WHERE key='a'")
    conn.commit()

    dialog = manual_dialog(session, qtbot)
    out = dialog.manual_out.toPlainText()
    assert "[GetName]" not in out          # the markup is hidden from the human as well
    assert "===0===" in out

    dialog.manual_in.setPlainText(out.replace("Gain", "Получить"))
    dialog.manual_apply.click()

    row = conn.execute(
        "SELECT ru_text, status FROM units WHERE key='a'").fetchone()
    assert row["ru_text"] == "Получить [GetName]"
    assert row["status"] == Status.MACHINE.value


def test_manual_mode_refuses_a_damaged_batch(session, qtbot) -> None:
    """From a batch with a divergence nothing is applied."""
    conn, _ = session
    dialog = manual_dialog(session, qtbot)
    dialog.manual_in.setPlainText("Привет без разделителей")
    dialog.manual_apply.click()

    assert dialog.manual_note.text()
    assert conn.execute(
        "SELECT ru_text FROM units WHERE key='a'").fetchone()[0] is None


def test_manual_mode_works_without_a_service(session, qtbot) -> None:
    """The only mode for somebody who has not a single subscription."""
    conn, path = session
    prefs.set("mt/provider", "none")
    dialog = MtDialog(conn, 1, path)
    qtbot.addWidget(dialog)
    dialog.scope_buttons["all"].setChecked(True)
    dialog.tabs.setCurrentIndex(1)
    assert dialog.manual_out.toPlainText()
    assert dialog.manual_apply.isEnabled()


def test_manual_mode_can_use_ascii_placeholders(session, qtbot) -> None:
    """Through a browser field and the clipboard ⟦N⟧ gets mangled or vanishes."""
    conn, _ = session
    conn.execute("UPDATE units SET en_text='Gain [GetName]' WHERE key='a'")
    conn.commit()
    prefs.set("mt/manual_ascii_tokens", True)

    dialog = manual_dialog(session, qtbot)
    out = dialog.manual_out.toPlainText()
    assert "{{0}}" in out and "⟦" not in out

    dialog.manual_in.setPlainText(out.replace("Gain", "Получить"))
    dialog.manual_apply.click()
    assert conn.execute(
        "SELECT ru_text FROM units WHERE key='a'").fetchone()[0] \
        == "Получить [GetName]"


def test_the_estimate_counts_rows_and_requests(session, qtbot) -> None:
    conn, path = session
    dialog = MtDialog(conn, 1, path)
    qtbot.addWidget(dialog)
    dialog.scope_buttons["all"].setChecked(True)
    text = dialog.estimate.text()
    assert "1" in text          # exactly one row passes the reach
