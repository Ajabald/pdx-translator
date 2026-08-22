"""The «New project» window: prefilling the paths and creating a project."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

from pdxloc import project, settings  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n'


@pytest.fixture
def dialog(tmp_path, monkeypatch, qtbot):
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "last_browse_dir", lambda: "")
    monkeypatch.setattr(settings, "set_last_browse_dir", lambda p: None)

    from pdxloc.gui.start_screen import ProjectDialog

    dlg = ProjectDialog()
    qtbot.addWidget(dlg)
    return dlg


def test_project_file_defaults_to_the_pen_of_its_game(dialog, tmp_path):
    """The file lands in the pen of the chosen game, but the path is visible and editable."""
    assert str(tmp_path / "Projects") in dialog.file_edit.placeholderText()

    dialog.name_edit.setText("Мой мод")

    assert dialog.file_edit.text() == str(
        tmp_path / "Projects" / "CK3" / "Мой мод.pdxproj")


def test_choosing_a_game_moves_the_suggestion_to_its_pen(dialog, tmp_path):
    dialog.name_edit.setText("Мой мод")
    dialog.game_combo.setCurrentText("Stellaris")
    assert dialog.game_id() == "stellaris"
    assert dialog.file_edit.text() == str(
        tmp_path / "Projects" / "Stellaris" / "Мой мод.pdxproj")


def test_a_game_of_your_own_gets_a_pen_too(dialog, tmp_path):
    """The format is common — there is nothing to forbid CK2 or Victoria 2 for."""
    dialog.name_edit.setText("Мой мод")
    dialog.game_combo.setCurrentText("Victoria 2")
    assert dialog.game_id() == "victoria_2"
    assert dialog.file_edit.text() == str(
        tmp_path / "Projects" / "victoria_2" / "Мой мод.pdxproj")


def test_the_game_decides_which_language_folders_are_offered(dialog):
    dialog.game_combo.setCurrentText("Europa Universalis IV")
    offered = [dialog.tgt_lang.itemText(i) for i in range(dialog.tgt_lang.count())]
    assert "russian" not in offered      # EU4 really does not have it
    dialog.game_combo.setCurrentText("Crusader Kings III")
    offered = [dialog.tgt_lang.itemText(i) for i in range(dialog.tgt_lang.count())]
    assert "russian" in offered


def test_name_with_forbidden_characters(dialog, tmp_path):
    dialog.name_edit.setText("Bloodlines: Legacies/AGOT")
    assert dialog.file_edit.text() == str(
        tmp_path / "Projects" / "CK3" / "Bloodlines_ Legacies_AGOT.pdxproj")


def test_bare_file_name_goes_to_the_pen(dialog, tmp_path):
    """Just a name was entered — the file still has to land in the pen of its game."""
    dialog.name_edit.setText("Мод")
    dialog.file_edit.setText("другое-имя")

    assert dialog.values()["path"] == (
        tmp_path / "Projects" / "CK3" / "другое-имя.pdxproj")


def test_target_folder_suggested_from_source(dialog, tmp_path):
    """…\\localization\\english was given — the translation folder is offered by itself."""
    src = tmp_path / "mod" / "localization" / "english"
    dialog.src_edit.setText(str(src))
    dialog._suggest_target()

    assert dialog.tgt_edit.text() == str(tmp_path / "mod" / "localization" / "russian")


def test_target_suggestion_follows_language(dialog, tmp_path):
    dialog.tgt_lang.setCurrentText("french")
    dialog.src_edit.setText(str(tmp_path / "loc" / "english"))
    dialog._suggest_target()

    assert dialog.tgt_edit.text().endswith("french")


def test_placeholders_follow_the_chosen_languages(dialog):
    """The grey hint in the field is the same advice as the text below, only shorter.

    While it stood at english→russian, the dialog contradicted itself: below it
    spoke of polish, while in the field russian was offered.
    """
    assert dialog.tgt_edit.placeholderText().endswith("russian")

    dialog.src_lang.setCurrentText("french")
    dialog.tgt_lang.setCurrentText("polish")

    assert dialog.src_edit.placeholderText().endswith("french")
    assert dialog.tgt_edit.placeholderText().endswith("polish")
    assert "l_french" in dialog.hint.text()      # and the original too, not only the translation
    assert "l_polish" in dialog.hint.text()


def test_target_not_overwritten(dialog, tmp_path):
    dialog.tgt_edit.setText(str(tmp_path / "своя папка"))
    dialog.src_edit.setText(str(tmp_path / "loc" / "english"))
    dialog._suggest_target()

    assert dialog.tgt_edit.text() == str(tmp_path / "своя папка")


def test_a_mod_with_both_languages_keeps_the_same_root(dialog, tmp_path):
    """The root is …\\mod\\localization, and the translation lives in that same root.

    The sibling guess answered …\\mod\\russian — outside the mod. The project then
    found no translation at all and offered to write the mod past itself.
    """
    root = tmp_path / "mod" / "localization"
    (root / "english").mkdir(parents=True)
    dialog.src_edit.setText(str(root))
    dialog._suggest_target()

    assert dialog.tgt_edit.text() == str(root)


def test_the_translation_folder_may_be_left_empty(dialog, tmp_path, make_tree):
    """A mod that is English only has no such folder — demanding one invents a path."""
    src = make_tree({"m_l_english.yml": EN}, "en")
    dialog.name_edit.setText("Только английский")
    dialog.src_edit.setText(str(src))
    dialog.tgt_edit.setText("")

    dialog._validate()      # the window used to refuse here

    assert dialog.result() == QDialog.Accepted
    assert dialog.values()["tgt_root"] == ""


def test_an_empty_folder_creates_a_working_project(dialog, tmp_path, make_tree):
    """The whole point: translating a mod nobody has translated yet."""
    from pdxloc.core.scanner import scan_project

    src = make_tree({"m_l_english.yml": EN}, "en")
    dialog.name_edit.setText("Без перевода")
    dialog.src_edit.setText(str(src))
    dialog.tgt_edit.setText("")
    values = dialog.values()

    conn = project.create_project(
        values["path"], name=values["name"], src_root=values["src_root"],
        tgt_root=values["tgt_root"])
    try:
        assert scan_project(conn, 1).new == 1
        assert project.translation_root(conn) is None
    finally:
        conn.close()


def test_browse_buttons_are_labelled(dialog):
    """The explorer buttons are labelled, as in the other windows, and not a narrow «…»."""
    from PySide6.QtWidgets import QToolButton

    labels = {b.text() for b in dialog.findChildren(QToolButton)}
    assert labels == {"Browse…"}


def test_creates_working_project(dialog, tmp_path, make_tree):
    """An end-to-end check: the window was filled in — a working project file came out."""
    from pdxloc.core.scanner import scan_project

    src = make_tree({"m_l_english.yml": EN}, "en")
    dialog.name_edit.setText("Проверка")
    dialog.src_edit.setText(str(src))
    dialog._suggest_target()
    values = dialog.values()

    conn = project.create_project(
        values["path"], name=values["name"], src_root=values["src_root"],
        tgt_root=values["tgt_root"], src_lang=values["src_lang"],
        tgt_lang=values["tgt_lang"])
    try:
        stats = scan_project(conn, 1)
        assert stats.new == 1
        assert project.project_name(conn) == "Проверка"
        row = conn.execute("SELECT src_lang, tgt_lang FROM projects").fetchone()
        assert (row["src_lang"], row["tgt_lang"]) == ("english", "russian")
    finally:
        conn.close()
    assert values["path"].is_file()
    assert values["path"].parent == tmp_path / "Projects" / "CK3"
