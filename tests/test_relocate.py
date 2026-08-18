"""Смена папки оригинала: предпросмотр считает потери, перевод переживает переезд."""
from __future__ import annotations

import shutil

from pdxloc.core import relocate
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

from test_scanner import get_unit, make_project

EN = 'l_english:\n greet:0 "Winter is coming"\n bye:0 "Farewell"\n'
RU = 'l_russian:\n greet:0 "Зима близко"\n bye:0 "Прощай"\n'
EN2 = 'l_english:\n extra:0 "Second file"\n'


def setup(db, make_tree, spec=None):
    en = make_tree(spec or {"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    return pid, en


def test_preview_full_match(db, make_tree, tmp_path):
    """Мод переехал целиком: набор файлов совпадает, терять нечего."""
    pid, en = setup(db, make_tree)
    moved = tmp_path / "moved"
    shutil.copytree(en, moved)

    p = relocate.preview_root_change(db, pid, moved)
    assert p.usable and not p.risky
    assert p.root == moved
    assert p.matched == ["m_l_english.yml"]
    assert not p.missing and not p.added
    assert "matches completely" in p.summary()


def test_preview_counts_what_will_be_lost(db, make_tree, tmp_path):
    """Файла нет в новой папке — видно, сколько строк и переводов уедет."""
    pid, en = setup(db, make_tree, {"m_l_english.yml": EN, "extra_l_english.yml": EN2})
    moved = tmp_path / "partial"
    moved.mkdir()
    shutil.copy(en / "m_l_english.yml", moved / "m_l_english.yml")

    p = relocate.preview_root_change(db, pid, moved)
    assert p.usable and p.risky
    assert p.missing == ["extra_l_english.yml"]
    assert p.units_missing == 1
    assert p.translated_missing == 0        # extra не переводили
    assert "Files not found: 1" in p.summary()


def test_preview_counts_translated_separately(db, make_tree, tmp_path):
    """Переводы в пропавшем файле считаются отдельной строкой — они уйдут в архив."""
    pid, en = setup(db, make_tree, {"m_l_english.yml": EN, "extra_l_english.yml": EN2})
    moved = tmp_path / "only_extra"
    moved.mkdir()
    shutil.copy(en / "extra_l_english.yml", moved / "extra_l_english.yml")

    p = relocate.preview_root_change(db, pid, moved)
    assert p.missing == ["m_l_english.yml"]
    assert (p.units_missing, p.translated_missing) == (2, 2)
    assert "will go to the archive" in p.summary()


def test_preview_finds_language_subfolder(db, make_tree, tmp_path):
    """Показали папку мода целиком — берём ту, где лежат знакомые файлы."""
    pid, en = setup(db, make_tree)
    mod = tmp_path / "mod"
    target = mod / "localization" / "english"
    target.mkdir(parents=True)
    shutil.copy(en / "m_l_english.yml", target / "m_l_english.yml")

    p = relocate.preview_root_change(db, pid, mod)
    assert p.root == target
    assert p.matched == ["m_l_english.yml"]
    assert str(target) in p.summary()


def test_preview_picks_the_matching_language_folder(db, make_tree, tmp_path):
    """У мода две папки английского — выигрывает та, где файлы базы."""
    pid, en = setup(db, make_tree)
    mod = tmp_path / "agot"
    (mod / "localization" / "english").mkdir(parents=True)
    replace = mod / "localization" / "replace" / "english"
    replace.mkdir(parents=True)
    shutil.copy(en / "m_l_english.yml", replace / "m_l_english.yml")
    with open(mod / "localization" / "english" / "other_l_english.yml",
              "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(EN2)

    p = relocate.preview_root_change(db, pid, mod)
    assert p.root == replace


def test_preview_rejects_folder_without_loc_files(db, make_tree, tmp_path):
    pid, _ = setup(db, make_tree)
    empty = tmp_path / "empty"
    empty.mkdir()

    p = relocate.preview_root_change(db, pid, empty)
    assert not p.usable
    assert "no localization files" in p.error


def test_preview_reports_missing_folder(db, make_tree, tmp_path):
    pid, _ = setup(db, make_tree)
    p = relocate.preview_root_change(db, pid, tmp_path / "нет такой")
    assert not p.usable
    assert "not found" in p.error


def test_preview_warns_when_nothing_matches(db, make_tree, tmp_path):
    """Папка чужого мода: файлы локализации есть, но ни один не знаком базе."""
    pid, _ = setup(db, make_tree)
    alien = tmp_path / "alien"
    alien.mkdir()
    with open(alien / "alien_l_english.yml", "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(EN2)

    p = relocate.preview_root_change(db, pid, alien)
    assert p.usable                      # запретить нельзя: автор мог всё переименовать
    assert not p.matched
    assert "whole translation goes to the archive" in p.summary()


def test_translations_survive_relocation(db, make_tree, tmp_path):
    """Главное: после переезда мода и рескана переводы на месте."""
    pid, en = setup(db, make_tree)
    moved = tmp_path / "steam2" / "mod" / "english"
    shutil.copytree(en, moved)
    shutil.rmtree(en)

    relocate.set_en_root(db, pid, moved)
    stats = scan_project(db, pid)

    assert stats.deleted == 0
    assert stats.unchanged == 2
    u = get_unit(db, "greet")
    assert u["ru_text"] == "Зима близко"
    assert u["status"] == Status.TRANSLATED.value
    assert not u["is_deleted"]


def test_new_version_in_another_folder_becomes_stale(db, make_tree, tmp_path):
    """Переезд и обновление разом: изменившаяся строка — «Устарело», перевод цел."""
    pid, en = setup(db, make_tree)
    moved = tmp_path / "v2"
    shutil.copytree(en, moved)
    with open(moved / "m_l_english.yml", "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(EN.replace('"Winter is coming"', '"Winter has come"'))

    relocate.set_en_root(db, pid, moved)
    scan_project(db, pid)

    u = get_unit(db, "greet")
    assert u["status"] == Status.STALE.value
    assert u["ru_text"] == "Зима близко"
    assert u["prev_en_text"] == "Winter is coming"
    assert get_unit(db, "bye")["status"] == Status.TRANSLATED.value


def test_set_en_root_is_visible_to_the_scanner(db, make_tree, tmp_path):
    pid, en = setup(db, make_tree)
    moved = tmp_path / "elsewhere"
    shutil.copytree(en, moved)
    assert relocate.set_en_root(db, pid, moved) == moved
    assert relocate.get_en_root(db, pid) == moved
