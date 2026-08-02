"""Сборка базы из перевода-мода: он лежит отдельным модом со своим деревом.

Живой случай: русификатор AGOT (мод 2962803371) держит рядом две папки —
`localization/russian` с переводом самого мода и `localization/replace/russian`
с заменой ванильных строк. Пользователь указал их общий корень, и приложение
ответило «ни один из 417 файлов оригинала не имеет пары», хотя парная папка
лежала на уровень ниже.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from ck3loc.core import tm_import  # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'
RU_VANILLA = 'l_russian:\n vanilla_key:0 "Ванильная строка"\n'


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)


@pytest.fixture
def mods(tmp_path):
    """Два мода воркшопа: сам мод и отдельный русификатор."""
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
    """Из двух папок языка берётся та, что действительно парная оригиналу."""
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
    """Указана правильная папка — подменять нечего."""
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
    """Окно само спускается в папку языка и говорит об этом в строке состояния."""
    from ck3loc.gui.tm_import_dialog import TmImportDialog

    mod, ru = mods
    dlg = TmImportDialog()
    qtbot.addWidget(dlg)
    dlg.src_edit.setText(str(mod / "localization" / "english"))
    dlg.tgt_edit.setText(str(ru / "localization"))
    dlg._on_tgt_edited()

    assert dlg.tgt_edit.text() == str(ru / "localization" / "russian")
    assert "с парой: 1" in dlg.status.text()
    assert "вложенная папка" in dlg.status.text()


def test_build_from_mod_root(mods, tmp_path):
    """Сборка базы по паре модов даёт пары перевода, а не пустой файл."""
    mod, ru = mods
    out = tmp_path / "agot.ck3tm"
    src = mod / "localization" / "english"
    best, _ = tm_import.resolve_target_dir(src, ru, "english", "russian")

    report = tm_import.build_tm_from_dirs(src, best, out, name="AGOT", kind="import")

    assert report.files == 1 and report.pairs == 2
    assert out.is_file()
