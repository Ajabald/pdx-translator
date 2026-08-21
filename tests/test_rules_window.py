"""The check setup window: the edits reach the table instead of staying in the window.

The check is called from three places — the «!» column, the recount of one row
and the F6 report. All three used to call `qa.check_unit` without a set, that is,
always with the built-in values; a setting that failed to reach even one of them
would diverge in the numbers on one and the same project.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from pdxloc import project, settings  # noqa: E402
from pdxloc.core import qa_rules  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402
from pdxloc.gui import rules_state  # noqa: E402
from pdxloc.gui.rules_window import GLOBAL, PROJECT, RulesWindow  # noqa: E402

# «Привет » — an edge space that is not in the original: edge_space fires under
# any defaults, so the rule will do as a test subject.
EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет "\n b:0 "Мир"\n'


@pytest.fixture
def project_file(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    conn.close()
    return path


@pytest.fixture
def conn(project_file):
    c = project.open_project(project_file, [])
    rules_state.open_project(c)
    yield c
    c.close()
    rules_state.close_project()


@pytest.fixture
def window(qtbot, conn, project_file):
    win = RulesWindow(conn, project_file)
    qtbot.addWidget(win)
    # the background counter is not needed in a test: it goes into the database on its own connection
    win.rules_tab._debounce.stop()
    yield win
    win.rules_tab.shutdown()


def rule_item(win, rule_id):
    return win.rules_tab._item_of(rule_id)


# --- the tree and the edits ---------------------------------------------


def test_every_rule_is_shown_under_its_category(window) -> None:
    shown = {i.data(0, Qt.UserRole) for i in window.rules_tab._items()}
    assert shown == {r.id for r in qa_rules.BUILTIN_RULES}


def test_unchecking_a_rule_disables_it_after_save(window, conn) -> None:
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)
    window._save()
    assert not rules_state.ruleset().get("edge_space").enabled
    # and this is written into the project file, not only into memory
    assert project.get_qa_overlay(conn)["rules"]["edge_space"] == {"enabled": False}


def test_param_edit_reaches_the_saved_ruleset(window) -> None:
    window.rules_tab.tree.setCurrentItem(rule_item(window, "edge_space"))
    box = window.rules_tab.params._widgets["compare_with_source"]
    box.setChecked(False)
    window._save()
    assert rules_state.ruleset().get("edge_space").params[
        "compare_with_source"] is False


def test_severity_edit_reaches_the_saved_ruleset(window) -> None:
    tab = window.rules_tab
    tab.tree.setCurrentItem(rule_item(window, "same_as_en"))
    tab.severity_combo.setCurrentIndex(
        tab.severity_combo.findData(qa_rules.INFO))
    window._save()
    assert rules_state.ruleset().severity("same_as_en") == qa_rules.INFO


def test_saved_overlay_is_a_delta_not_a_dump(window, conn) -> None:
    """A full dump would freeze the set at the current version of the application."""
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)
    window._save()
    assert set(project.get_qa_overlay(conn)["rules"]) == {"edge_space"}


def test_reset_rule_returns_the_default(window) -> None:
    tab = window.rules_tab
    tab.tree.setCurrentItem(rule_item(window, "edge_space"))
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)
    tab._reset_rule()
    assert tab._rules.get("edge_space").enabled


# --- presets and scopes -------------------------------------------------


def test_preset_choice_is_stored_and_applied(window, conn) -> None:
    tab = window.rules_tab
    tab.preset_combo.setCurrentIndex(tab.preset_combo.findData("quiet"))
    window._save()
    assert project.get_qa_overlay(conn)["preset"] == "quiet"
    assert "edge_space" not in rules_state.ruleset().active_ids()


def test_global_scope_writes_the_file_next_to_the_app(window) -> None:
    tab = window.rules_tab
    tab.scope_combo.setCurrentIndex(tab.scope_combo.findData(GLOBAL))
    tab.preset_combo.setCurrentIndex(tab.preset_combo.findData("quiet"))
    window._save()
    assert settings.qa_rules_path().is_file()
    assert rules_state.preset() == "quiet"


def test_project_scope_does_not_touch_the_global_file(window) -> None:
    tab = window.rules_tab
    assert tab.scope == PROJECT
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)
    window._save()
    assert not settings.qa_rules_path().exists()


def test_project_edits_do_not_survive_closing_the_project(window, conn) -> None:
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)
    window._save()
    rules_state.close_project()
    assert rules_state.ruleset().get("edge_space").enabled


# --- a try on a pair, and the examples ----------------------------------


def test_hit_counter_counts_the_project(project_file, conn) -> None:
    """The counter is half the point of the window: by it one decides if a rule is noisy.

    We drive `run()` directly, without a thread: what is checked is the query and
    the counting, not the mechanics of QThread (that is shared with `ScanWorker`).
    """
    from pdxloc.gui.rules_window import _CountWorker

    seen: list[tuple[dict, int]] = []
    worker = _CountWorker(project_file, qa_rules.default_ruleset())
    worker.done.connect(lambda counts, n: seen.append((counts, n)))
    worker.run()

    counts, scanned = seen[0]
    assert scanned == 2                       # both rows are translated
    assert counts.get("edge_space") == 1      # only «Привет »


def test_hit_counter_follows_the_rules_it_was_given(project_file) -> None:
    from pdxloc.gui.rules_window import _CountWorker

    seen: list[dict] = []
    worker = _CountWorker(project_file, qa_rules.resolve({"preset": "quiet"}))
    worker.done.connect(lambda counts, _: seen.append(counts))
    worker.run()
    assert "edge_space" not in seen[0]


def test_probe_answers_for_a_pair(window) -> None:
    window.rules_tab.set_probe("Hello", "Привет ")
    expected = qa_rules.BY_ID["edge_space"].message_text()
    assert expected in window.rules_tab.probe_label.text()


def test_probe_follows_the_edited_rules(window) -> None:
    tab = window.rules_tab
    tab.set_probe("Hello", "Привет ")
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)
    assert tab.probe_label.text() == "No issues."


def test_take_current_row_fills_the_probe(qtbot, conn, project_file) -> None:
    win = RulesWindow(conn, project_file,
                      current_pair=lambda: ("Hello", "Привет "))
    qtbot.addWidget(win)
    win.rules_tab._debounce.stop()
    try:
        assert win.rules_tab.take_row_btn.isEnabled()
        win.rules_tab.take_row_btn.click()
        assert win.rules_tab.probe_en.toPlainText() == "Hello"
        assert win.rules_tab.probe_ru.toPlainText() == "Привет "
    finally:
        win.rules_tab.shutdown()


def test_examples_are_shown_and_agree_with_the_rule(window) -> None:
    tab = window.rules_tab
    tab.tree.setCurrentItem(rule_item(window, "edge_space"))
    rule = qa_rules.BY_ID["edge_space"]
    assert tab.examples.rowCount() == len(rule.example_bad) + len(rule.example_ok)
    for row in range(tab.examples.rowCount()):
        assert tab.examples.item(row, 2).text() == tab.examples.item(row, 3).text()


# --- rules of one's own -------------------------------------------------


def add_own_rule(monkeypatch, window, title="Ellipsis",
                 kind="forbidden_chars") -> str:
    """Set up a rule of one's own the way a user does it.

    The setup dialog is modal: without silencing it the test suite would stand
    dead on `exec()` — exactly as the first-start wizard once did.
    """
    from pdxloc.gui import rules_window as rw

    class Stub:
        def __init__(self, parent=None):
            pass

        def exec(self):
            from PySide6.QtWidgets import QDialog
            return QDialog.Accepted

        def values(self):
            return title, kind

    monkeypatch.setattr(rw, "NewRuleDialog", Stub)
    before = {r.id for r in window.rules_tab._rules}
    window.rules_tab._add_user_rule()
    return next(iter({r.id for r in window.rules_tab._rules} - before))


def group_titles(window) -> list[str]:
    tree = window.rules_tab.tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def rules_under(item) -> set[str]:
    """The rule identifiers in a subtree — the walk is just as recursive."""
    found = set()
    for i in range(item.childCount()):
        child = item.child(i)
        rule_id = child.data(0, Qt.UserRole)
        found |= {rule_id} if rule_id else rules_under(child)
    return found


def test_tree_separates_built_in_rules_from_own(monkeypatch, window) -> None:
    """The main thing the window did not show: what belongs to whom.

    The categories used to go as a flat list, and «Rules of one's own» looked like
    the same kind of category as «Markup» — from the window there was no telling
    which rule's check cannot be rewritten.
    """
    rule_id = add_own_rule(monkeypatch, window)
    tree = window.rules_tab.tree
    assert group_titles(window) == ["Built-in rules", "Own rules"]

    base, own = tree.topLevelItem(0), tree.topLevelItem(1)
    assert rules_under(own) == {rule_id}
    assert rules_under(base) == {r.id for r in qa_rules.BUILTIN_RULES}


def test_language_group_names_the_language_of_the_project(window) -> None:
    """«Target language» tells nothing to somebody who is translating anyway."""
    titles = []
    base = window.rules_tab.tree.topLevelItem(0)
    for i in range(base.childCount()):
        titles.append(base.child(i).text(0))
    assert any("Target language ·" in t and "ru" in t for t in titles), titles


def test_rules_of_another_language_are_shown_apart_with_a_reason(
        qtbot, conn, project_file) -> None:
    """A rule of a foreign language stays quiet — unexplained that looks like a breakage."""
    from pdxloc.gui import rules_state as state

    state._locale = "fr"
    state._rebuild()
    try:
        win = RulesWindow(conn, project_file)
        qtbot.addWidget(win)
        win.rules_tab._debounce.stop()
        base = win.rules_tab.tree.topLevelItem(0)
        others = [base.child(i) for i in range(base.childCount())
                  if base.child(i).text(0) == "Other languages"]
        assert others, [base.child(i).text(0) for i in range(base.childCount())]
        assert rules_under(others[0]) == {"glued_markup", "linking_calque"}
        assert others[0].toolTip(0)
        win.rules_tab.shutdown()
    finally:
        state.open_project(conn)


def test_a_built_in_rule_says_it_cannot_be_rewritten(window) -> None:
    tab = window.rules_tab
    tab.tree.setCurrentItem(rule_item(window, "edge_space"))
    assert not tab.user_fields.isVisibleTo(tab)
    assert "Built-in rule" in tab.kind_label.text()
    assert not tab.delete_btn.isEnabled()
    assert not tab.duplicate_btn.isEnabled()
    # but the setting is available — the whole section was made for its sake
    assert tab.params._widgets["compare_with_source"].isEnabled()


def test_own_rule_appears_in_the_tree_and_is_selected(monkeypatch, window) -> None:
    rule_id = add_own_rule(monkeypatch, window)
    assert rule_id == "ellipsis"
    item = rule_item(window, rule_id)
    assert item is not None and item.text(0) == "Ellipsis"
    assert window.rules_tab.current_rule().id == rule_id


def test_own_rule_reaches_the_check_after_save(monkeypatch, window, conn) -> None:
    rule_id = add_own_rule(monkeypatch, window)
    window.rules_tab.params._widgets["chars"].setText("…")
    window.rules_tab._on_edited()
    window._save()

    assert rules_state.ruleset().check("Wait...", "Подожди…") == [rule_id]
    # and it is written whole and not as a delta: a rule of one's own has no base
    stored = project.get_qa_overlay(conn)["custom"]
    assert stored[0]["id"] == rule_id and stored[0]["params"]["chars"] == "…"


def test_own_rule_is_deleted_by_the_button(monkeypatch, window) -> None:
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import rules_window as rw

    rule_id = add_own_rule(monkeypatch, window)
    monkeypatch.setattr(rw.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    window.rules_tab._delete_user_rule()
    assert window.rules_tab._rules.get(rule_id) is None
    assert rule_item(window, rule_id) is None


def test_rule_names_do_not_collide(monkeypatch, window) -> None:
    """The name of a rule lives in files — in the overlay and next to the «not an error» mark."""
    first = add_own_rule(monkeypatch, window, title="Ellipsis")
    second = add_own_rule(monkeypatch, window, title="Ellipsis")
    assert first != second


def test_a_name_without_latin_letters_still_gives_a_usable_id(
        monkeypatch, window) -> None:
    rule_id = add_own_rule(monkeypatch, window, title="Троеточие")
    assert rule_id.isascii() and rule_id


def test_a_rule_from_the_global_layer_cannot_be_deleted_here(
        monkeypatch, window) -> None:
    """It is set for all the projects — inside a project it can only be switched off."""
    tab = window.rules_tab
    tab.scope_combo.setCurrentIndex(tab.scope_combo.findData(GLOBAL))
    rule_id = add_own_rule(monkeypatch, window)
    window._save()

    tab.scope_combo.setCurrentIndex(tab.scope_combo.findData(PROJECT))
    tab.tree.setCurrentItem(rule_item(window, rule_id))
    assert not tab.delete_btn.isEnabled()
    assert tab.delete_btn.toolTip()

    rule_item(window, rule_id).setCheckState(0, Qt.Unchecked)
    window._save()
    assert not rules_state.ruleset().get(rule_id).enabled
    # the rule itself went on living in the global layer
    assert "custom" not in project.get_qa_overlay(conn := window.conn)
    assert conn is not None


def test_a_broken_expression_is_shown_instead_of_being_swallowed(
        monkeypatch, window) -> None:
    add_own_rule(monkeypatch, window, title="Broken", kind="target_regex")
    window.rules_tab.params._widgets["pattern"].setText("([a-z")
    window.rules_tab._on_edited()
    assert not window.rules_tab.problem_label.isHidden()
    assert "pattern" in window.rules_tab.problem_label.text()


def test_own_rule_can_be_duplicated(monkeypatch, window) -> None:
    rule_id = add_own_rule(monkeypatch, window)
    tab = window.rules_tab
    tab.params._widgets["chars"].setText("…")
    tab._on_edited()

    tab._duplicate_user_rule()
    copy = tab.current_rule()
    assert copy.id != rule_id
    assert copy.params["chars"] == "…"          # the copy works the same way
    assert tab._rules.get(rule_id) is not None  # the original is in place


# --- returning to the defaults ------------------------------------------


def yes(monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import rules_window as rw

    monkeypatch.setattr(rw.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(rw.QMessageBox, "information",
                        staticmethod(lambda *a, **k: QMessageBox.Ok))


def test_a_hand_set_rule_is_marked_in_the_tree(window) -> None:
    """Otherwise «return to the set» strikes blind: what differs is not visible."""
    tab = window.rules_tab
    item = rule_item(window, "edge_space")
    tab.tree.setCurrentItem(item)       # the reset button applies to the selected one
    assert not item.font(0).bold()

    item.setCheckState(0, Qt.Unchecked)
    assert item.font(0).bold()
    assert item.toolTip(0)
    assert tab.reset_rule_btn.isEnabled()

    tab._reset_rule()
    assert not rule_item(window, "edge_space").font(0).bold()
    assert not tab.reset_rule_btn.isEnabled()


def test_returning_built_in_rules_keeps_own_ones(monkeypatch, window) -> None:
    """The former «Reset everything» deleted the rules of one's own as well — silently."""
    yes(monkeypatch)
    rule_id = add_own_rule(monkeypatch, window)
    tab = window.rules_tab
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)

    tab._reset_base()
    assert tab._rules.get("edge_space").enabled          # the built-in one came back
    assert tab._rules.get(rule_id) is not None           # one's own stayed


def test_deleting_own_rules_is_a_separate_action(monkeypatch, window) -> None:
    yes(monkeypatch)
    rule_id = add_own_rule(monkeypatch, window)
    tab = window.rules_tab
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)

    tab._delete_all_own()
    assert tab._rules.get(rule_id) is None
    assert not tab._rules.get("edge_space").enabled      # the setting is untouched


def test_changing_the_preset_does_not_take_own_rules_with_it(
        monkeypatch, window) -> None:
    """A preset is about the strictness of the built-in checks, of one's own it says nothing."""
    rule_id = add_own_rule(monkeypatch, window)
    tab = window.rules_tab
    tab.preset_combo.setCurrentIndex(tab.preset_combo.findData("quiet"))
    assert tab._rules.get(rule_id) is not None
    assert rule_item(window, rule_id) is not None


# --- exchanging the setting ---------------------------------------------


def test_settings_travel_through_a_file(monkeypatch, window, tmp_path, qtbot,
                                        conn, project_file) -> None:
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import rules_window as rw

    rule_id = add_own_rule(monkeypatch, window)
    window.rules_tab.params._widgets["chars"].setText("…")
    window.rules_tab._on_edited()
    rule_item(window, "edge_space").setCheckState(0, Qt.Unchecked)

    path = tmp_path / "team.pdxqa"
    monkeypatch.setattr(rw.QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(path), "")))
    monkeypatch.setattr(rw.QMessageBox, "information",
                        staticmethod(lambda *a, **k: QMessageBox.Ok))
    window.rules_tab._export()
    assert path.is_file()

    other = RulesWindow(conn, project_file)
    qtbot.addWidget(other)
    other.rules_tab._debounce.stop()
    try:
        monkeypatch.setattr(rw.QFileDialog, "getOpenFileName",
                            staticmethod(lambda *a, **k: (str(path), "")))
        monkeypatch.setattr(rw.QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Yes))
        other.rules_tab._import()
        assert other.rules_tab._rules.get(rule_id).params["chars"] == "…"
        assert not other.rules_tab._rules.get("edge_space").enabled
    finally:
        other.rules_tab.shutdown()


def test_import_asks_before_replacing(monkeypatch, window, tmp_path) -> None:
    """An arrived set replaces the layer whole — doing that silently will not do."""
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.core import qa_exchange, qa_rules as rules_module
    from pdxloc.gui import rules_window as rw

    path = qa_exchange.write(tmp_path / "s.pdxqa", "quiet",
                             rules_module.resolve({"preset": "quiet"}))
    monkeypatch.setattr(rw.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(path), "")))
    monkeypatch.setattr(rw.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    window.rules_tab._import()
    assert window.rules_tab._preset[PROJECT] != "quiet"


def test_an_unreadable_file_does_not_change_anything(
        monkeypatch, window, tmp_path) -> None:
    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import rules_window as rw

    path = tmp_path / "broken.pdxqa"
    path.write_text("{не json", encoding="utf-8")
    monkeypatch.setattr(rw.QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(path), "")))
    said: list[str] = []
    monkeypatch.setattr(rw.QMessageBox, "critical",
                        staticmethod(lambda *a, **k: said.append(a[-1])
                                     or QMessageBox.Ok))
    before = [r.id for r in window.rules_tab._rules]
    window.rules_tab._import()
    assert [r.id for r in window.rules_tab._rules] == before
    assert said


# --- the «not an error» tab ---------------------------------------------


def test_the_empty_tab_explains_what_it_is_for(window) -> None:
    """An empty list raised a question out loud — so it was not answering it."""
    tab = window.ignores_tab
    assert not tab.list.isVisibleTo(tab)
    assert not tab.empty_label.isHidden()
    assert "F6" in tab.empty_label.text()


def test_the_explanation_gives_way_to_the_list(window, conn) -> None:
    from pdxloc.core import qa

    unit_id = conn.execute("SELECT id FROM units LIMIT 1").fetchone()["id"]
    qa.ignore_issue(conn, unit_id, "edge_space")
    window.ignores_tab.reload()
    assert window.ignores_tab.empty_label.isHidden()
    assert not window.ignores_tab.list.isHidden()


def test_ignored_issue_can_be_returned_to_the_check(window, conn) -> None:
    from pdxloc.core import qa

    unit_id = conn.execute("SELECT id FROM units LIMIT 1").fetchone()["id"]
    qa.ignore_issue(conn, unit_id, "edge_space")
    window.ignores_tab.reload()
    assert window.ignores_tab.list.count() == 1

    window.ignores_tab.list.selectAll()
    window.ignores_tab._return_selected()
    assert window.ignores_tab.list.count() == 0
    assert qa.ignored_pairs(conn) == set()


# --- the window without a project ---------------------------------------


def test_a_long_list_gets_a_multi_line_field(qtbot) -> None:
    """Lists of declining functions happen to run to a hundred names and more.

    Such a thing does not fit into a line with commas, and editing it there is
    dangerous: one comma knocked out glues two names together, and both stop
    working silently.
    """
    from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

    from pdxloc.gui.rules_param_editors import ParamEditors

    editors = ParamEditors()
    qtbot.addWidget(editors)
    rule = qa_rules.BY_ID["brackets_mismatch"]

    short = rule.with_params(ignore_extra_tails=["GetOne", "GetTwo"])
    editors.set_rule(short)
    assert isinstance(editors._widgets["ignore_extra_tails"], QLineEdit)

    names = [f"GetName{i}" for i in range(60)]
    editors.set_rule(rule.with_params(ignore_extra_tails=names))
    field = editors._widgets["ignore_extra_tails"]
    assert isinstance(field, QPlainTextEdit)
    assert field.toPlainText().splitlines() == names
    # it reads back without loss, and a list pasted with commas does too
    assert editors.values(rule)["ignore_extra_tails"] == names
    field.setPlainText("GetA, GetB\nGetC")
    assert editors.values(rule)["ignore_extra_tails"] == ["GetA", "GetB", "GetC"]


def _hoi4_project(tmp_path, make_tree):
    """A project of another game: its recommended set is not the one CK3 has."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "hoi4.pdxproj"
    conn = project.create_project(path, name="H", game="hoi4",
                                  src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    conn.close()
    return path


def test_the_recommended_preset_leads_the_list(qtbot, tmp_path, make_tree) -> None:
    """The shop window is obliged to show which of the four game sets is yours.

    Before 0.1.2 «(recommended)» was written right into the `ck3_ru` label, that
    is, stood by everyone at once: the HOI4 translator read advice about somebody
    else's set, while their own — taken off their own vanilla translation — they
    saw with no mark at all. Since 0.1.2 a set is called by the game, and the
    recommended one is the one whose name matched the game of the project.
    """
    path = _hoi4_project(tmp_path, make_tree)
    conn = project.open_project(path, [])
    rules_state.open_project(conn)
    try:
        win = RulesWindow(conn, path)
        qtbot.addWidget(win)
        win.rules_tab._debounce.stop()
        combo = win.rules_tab.preset_combo

        assert combo.itemData(0) == "hoi4"
        assert "recommended for this project" in combo.itemText(0)
        assert combo.itemData(1) is None                  # the separator
        others = [combo.itemText(i) for i in range(2, combo.count())]
        assert others and not any("recommended" in text for text in others)
        # not a single set was lost or doubled
        chosen = [combo.itemData(i) for i in range(combo.count())
                  if combo.itemData(i)]
        assert sorted(chosen) == sorted(qa_rules.PRESET_ORDER)
        win.rules_tab.shutdown()
    finally:
        rules_state.close_project()
        conn.close()


def test_the_menu_marks_the_recommended_preset_and_lets_it_go(
        qtbot, monkeypatch, tmp_path, make_tree) -> None:
    """The mark comes with a project and leaves together with it.

    The menu lives the whole session, so the items are not recreated but moved
    about; otherwise the radio group would pile them up at every change of
    project.
    """
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")

    from pdxloc.gui.main_window import MainWindow

    path = _hoi4_project(tmp_path, make_tree)
    win = MainWindow()
    qtbot.addWidget(win)

    def shown():
        """The presets in the order they stand in the menu."""
        name_of = {action: name for name, action in win.qa_preset_actions.items()}
        return [name_of[a] for a in win._qa_preset_menu.actions()
                if not a.isSeparator()]

    before = shown()
    assert not any("recommended" in a.text()
                   for a in win._qa_preset_menu.actions())

    win.open_project(path)
    labels = {a.text() for a in win._qa_preset_menu.actions()}
    assert any("recommended for this project" in text for text in labels)
    assert win.qa_preset_actions["hoi4"].text().startswith("Hearts of Iron IV")
    assert shown()[0] == "hoi4"

    win.show_start()
    assert shown() == before          # exactly as many items, and the order is the same
    assert not any("recommended" in a.text()
                   for a in win._qa_preset_menu.actions())


def test_preset_from_the_menu_changes_the_issues_column(
        qtbot, monkeypatch, tmp_path, project_file) -> None:
    """An end-to-end check: the menu → the rule set → the «!» column of the table.

    That is what the whole thing was started for: the model used to count the
    remarks with the built-in values and did not see the setting at all.
    """
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")

    from pdxloc.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.open_project(project_file)
    model = win.editor_screen.model
    unit_id = win.conn.execute("SELECT id FROM units WHERE key = 'a'").fetchone()["id"]
    assert "edge_space" in model.issues_of(unit_id)

    win._set_qa_preset("quiet")
    assert "edge_space" not in model.issues_of(unit_id)
    assert win.qa_preset_actions["quiet"].isChecked()


def test_window_opens_without_a_project(qtbot) -> None:
    """The rule set is global — forbidding its setup until a mod is open would be
    odd, and the counter of hits simply keeps quiet."""
    win = RulesWindow(None, None)
    qtbot.addWidget(win)
    try:
        assert not win.rules_tab.scope_combo.isEnabled()
        assert win.rules_tab.scope == GLOBAL
        assert "project" in win.rules_tab.status_text()
    finally:
        win.rules_tab.shutdown()
