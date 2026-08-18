"""Папка игры и язык текста — разные вещи.

Одно поле «язык перевода» делало две работы. Для CK3+русского они совпадали и
не жали; расходятся ровно там, где переводят на язык, которого в игре нет:
португальский в CK3 лежит в файлах `l_english`. Без разделения такой перевод
в проекте не выразить.

Правило хранения: локаль, совпадающая с выведенной из папки, **не хранится**.
Так проект не зарастает значениями, которые и так известны, а смена папки сама
тянет за собой язык текста.
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


# --- схема ---------------------------------------------------------------


def test_schema_version_is_pinned() -> None:
    """Число здесь затем, чтобы схему нельзя было изменить не заметив.

    Поменял — напиши миграцию и её тест, а потом уже правь эту строку.
    """
    assert db.SCHEMA_VERSION == 9


def test_migration_adds_locale_columns_without_touching_rows(tmp_path, make_tree) -> None:
    """Миграция 4→5 только дописывает колонки: строки не пересобираются."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "old.pdxproj"
    c = project.create_project(path, name="Old", src_root=en, tgt_root=ru)
    scan_project(c, 1)
    before = c.execute("SELECT COUNT(*) FROM units").fetchone()[0]

    # откатываем проект к состоянию v4: колонок нет, версия прежняя
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
        # значения пустые: «совпадает с папкой языка»
        row = again.execute(
            "SELECT src_locale, tgt_locale FROM projects WHERE id = 1").fetchone()
        assert row["src_locale"] == "" and row["tgt_locale"] == ""
    finally:
        again.close()


# --- выведение локали ----------------------------------------------------


def test_empty_locale_is_derived_from_the_game_folder(conn) -> None:
    langs = project.languages(conn)
    assert (langs.src_lang, langs.tgt_lang) == ("english", "russian")
    assert (langs.src_locale, langs.tgt_locale) == ("en", "ru")
    assert not langs.split


def test_unknown_folder_gives_no_locale() -> None:
    """Мод завёл своё имя папки — угадывать по нему нечего."""
    assert languages.default_locale("средиземноморский") == ""
    assert languages.resolve_locale("средиземноморский", "") == ""
    assert languages.resolve_locale("средиземноморский", "it") == "it"


def test_translation_into_a_language_the_game_does_not_know(conn) -> None:
    """Португальский в CK3 живёт в файлах l_english — ради этого и разделяли."""
    project.set_languages(conn, project.ProjectLanguages(
        src_lang="english", tgt_lang="english",
        src_locale="en", tgt_locale="pt"))
    langs = project.languages(conn)
    assert langs.tgt_lang == "english"      # файлы по-прежнему l_english
    assert langs.tgt_locale == "pt"         # а текст португальский
    assert langs.split


def test_matching_locale_is_not_stored(conn) -> None:
    """Иначе смена папки языка не тянула бы за собой язык текста."""
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


# --- предпросмотр смены языка -------------------------------------------


def test_changing_only_the_text_language_does_not_need_a_scan(conn) -> None:
    preview = relocate.preview_language_change(conn, 1, "english", "russian")
    assert not preview.scan_needed and not preview.risky
    assert "not affected" in preview.summary()


def test_changing_the_folder_language_warns_about_lost_rows(conn) -> None:
    """Сканер ищет файлы по метке _l_<язык>; смена языка их «теряет»."""
    preview = relocate.preview_language_change(conn, 1, "french", "russian")
    assert preview.scan_needed and preview.risky
    assert preview.found == 0
    assert preview.units_missing == 2        # обе строки проекта
    assert "Not a single file was found" in preview.summary()


def test_keeping_the_folder_language_finds_every_file(conn) -> None:
    preview = relocate.preview_language_change(conn, 1, "english", "french")
    assert preview.scan_needed and not preview.risky
    assert preview.found == preview.known_files == 1


# --- языковые правила проверки ------------------------------------------


RU_ONLY = ("glued_markup", "linking_calque")


def test_russian_rules_are_off_for_other_languages() -> None:
    """Француз не должен получать замечания про русское склонение."""
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
    """Язык неизвестен — молчать наугад хуже, чем показать лишнее."""
    rules = qa_rules.resolve(locale="")
    for code in RU_ONLY:
        assert rules.get(code).enabled


def test_the_translator_can_switch_a_foreign_rule_back_on() -> None:
    """Правило написано под русский, но переводчику виднее.

    Поэтому язык — часть основания набора, а не последний штрих: иначе он
    затирал бы осознанный выбор.
    """
    rules = qa_rules.resolve(
        {"rules": {"glued_markup": {"enabled": True}}}, locale="fr")
    assert rules.get("glued_markup").enabled


def test_rules_of_a_foreign_language_stay_visible() -> None:
    """Выключенное правило видно в окне настройки; выброшенное — пропало бы."""
    french = qa_rules.resolve(locale="fr")
    assert len(french) == len(qa_rules.BUILTIN_RULES)
    assert french.get("linking_calque") is not None


# --- окно ----------------------------------------------------------------


def test_dialog_hides_text_languages_until_asked(conn, qtbot) -> None:
    """Поле, которое нечем заполнить, только путает."""
    from pdxloc.gui.languages_dialog import LanguagesDialog

    dlg = LanguagesDialog(conn)
    qtbot.addWidget(dlg)
    assert not dlg.split.isChecked()
    assert not dlg.locales.isVisibleTo(dlg)

    dlg.split.setChecked(True)
    assert dlg.locales.isVisibleTo(dlg)
    # подставлено то, что и так подразумевается папками
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
