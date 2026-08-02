"""Регрессия дефекта: сборка базы из ванильной локализации CK3.

Пользователь указал корень игры, приложение не нашло ни одной пары, но всё
равно создало файл базы — пустой и с виду исправный. Плюс на настоящих папках
сборка идёт десятки секунд без возможности прервать.
"""
from __future__ import annotations

import pytest

from ck3loc.core import tm_import
from ck3loc.project import tm_meta

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'


@pytest.fixture
def game_tree(tmp_path):
    """Дерево, похожее на установленную CK3: локализация лежит глубоко."""
    root = tmp_path / "Crusader Kings III"
    loc = root / "game" / "localization"
    for lang, text in (("english", EN), ("russian", RU)):
        d = loc / lang
        d.mkdir(parents=True)
        with open(d / f"mod_l_{lang}.yml", "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    (root / "binaries").mkdir()
    return root


def test_find_localization_dirs_from_game_root(game_tree):
    """Указан корень игры — находим game/localization/<язык>."""
    src, tgt = tm_import.find_localization_dirs(game_tree, "english", "russian")
    assert src == game_tree / "game" / "localization" / "english"
    assert tgt == game_tree / "game" / "localization" / "russian"


def test_find_localization_dirs_from_localization_folder(game_tree):
    loc = game_tree / "game" / "localization"
    src, tgt = tm_import.find_localization_dirs(loc, "english", "russian")
    assert src == loc / "english" and tgt == loc / "russian"


def test_find_localization_dirs_from_language_folder(game_tree):
    en = game_tree / "game" / "localization" / "english"
    src, tgt = tm_import.find_localization_dirs(en, "english", "russian")
    assert src == en and tgt == en.parent / "russian"


def test_find_localization_dirs_missing(tmp_path):
    (tmp_path / "empty").mkdir()
    assert tm_import.find_localization_dirs(tmp_path / "empty") == (None, None)


def test_count_pairs(game_tree):
    loc = game_tree / "game" / "localization"
    assert tm_import.count_pairs(loc / "english", loc / "russian") == (1, 1)
    # корень игры: файлы находятся, но пар нет — каталог языка в пути не меняется
    paired, total = tm_import.count_pairs(game_tree, game_tree)
    assert total == 1 and paired == 0


def test_no_pairs_leaves_no_file(game_tree, tmp_path):
    """Главный дефект: раньше оставалась пустая, но с виду рабочая база."""
    out = tmp_path / "broken.ck3tm"
    with pytest.raises(ValueError, match="ни одной пары"):
        tm_import.build_tm_from_dirs(game_tree, game_tree, out, name="Root")
    assert not out.exists(), "файл пустой базы не должен оставаться на диске"
    assert not out.with_suffix(out.suffix + ".part").exists()


def test_empty_source_dir_reports_clearly(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="нет файлов локализации"):
        tm_import.build_tm_from_dirs(empty, empty, tmp_path / "x.ck3tm", name="X")


def test_successful_build_from_game_root_dirs(game_tree, tmp_path):
    loc = game_tree / "game" / "localization"
    out = tmp_path / "vanilla.ck3tm"
    report = tm_import.build_tm_from_dirs(
        loc / "english", loc / "russian", out, name="CK3", kind="game")
    assert report.pairs == 2
    assert out.is_file()
    assert not out.with_suffix(out.suffix + ".part").exists()
    meta = tm_meta(out)
    assert meta["kind"] == "game"


def test_game_entries_marked_as_game_source(game_tree, tmp_path):
    """Записи игровой базы помечаются как «база игры», а не «импорт»."""
    import sqlite3

    loc = game_tree / "game" / "localization"
    out = tmp_path / "vanilla.ck3tm"
    tm_import.build_tm_from_dirs(
        loc / "english", loc / "russian", out, name="CK3", kind="game")
    conn = sqlite3.connect(f"file:{out.as_posix()}?mode=ro", uri=True)
    sources = {r[0] for r in conn.execute("SELECT DISTINCT source FROM tm_entries")}
    conn.close()
    assert sources == {"game"}


def test_cancel_removes_partial_file(game_tree, tmp_path):
    """Прерывание не оставляет недописанную базу."""
    loc = game_tree / "game" / "localization"
    out = tmp_path / "cancelled.ck3tm"
    with pytest.raises(tm_import.TmBuildCancelled):
        tm_import.build_tm_from_dirs(
            loc / "english", loc / "russian", out, name="X",
            should_cancel=lambda: True)
    assert not out.exists()
    assert not out.with_suffix(out.suffix + ".part").exists()


def test_existing_database_survives_failed_rebuild(game_tree, tmp_path):
    """Неудачная пересборка не портит уже работающую базу."""
    loc = game_tree / "game" / "localization"
    out = tmp_path / "vanilla.ck3tm"
    tm_import.build_tm_from_dirs(loc / "english", loc / "russian", out, name="CK3")
    size_before = out.stat().st_size

    with pytest.raises(ValueError):
        tm_import.build_tm_from_dirs(game_tree, game_tree, out, name="CK3")
    assert out.stat().st_size == size_before
    assert tm_meta(out)["name"] == "CK3"
