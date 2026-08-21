"""The three-position sorting of the columns of the rows table."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import unit_ops  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.core.statuses import Status  # noqa: E402
from pdxloc.gui.sorting import FIRST, OFF, SECOND, SortState  # noqa: E402
from pdxloc.gui.units_model import (  # noqa: E402
    COL_CHANGE, COL_ISSUES, COL_KEY, COL_QS_FIRST, COL_RU, COL_STATUS,
    UnitFilters, UnitsTableModel, _text_key,
)

# the keys are deliberately out of alphabetical order and with numbers: 10 must not come before 2
EN = (
    'l_english:\n'
    ' agot_10:0 "Zulu text"\n'
    ' agot_2:0 "Alpha text"\n'
    ' agot_1:0 "Mike text"\n'
    ' agot_3:0 "Bravo text"\n'
)
RU = 'l_russian:\n agot_2:0 "Альфа"\n agot_1:0 "Майк"\n'


# --- the state machine, without Qt --------------------------------------


def test_three_clicks_return_to_the_natural_order() -> None:
    s = SortState()
    s.click(COL_KEY)
    assert (s.column, s.step) == (COL_KEY, FIRST)
    s.click(COL_KEY)
    assert (s.column, s.step) == (COL_KEY, SECOND)
    s.click(COL_KEY)
    assert (s.column, s.step) == (None, OFF)


def test_click_on_another_column_resets_the_previous_one() -> None:
    s = SortState()
    s.click(COL_KEY)
    s.click(COL_KEY)               # brought it to descending
    s.click(COL_STATUS)            # and went off to the neighbouring column
    assert (s.column, s.step) == (COL_STATUS, FIRST)


def test_natural_key_compares_numbers_as_numbers() -> None:
    assert _text_key("agot_2") < _text_key("agot_10")
    assert _text_key("agot_2") < _text_key("agot_2a")


def test_empty_text_sorts_last() -> None:
    assert _text_key("яблоко") < _text_key("")
    assert _text_key("яблоко") < _text_key(None)


# --- the model on live data ---------------------------------------------


@pytest.fixture
def model(tmp_path, make_tree, monkeypatch):
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    m = UnitsTableModel(conn)
    m.reload(1, UnitFilters())
    yield m
    conn.close()


def ids(m: UnitsTableModel) -> list[int]:
    return [m.unit_id_at(i) for i in range(m.rowCount())]


def keys(m: UnitsTableModel) -> list[str]:
    return [m.raw_cell(i, COL_KEY) for i in range(m.rowCount())]


def test_sorting_cycle_restores_the_exact_original_order(model) -> None:
    natural = ids(model)
    model.set_sort((COL_KEY, False))
    assert ids(model) != natural or len(natural) < 2
    model.set_sort((COL_KEY, True))
    model.set_sort(None)
    assert ids(model) == natural


def test_key_column_sorts_numbers_numerically(model) -> None:
    model.set_sort((COL_KEY, False))
    assert keys(model) == ["agot_1", "agot_2", "agot_3", "agot_10"]
    model.set_sort((COL_KEY, True))
    assert keys(model) == ["agot_10", "agot_3", "agot_2", "agot_1"]


def test_row_index_survives_every_step_of_the_cycle(model) -> None:
    """`_row_by_id` is obliged to be rebuilt at every rearrangement.

    refresh_row, jump_to_unit and the restoration of the selection go by it — if it
    falls behind, an edit will travel into a foreign row.
    """
    for spec in ((COL_KEY, False), (COL_KEY, True), None, (COL_STATUS, False)):
        model.set_sort(spec)
        for i in range(model.rowCount()):
            assert model.row_of_unit(model.unit_id_at(i)) == i


def test_row_index_survives_sorting_with_the_issues_filter(model) -> None:
    model.set_sort((COL_ISSUES, False))
    model.reload(1, UnitFilters(only_issues=True))
    for i in range(model.rowCount()):
        assert model.row_of_unit(model.unit_id_at(i)) == i


def test_status_column_sorts_in_work_order_not_alphabet(model) -> None:
    """«Untranslated» is above «Auto», though the alphabet would order the opposite."""
    model.set_sort((COL_STATUS, False))
    statuses = [model.row_data(i)["status"] for i in range(model.rowCount())]
    assert statuses.index(Status.UNTRANSLATED.value) < statuses.index(
        Status.TRANSLATED.value)


def test_empty_translations_go_last_ascending(model) -> None:
    model.set_sort((COL_RU, False))
    texts = [model.raw_cell(i, COL_RU) for i in range(model.rowCount())]
    filled = [t for t in texts if t]
    assert texts[:len(filled)] == filled       # the empty ones are all in the tail


def test_change_column_puts_meaningful_before_cosmetic(model) -> None:
    rows = model.rowCount()
    order = {"meaningful": 0, "cosmetic": 1}
    model.set_sort((COL_CHANGE, False))
    kinds = [model.raw_cell(i, COL_CHANGE) for i in range(rows)]
    ranks = [order.get(k, 2) for k in kinds]
    assert ranks == sorted(ranks)


def test_sort_survives_a_filter_change(model) -> None:
    model.set_sort((COL_KEY, True))
    model.reload(1, UnitFilters(search="text"))
    assert keys(model) == sorted(keys(model), key=_text_key, reverse=True)


def test_issue_column_orders_by_count_then_severity(model) -> None:
    """With an equal number of remarks the row that holds an error is higher."""
    model._issue_rank = {model.unit_id_at(0): (1, 0),    # one warning
                         model.unit_id_at(1): (1, 1),    # one error
                         model.unit_id_at(2): (2, 0)}    # two warnings
    model.set_sort((COL_ISSUES, False))
    assert [model._issue_rank.get(i, (0, 0)) for i in ids(model)[:3]] == [
        (2, 0), (1, 1), (1, 0)]


# --- the interaction with the table -------------------------------------


@pytest.fixture
def window(tmp_path, make_tree, qtbot, monkeypatch):
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    conn.close()

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.project_path = path
    win.open_project(path)
    return win


def test_header_click_on_quick_column_does_not_sort(window) -> None:
    """✓ ✗ C И are buttons: a click on their header must not shuffle the table."""
    before = ids(window.editor_screen.model)
    window.editor_screen._on_header_clicked(COL_QS_FIRST)
    assert window.editor_screen.state.sort_spec is None
    assert ids(window.editor_screen.model) == before


def test_quick_click_changes_the_status_of_the_row_it_hit(window) -> None:
    """After a sort a click on «И» is obliged to hit its own row and not the neighbouring one."""
    screen = window.editor_screen
    screen._on_header_clicked(COL_KEY)
    screen._on_header_clicked(COL_KEY)          # descending — the order is certainly not the same
    row = 1
    target_id = screen.model.unit_id_at(row)
    index = screen.model.index(row, COL_QS_FIRST + 3)   # the «И» column
    screen._on_table_clicked(index)
    status = screen.conn.execute(
        "SELECT status FROM units WHERE id = ?", (target_id,)).fetchone()["status"]
    assert status == Status.IGNORED.value


def test_selection_survives_sorting(window) -> None:
    screen = window.editor_screen
    screen._select_row(2)
    picked = screen.detail.unit_id
    screen._on_header_clicked(COL_KEY)
    assert screen.detail.unit_id == picked
    assert screen.model.row_of_unit(picked) is not None


def test_sort_menu_mirrors_the_header(window) -> None:
    window.editor_screen._on_header_clicked(COL_STATUS)
    assert window.sort_actions[COL_STATUS].isChecked()
    assert not window.sort_desc_action.isChecked()
    window.editor_screen._on_header_clicked(COL_STATUS)
    assert window.sort_desc_action.isChecked()
    window.editor_screen._on_header_clicked(COL_STATUS)
    assert window.sort_actions[None].isChecked()
    assert not window.sort_desc_action.isEnabled()


def test_sorting_does_not_hit_the_database(window, monkeypatch) -> None:
    """A click on a header is a rearrangement in memory, not SQL with a recount of the checks."""
    screen = window.editor_screen
    calls = []
    original = screen.model.reload
    monkeypatch.setattr(screen.model, "reload",
                        lambda *a, **k: (calls.append(1), original(*a, **k))[1])
    screen._on_header_clicked(COL_KEY)
    assert calls == []
    # while a change of the filter does bring one
    screen.state.set_status(Status.UNTRANSLATED.value)
    assert calls == [1]


def test_status_change_keeps_the_row_in_place(window) -> None:
    """The row must not travel out from under the cursor at the moment a status is set."""
    screen = window.editor_screen
    screen._on_header_clicked(COL_STATUS)
    before = ids(screen.model)
    unit_id = screen.model.unit_id_at(0)
    unit_ops.set_status(screen.conn, [unit_id], Status.IGNORED)
    screen.model.refresh_row(unit_id)
    assert ids(screen.model) == before
