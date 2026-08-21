"""The highlighting of terms in the source field — and that it erases nothing.

The main one here is `test_both_highlights_survive_together`. The field has one
list of ExtraSelections, `setExtraSelections` replaces it whole, and before
`_refresh_extra_selections` appeared the highlighting of changes called it itself.
A second call from the highlighting of terms would silently erase the diff of a
stale row — an error one notices by eye a week later.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc.core import glossary  # noqa: E402
from pdxloc.core.statuses import Status  # noqa: E402
from pdxloc.db import get_connection  # noqa: E402
from pdxloc.gui import prefs  # noqa: E402
from pdxloc.gui.detail_pane import DetailPane  # noqa: E402

EN = "The Maester of Winterfell waits"
PREV = "The Maester of Winterfell sleeps"


@pytest.fixture
def conn(tmp_path):
    c = get_connection(tmp_path / "p.sqlite3")
    c.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    c.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f.yml')")
    c.commit()
    yield c
    c.close()


def add_unit(conn, *, status=Status.TRANSLATED, prev=None) -> int:
    cur = conn.execute(
        "INSERT INTO units (file_id, key, en_text, prev_en_text, ru_text, status) "
        "VALUES (1, 'k', ?, ?, 'Мейстер ждёт', ?)", (EN, prev, status.value))
    conn.commit()
    return cur.lastrowid


@pytest.fixture
def pane(conn, qtbot):
    """A pane that lets the project go at the end of the test.

    `clear()` here is no decoration: the settings are global, and a `prefs.set`
    from one test wakes the panes of all the others through the common notifier. A
    live pane with a `unit_id` from a closed database will go reading into it —
    exactly as it would in the application, were a project closed without letting
    the pane go. The application does let it go (`editor_screen.close_session`),
    and the test is obliged to as well.
    """
    prefs.set("detail/highlight_terms", True)
    prefs.set("detail/highlight_changes", True)
    glossary.upsert_manual(conn, "Maester", "мейстер")
    p = DetailPane(conn)
    qtbot.addWidget(p)
    p.reload_glossary()
    yield p
    p.clear()


def selections(pane) -> list[tuple[int, int]]:
    return sorted((s.cursor.selectionStart(), s.cursor.selectionEnd())
                  for s in pane.en_view.extraSelections())


def test_an_approved_term_is_highlighted(pane, conn):
    pane.load_unit(add_unit(conn))
    assert selections(pane) == [(EN.index("Maester"), EN.index("Maester") + 7)]


def test_the_translation_hangs_on_the_highlight_as_a_tooltip(pane, conn):
    pane.load_unit(add_unit(conn))
    assert pane.en_view.extraSelections()[0].format.toolTip() == "мейстер"


def test_a_candidate_is_not_highlighted(pane, conn):
    """What is highlighted is what was accepted. A candidate is not yet a decision of the translator."""
    glossary.save_candidates(conn, [glossary.Candidate(
        en_term="Winterfell", ru_term="винтерфелл", score=0.63, pairs=9, runner_up=0.1)])
    pane.reload_glossary()
    pane.load_unit(add_unit(conn))
    assert len(selections(pane)) == 1        # only Maester, without Winterfell


def test_both_highlights_survive_together(pane, conn):
    """A stale row: both the diff of the original and the term are visible.

    Exactly the regression the single owner of setExtraSelections was set up for.
    """
    pane.load_unit(add_unit(conn, status=Status.STALE, prev=PREV))
    found = selections(pane)
    term = (EN.index("Maester"), EN.index("Maester") + 7)
    assert term in found, "термин потерялся под подсветкой изменений"
    assert len(found) > 1, "подсветка изменений потерялась под термином"


def test_turning_terms_off_keeps_the_diff(pane, conn):
    unit_id = add_unit(conn, status=Status.STALE, prev=PREV)
    pane.load_unit(unit_id)
    with_terms = selections(pane)

    pane.highlight_terms_check.setChecked(False)
    without = selections(pane)

    term = (EN.index("Maester"), EN.index("Maester") + 7)
    assert term not in without
    assert without, "дифф обязан остаться — выключали не его"
    assert len(without) < len(with_terms)


def test_turning_changes_off_keeps_the_terms(pane, conn):
    pane.load_unit(add_unit(conn, status=Status.STALE, prev=PREV))
    pane.highlight_check.setChecked(False)
    assert selections(pane) == [(EN.index("Maester"), EN.index("Maester") + 7)]


def test_an_empty_glossary_highlights_nothing(conn, qtbot):
    p = DetailPane(conn)
    qtbot.addWidget(p)
    p.reload_glossary()
    p.load_unit(add_unit(conn))
    assert selections(p) == []
    p.clear()


def test_the_pane_survives_a_closed_project(pane, conn):
    """The project was closed — the pane is obliged to put the terms out, not to fall over."""
    conn.close()
    pane.reload_glossary()
    assert pane._terms == {}
