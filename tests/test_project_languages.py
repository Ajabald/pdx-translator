"""The game folder and the language of the text are different things.

One field, «the target language», did two jobs. For CK3 plus Russian they
coincided and did not pinch; they diverge exactly where the translation goes into
a language the game does not have: Portuguese in CK3 lies in `l_english` files.
Without the split such a translation cannot be expressed in a project.

The rule of storage: a locale that coincides with the one derived from the folder
is **not stored**. That way the project does not grow over with values that are
known anyway, and a change of the folder drags the language of the text with it.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc import db, project  # noqa: E402
from pdxloc.core import languages, qa, qa_rules, relocate  # noqa: E402
from pdxloc.core.scanner import scan_project  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def conn(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    c = project.create_project(tmp_path / "p.pdxproj", name="P",
                               src_root=en, tgt_root=ru)
    scan_project(c, 1)
    yield c
    c.close()


# --- the schema ---------------------------------------------------------


def test_schema_version_is_pinned() -> None:
    """The number is here so that the schema cannot be changed unnoticed.

    Changed it — write a migration and a test for it, and only then edit this line.
    """
    assert db.SCHEMA_VERSION == 10


def test_migration_adds_locale_columns_without_touching_rows(tmp_path, make_tree) -> None:
    """The 4→5 migration only adds columns: the rows are not rebuilt."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "old.pdxproj"
    c = project.create_project(path, name="Old", src_root=en, tgt_root=ru)
    scan_project(c, 1)
    before = c.execute("SELECT COUNT(*) FROM units").fetchone()[0]

    # we roll the project back to the v4 state: no columns, the former version
    c.execute("ALTER TABLE projects DROP COLUMN src_locale")
    c.execute("ALTER TABLE projects DROP COLUMN tgt_locale")
    c.execute("UPDATE schema_meta SET value = '4' WHERE key = 'schema_version'")
    c.commit()
    c.close()

    again = project.open_project(path, [])
    try:
        cols = {r[1] for r in again.execute("PRAGMA table_info(projects)")}
        assert {"src_locale", "tgt_locale"} <= cols
        assert again.execute("SELECT COUNT(*) FROM units").fetchone()[0] == before
        # the values are empty: «the same as the language folder»
        row = again.execute(
            "SELECT src_locale, tgt_locale FROM projects WHERE id = 1").fetchone()
        assert row["src_locale"] == "" and row["tgt_locale"] == ""
    finally:
        again.close()


# --- deriving the locale ------------------------------------------------


def test_empty_locale_is_derived_from_the_game_folder(conn) -> None:
    langs = project.languages(conn)
    assert (langs.src_lang, langs.tgt_lang) == ("english", "russian")
    assert (langs.src_locale, langs.tgt_locale) == ("en", "ru")
    assert not langs.split


def test_unknown_folder_gives_no_locale() -> None:
    """A mod has set up a folder name of its own — there is nothing to guess by it."""
    assert languages.default_locale("средиземноморский") == ""
    assert languages.resolve_locale("средиземноморский", "") == ""
    assert languages.resolve_locale("средиземноморский", "it") == "it"


def test_translation_into_a_language_the_game_does_not_know(conn) -> None:
    """Portuguese in CK3 lives in l_english files — that is what the split was for."""
    project.set_languages(conn, project.ProjectLanguages(
        src_lang="english", tgt_lang="english",
        src_locale="en", tgt_locale="pt"))
    langs = project.languages(conn)
    assert langs.tgt_lang == "english"      # the files are still l_english
    assert langs.tgt_locale == "pt"         # while the text is Portuguese
    assert langs.split


def test_matching_locale_is_not_stored(conn) -> None:
    """Otherwise a change of the language folder would not drag the language of the text with it."""
    project.set_languages(conn, project.ProjectLanguages(
        src_lang="english", tgt_lang="russian",
        src_locale="en", tgt_locale="ru"))
    row = conn.execute(
        "SELECT src_locale, tgt_locale FROM projects WHERE id = 1").fetchone()
    assert row["src_locale"] == "" and row["tgt_locale"] == ""

    project.set_languages(conn, project.ProjectLanguages(
        src_lang="english", tgt_lang="french",
        src_locale="en", tgt_locale="fr"))
    assert project.languages(conn).tgt_locale == "fr"


# --- the preview of a language change -----------------------------------


def test_changing_only_the_text_language_does_not_need_a_scan(conn) -> None:
    preview = relocate.preview_language_change(conn, 1, "english", "russian")
    assert not preview.scan_needed and not preview.risky
    assert "not affected" in preview.summary()


def test_changing_the_folder_language_warns_about_lost_rows(conn) -> None:
    """The scanner looks for files by the _l_<language> mark; a change of language «loses» them."""
    preview = relocate.preview_language_change(conn, 1, "french", "russian")
    assert preview.scan_needed and preview.risky
    assert preview.found == 0
    assert preview.units_missing == 2        # both rows of the project
    assert "Not a single file was found" in preview.summary()


def test_keeping_the_folder_language_finds_every_file(conn) -> None:
    preview = relocate.preview_language_change(conn, 1, "english", "french")
    assert preview.scan_needed and not preview.risky
    assert preview.found == preview.known_files == 1


# --- the language check rules -------------------------------------------


RU_ONLY = ("glued_markup", "linking_calque")


def test_russian_rules_are_off_for_other_languages() -> None:
    """A translator into French must not get remarks about Russian declension."""
    for code in RU_ONLY:
        assert qa_rules.BY_ID[code].locale == "ru"

    french = qa_rules.resolve(locale="fr")
    for code in RU_ONLY:
        assert not french.get(code).enabled

    russian = qa_rules.resolve(locale="ru")
    for code in RU_ONLY:
        assert russian.get(code).enabled


def test_russian_rule_stays_silent_on_a_french_project() -> None:
    en, ru = "House [GetPlayer.GetDynasty.GetName]", "дома[GetPlayer.GetDynasty.GetName]"
    assert "glued_markup" in qa.check_unit(en, ru)
    french = qa_rules.resolve(locale="fr")
    assert "glued_markup" not in qa.check_unit(en, ru, ruleset=french)


def test_unknown_locale_silences_nothing() -> None:
    """The language is unknown — being silent at random is worse than showing too much."""
    rules = qa_rules.resolve(locale="")
    for code in RU_ONLY:
        assert rules.get(code).enabled


def test_the_translator_can_switch_a_foreign_rule_back_on() -> None:
    """The rule is written for Russian, but the translator knows better.

    That is why the language is part of the base of the set and not the last
    touch: otherwise it would wipe out a deliberate choice.
    """
    rules = qa_rules.resolve(
        {"rules": {"glued_markup": {"enabled": True}}}, locale="fr")
    assert rules.get("glued_markup").enabled


def test_rules_of_a_foreign_language_stay_visible() -> None:
    """A switched-off rule shows in the setup window; a thrown-out one would be gone."""
    french = qa_rules.resolve(locale="fr")
    assert len(french) == len(qa_rules.BUILTIN_RULES)
    assert french.get("linking_calque") is not None


# --- the window ---------------------------------------------------------


def test_dialog_hides_text_languages_until_asked(conn, qtbot) -> None:
    """A field that there is nothing to fill in with only confuses."""
    from pdxloc.gui.languages_dialog import LanguagesDialog

    dlg = LanguagesDialog(conn)
    qtbot.addWidget(dlg)
    assert not dlg.split.isChecked()
    assert not dlg.locales.isVisibleTo(dlg)

    dlg.split.setChecked(True)
    assert dlg.locales.isVisibleTo(dlg)
    # what the folders imply anyway is filled in
    assert dlg.src_locale.currentText() == "en"
    assert dlg.tgt_locale.currentText() == "ru"


def test_dialog_warns_before_losing_files(conn, qtbot) -> None:
    from pdxloc.gui.languages_dialog import LanguagesDialog

    dlg = LanguagesDialog(conn)
    qtbot.addWidget(dlg)
    dlg.src_lang.setCurrentText("french")
    assert dlg.preview is not None and dlg.preview.risky
    assert "Not a single file was found" in dlg.report_box.toPlainText()


def test_dialog_saves_and_reports_whether_a_scan_is_needed(conn, qtbot) -> None:
    from pdxloc.gui.languages_dialog import LanguagesDialog

    dlg = LanguagesDialog(conn)
    qtbot.addWidget(dlg)
    seen: list[bool] = []
    dlg.languagesChanged.connect(seen.append)

    dlg.split.setChecked(True)
    dlg.tgt_locale.setCurrentText("pt")
    dlg._apply()

    assert project.languages(conn).tgt_locale == "pt"
    assert seen == [False], "менялся только язык текста — скан не нужен"
