"""A project without a translation folder, and changing that folder later.

A mod that is English only has no translation tree at all, and until 0.1.2 the
window creating a project demanded one anyway: the field was obligatory, filled
in with a guess, and after that unchangeable — `ru_root` was written once and by
nothing else. A guess that missed cost the project every translation on disk
silently, because the scan only ever asks whether the folder is there.

Two things are pinned down here: an unset folder is a lawful state that no part
of the application may read as «the current directory», and a folder chosen for
an existing project is checked before it is written.
"""
from __future__ import annotations

import pytest

from pdxloc import project
from pdxloc.core import relocate
from pdxloc.core.exporter import ExportOptions, export_project
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

from test_scanner import get_unit, make_project

EN = 'l_english:\n greet:0 "Winter is coming"\n bye:0 "Farewell"\n'
RU = 'l_russian:\n greet:0 "Зима близко"\n'


# --- the folder is not chosen --------------------------------------------


def test_an_unset_folder_is_not_the_current_directory(db, make_tree, monkeypatch,
                                                      tmp_path):
    """`Path("")` is «here», and a scan would take the working directory for a tree.

    The failure is quiet and expensive: the scan walks whatever the application
    happens to be started from and calls it the translation.
    """
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")
    monkeypatch.chdir(make_tree({"m_l_russian.yml": RU}, "cwd_with_translation"))

    stats = scan_project(db, pid)

    assert stats.files_ru == 0
    assert get_unit(db, "greet")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "greet")["ru_text"] is None


def test_a_project_without_a_folder_scans_and_translates(db, make_tree):
    """The ordinary path for a mod nobody has translated: every row is simply new."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")

    stats = scan_project(db, pid)

    assert (stats.new, stats.files_ru) == (2, 0)
    assert project.translation_root(db, pid) is None


def test_writing_without_a_folder_refuses_instead_of_guessing(db, make_tree):
    """Writing to wherever the application runs would scatter the mod over the disk."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")
    scan_project(db, pid)

    with pytest.raises(ValueError):
        export_project(db, pid, ExportOptions(mode="all_fallback_en"))


def test_an_explicit_folder_still_writes(db, make_tree, tmp_path):
    """Nothing is lost by having no folder: the write only needs one to be named."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")
    scan_project(db, pid)
    out = tmp_path / "mod" / "localization"

    report = export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)

    assert report.files_written == 1
    assert (out / "m_l_russian.yml").is_file()


# --- proposing a folder for a chosen original ----------------------------


def test_a_language_folder_gets_its_sibling(tmp_path):
    """The canonical layout: …\\localization\\english and …\\localization\\russian."""
    src = tmp_path / "mod" / "localization" / "english"
    src.mkdir(parents=True)

    assert relocate.suggest_target_root(src) == src.parent / "russian"


def test_a_localization_root_keeps_the_same_root(tmp_path):
    """The original and the translation in one mod: the root is the same folder.

    The sibling guess used to answer …\\mod\\russian here — outside the mod, where
    the game reads nothing and the scan finds no pairs.
    """
    src = tmp_path / "mod" / "localization"
    (src / "english").mkdir(parents=True)

    assert relocate.suggest_target_root(src) == src


def test_the_folder_holding_the_translation_wins(tmp_path, make_tree):
    """Where a translation is already on disk, the disk answers, not the path."""
    root = tmp_path / "mod" / "localization"
    (root / "english").mkdir(parents=True)
    (root / "english" / "m_l_english.yml").write_text(EN, encoding="utf-8-sig")
    (root / "russian").mkdir()
    (root / "russian" / "m_l_russian.yml").write_text(RU, encoding="utf-8-sig")

    assert relocate.suggest_target_root(root) == root
    assert relocate.suggest_target_root(root / "english") == root / "russian"


def test_a_neighbour_with_a_name_of_its_own_is_found(tmp_path):
    """Folders named `en` and `ru` carry no language in the path — only pairs tell."""
    src = tmp_path / "en"
    (src / "agot").mkdir(parents=True)
    (src / "agot" / "m_l_english.yml").write_text(EN, encoding="utf-8-sig")
    tgt = tmp_path / "ru"
    (tgt / "agot").mkdir(parents=True)
    (tgt / "agot" / "m_l_russian.yml").write_text(RU, encoding="utf-8-sig")

    assert relocate.suggest_target_root(src) == tgt


def test_a_folder_that_is_not_there_yet_still_gets_a_path(tmp_path):
    """A new project has nothing to measure — the answer is a proposal, not a find."""
    src = tmp_path / "mod" / "localization" / "english"

    assert relocate.suggest_target_root(src) == src.parent / "russian"


# --- changing the folder of an existing project --------------------------


def test_preview_counts_the_translation_files_there(db, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, "")
    scan_project(db, pid)

    preview = relocate.preview_target_change(db, pid, ru)

    assert preview.usable and preview.exists
    assert (preview.paired, preview.known_files) == (1, 1)


def test_an_empty_folder_is_not_an_error(db, make_tree, tmp_path):
    """Unlike the original folder: emptiness here is what the write is for."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")
    scan_project(db, pid)
    fresh = tmp_path / "mod" / "localization" / "russian"
    fresh.mkdir(parents=True)

    preview = relocate.preview_target_change(db, pid, fresh)

    assert preview.usable and preview.paired == 0


def test_a_folder_that_does_not_exist_is_announced(db, make_tree, tmp_path):
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")

    preview = relocate.preview_target_change(db, pid, tmp_path / "not-there")

    assert preview.usable and not preview.exists
    assert "does not exist" in preview.summary()


def test_a_file_instead_of_a_folder_is_refused(db, make_tree, tmp_path):
    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, "")
    a_file = tmp_path / "notes.txt"
    a_file.write_text("x", encoding="utf-8")

    preview = relocate.preview_target_change(db, pid, a_file)

    assert not preview.usable


def test_an_empty_path_clears_the_folder(db, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)

    preview = relocate.preview_target_change(db, pid, "")
    assert preview.usable and preview.cleared

    relocate.set_ru_root(db, pid, None)
    assert relocate.get_ru_root(db, pid) is None


def test_the_new_folder_is_read_by_the_next_scan(db, make_tree):
    """The point of the whole window: a mistake made once is no longer for life."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    wrong = make_tree({}, "wrong")
    right = make_tree({"m_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, wrong)
    scan_project(db, pid)
    assert get_unit(db, "greet")["ru_text"] is None

    relocate.set_ru_root(db, pid, right)
    scan_project(db, pid)

    assert get_unit(db, "greet")["ru_text"] == "Зима близко"
