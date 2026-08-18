"""Окно глоссария: прогон, разбор кандидатов, счётчики, гашение потока."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QItemSelectionModel, Qt  # noqa: E402

from pdxloc.core import glossary  # noqa: E402
from pdxloc.core.glossary import APPROVED, CANDIDATE, REJECTED  # noqa: E402
from pdxloc.db import get_connection  # noqa: E402
from pdxloc.gui.glossary_window import GlossaryWindow  # noqa: E402

PAIRS = [("The Maester waits", "Мейстер ждёт"),
         ("A Maester speaks", "Мейстер говорит"),
         ("Maester arrives now", "Мейстер приходит"),
         ("The Maester reads", "Мейстер читает")]


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "p.sqlite3"
    conn = get_connection(path)
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    conn.executemany(
        "INSERT INTO tm_entries (en_hash, en_text, ru_text) VALUES (?, ?, ?)",
        [(f"h{i}", en, ru) for i, (en, ru) in enumerate(PAIRS)])
    conn.commit()
    yield conn, path
    conn.close()


@pytest.fixture
def window(project, qtbot):
    conn, path = project
    w = GlossaryWindow(conn, path)
    qtbot.addWidget(w)
    yield w
    w.candidates.shutdown()
    w.terms.shutdown()


def run_extraction(window, qtbot):
    """Нажать «Найти термины» и дождаться конца прогона."""
    with qtbot.waitSignal(window.candidates.runFinished, timeout=5000):
        window.candidates.run_btn.click()


# --- прогон ---------------------------------------------------------------


def test_finding_terms_fills_the_candidates_tab(window, qtbot, project):
    conn, _ = project
    run_extraction(window, qtbot)
    found = {e.en_term.lower() for e in glossary.rows(conn, status=CANDIDATE)}
    assert "maester" in found
    assert window.candidates.model.rowCount() > 0


def test_the_run_button_comes_back_after_the_run(window, qtbot):
    run_extraction(window, qtbot)
    assert not window.candidates.is_busy()
    assert not window.candidates.progress.isVisible()


def test_a_second_run_adds_nothing_new(window, qtbot, project):
    conn, _ = project
    run_extraction(window, qtbot)
    before = len(glossary.rows(conn))
    run_extraction(window, qtbot)
    assert len(glossary.rows(conn)) == before


# --- разбор ---------------------------------------------------------------


def select_first_row(tab):
    index = tab.model.index(0, 0)
    tab.table.selectionModel().select(
        index, QItemSelectionModel.Select | QItemSelectionModel.Rows)


def test_accepting_moves_the_row_to_the_terms_tab(window, qtbot, project):
    conn, _ = project
    run_extraction(window, qtbot)
    select_first_row(window.candidates)
    window.candidates.accept_btn.click()

    assert glossary.rows(conn, status=APPROVED)
    window.terms.reload()
    assert window.terms.model.rowCount() == 1


def test_rejecting_takes_the_row_out_of_the_queue(window, qtbot, project):
    conn, _ = project
    run_extraction(window, qtbot)
    before = window.candidates.model.rowCount()
    select_first_row(window.candidates)
    window.candidates.reject_btn.click()

    assert glossary.rows(conn, status=REJECTED)
    assert window.candidates.model.rowCount() == before - 1


def test_accepting_tells_the_editor_to_repaint(window, qtbot):
    """Сигнал наружу — то, чем окно подсвечивает термин, не закрываясь."""
    run_extraction(window, qtbot)
    select_first_row(window.candidates)
    with qtbot.waitSignal(window.glossaryChanged, timeout=1000):
        window.candidates.accept_btn.click()


def test_deciding_on_an_empty_selection_does_nothing(window, qtbot, project):
    conn, _ = project
    run_extraction(window, qtbot)
    window.candidates.table.clearSelection()
    window.candidates.accept_btn.click()
    assert glossary.rows(conn, status=APPROVED) == []


# --- термины руками -------------------------------------------------------


def test_a_term_can_be_added_by_hand(window, project):
    conn, _ = project
    window.terms.en_input.setText("Winterfell")
    window.terms.ru_input.setText("Винтерфелл")
    window.terms.add_btn.click()

    assert glossary.approved_terms(conn) == {"winterfell": "Винтерфелл"}
    assert window.terms.en_input.text() == ""       # поля освобождены под следующий


def test_a_half_filled_term_is_not_added(window, project):
    conn, _ = project
    window.terms.en_input.setText("Winterfell")
    window.terms.add_btn.click()
    assert glossary.rows(conn) == []


def test_a_term_is_edited_in_place(window, project):
    conn, _ = project
    glossary.upsert_manual(conn, "Winterfell", "Винтерфел")
    window.terms.reload()
    window.terms.model.setData(window.terms.model.index(0, 1), "Винтерфелл", Qt.EditRole)
    assert glossary.approved_terms(conn) == {"winterfell": "Винтерфелл"}


def test_an_emptied_term_is_refused(window, project):
    """Пустой термин подсвечивать нечем — правка не принимается."""
    conn, _ = project
    glossary.upsert_manual(conn, "Winterfell", "Винтерфелл")
    window.terms.reload()
    assert not window.terms.model.setData(
        window.terms.model.index(0, 1), "   ", Qt.EditRole)
    assert glossary.approved_terms(conn) == {"winterfell": "Винтерфелл"}


def test_deleting_a_term_stops_the_highlight(window, project):
    conn, _ = project
    glossary.upsert_manual(conn, "Winterfell", "Винтерфелл")
    window.terms.reload()
    select_first_row(window.terms)
    window.terms.delete_btn.click()
    assert glossary.approved_terms(conn) == {}


# --- нижняя полоса --------------------------------------------------------


def test_the_bottom_bar_shows_the_active_tab(window, qtbot, project):
    """Полоса внизу — общая, и говорить обязана про открытую вкладку.

    Термин заводится мимо окна: так проверяется, что при переходе на вкладку
    она перечитывает данные, а не показывает счёт с момента открытия.
    """
    conn, _ = project
    glossary.upsert_manual(conn, "Winterfell", "Винтерфелл")

    window.tabs.setCurrentWidget(window.candidates)
    assert window.status_label.text() == window.candidates.status_text()

    window.tabs.setCurrentWidget(window.terms)
    assert window.status_label.text() == window.terms.status_text()
    assert "1" in window.status_label.text()


def test_counts_report_every_status(window, qtbot, project):
    conn, _ = project
    run_extraction(window, qtbot)
    select_first_row(window.candidates)
    window.candidates.reject_btn.click()
    assert glossary.counts(conn)[REJECTED] == 1


# --- закрытие -------------------------------------------------------------


def test_shutdown_stops_the_thread(window, qtbot):
    run_extraction(window, qtbot)
    window.candidates.shutdown()
    assert window.candidates._thread is None


def test_closing_while_idle_asks_nothing(window, qtbot):
    """Вопрос при закрытии — только если счёт идёт."""
    assert window._confirm_close_while_running() is True
