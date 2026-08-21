"""Building a database out of a translation mod: it lies as a separate mod with a tree of its own.

A live case: the AGOT Russian pack (mod 2962803371) keeps two folders next to each
other — `localization/russian` with the translation of the mod itself and
`localization/replace/russian` with the replacement of the vanilla rows. The user
pointed at their common root, and the application answered «not one of the 417
files of the original has a pair», while the paired folder lay one level down.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from pdxloc.core import tm_import  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'
RU_VANILLA = 'l_russian:\n vanilla_key:0 "Ванильная строка"\n'


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)


@pytest.fixture
def mods(tmp_path):
    """Two workshop mods: the mod itself and a separate Russian pack."""
    mod = tmp_path / "2962333032"
    _write(mod / "localization" / "english" / "agot" / "mod_l_english.yml", EN)

    ru = tmp_path / "2962803371"
    _write(ru / "localization" / "russian" / "agot" / "mod_l_russian.yml", RU)
    _write(ru / "localization" / "replace" / "russian" / "vanilla_l_russian.yml", RU_VANILLA)
    return mod, ru


def test_language_dirs_finds_both_trees(mods):
    _, ru = mods
    found = tm_import.language_dirs(ru, "russian")
    assert set(found) == {ru / "localization" / "russian",
                          ru / "localization" / "replace" / "russian"}


def test_resolve_picks_tree_that_pairs(mods):
    """Of the two language folders the one that really pairs with the original is taken."""
    mod, ru = mods
    src = mod / "localization" / "english"

    best, scored = tm_import.resolve_target_dir(src, ru, "english", "russian")

    assert best == ru / "localization" / "russian"
    assert (ru / "localization" / "replace" / "russian", 0) in scored


def test_resolve_from_localization_root(mods):
    mod, ru = mods
    best, _ = tm_import.resolve_target_dir(
        mod / "localization" / "english", ru / "localization", "english", "russian")
    assert best == ru / "localization" / "russian"


def test_resolve_keeps_correct_path(mods):
    """The right folder is given — there is nothing to substitute."""
    mod, ru = mods
    tgt = ru / "localization" / "russian"
    best, _ = tm_import.resolve_target_dir(
        mod / "localization" / "english", tgt, "english", "russian")
    assert best == tgt


def test_resolve_reports_nothing_when_no_pairs(tmp_path):
    src = tmp_path / "en"
    _write(src / "mod_l_english.yml", EN)
    other = tmp_path / "чужой мод"
    _write(other / "russian" / "другое_l_russian.yml", RU)

    best, scored = tm_import.resolve_target_dir(src, other, "english", "russian")

    assert best is None
    assert [n for _, n in scored] == [0, 0]


def test_dialog_substitutes_nested_folder(mods, qtbot):
    """The window goes down into the language folder itself and says so in the status line."""
    from pdxloc.gui.tm_build_tab import TmBuildTab

    mod, ru = mods
    tab = TmBuildTab()
    qtbot.addWidget(tab)
    tab.src_edit.setText(str(mod / "localization" / "english"))
    tab.tgt_edit.setText(str(ru / "localization"))
    tab._on_tgt_edited()

    assert tab.tgt_edit.text() == str(ru / "localization" / "russian")
    assert "with a pair: 1" in tab.status.text()
    assert "nested translation folder" in tab.status.text()


def test_build_from_mod_root(mods, tmp_path):
    """A build over a pair of mods gives pairs of translation, not an empty file."""
    mod, ru = mods
    out = tmp_path / "agot.pdxtm"
    src = mod / "localization" / "english"
    best, _ = tm_import.resolve_target_dir(src, ru, "english", "russian")

    report = tm_import.build_tm_from_dirs(src, best, out, name="AGOT", kind="import")

    assert report.files == 1 and report.pairs == 2
    assert out.is_file()
