"""A regression of a defect: building a database out of the vanilla CK3 localisation.

The user pointed at the root of the game, the application found not a single pair
but created the file of the database all the same — empty and sound to the eye.
On top of that, on real folders the building goes for tens of seconds with no way
to interrupt it.
"""
from __future__ import annotations

import pytest

from pdxloc.core import tm_import
from pdxloc.project import tm_meta

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'
RU = 'l_russian:\n a:0 "Привет"\n b:0 "Мир"\n'


@pytest.fixture
def game_tree(tmp_path):
    """A tree resembling an installed CK3: the localisation lies deep."""
    root = tmp_path / "Crusader Kings III"
    loc = root / "game" / "localization"
    for lang, text in (("english", EN), ("russian", RU)):
        d = loc / lang
        d.mkdir(parents=True)
        with open(d / f"mod_l_{lang}.yml", "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    (root / "binaries").mkdir()
    return root


@pytest.fixture
def pairless_tree(tmp_path):
    """A tree where there is no translation at all — there is nothing to build out of it."""
    root = tmp_path / "OnlyEnglish"
    d = root / "game" / "localization" / "english"
    d.mkdir(parents=True)
    with open(d / "mod_l_english.yml", "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(EN)
    return root


def test_find_localization_dirs_from_game_root(game_tree):
    """The root of the game is given — we find game/localization/<language>."""
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
    # the root of the game will do too: the language directory in the path is matched
    # on a par with the language mark in the name of the file
    assert tm_import.count_pairs(game_tree, game_tree) == (1, 1)


def test_no_pairs_leaves_no_file(pairless_tree, tmp_path):
    """The main defect: an empty but seemingly working database used to be left behind."""
    out = tmp_path / "broken.pdxtm"
    with pytest.raises(ValueError, match="pair was found"):
        tm_import.build_tm_from_dirs(
            pairless_tree, pairless_tree, out, name="Root")
    assert not out.exists(), "файл пустой базы не должен оставаться на диске"
    assert not out.with_suffix(out.suffix + ".part").exists()


def test_empty_source_dir_reports_clearly(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no localization files"):
        tm_import.build_tm_from_dirs(empty, empty, tmp_path / "x.pdxtm", name="X")


def test_successful_build_from_game_root_dirs(game_tree, tmp_path):
    loc = game_tree / "game" / "localization"
    out = tmp_path / "vanilla.pdxtm"
    report = tm_import.build_tm_from_dirs(
        loc / "english", loc / "russian", out, name="CK3", kind="game")
    assert report.pairs == 2
    assert out.is_file()
    assert not out.with_suffix(out.suffix + ".part").exists()
    meta = tm_meta(out)
    assert meta["kind"] == "game"


def test_game_entries_marked_as_game_source(game_tree, tmp_path):
    """The records of a game database are marked as «a game database» and not «an import»."""
    import sqlite3

    loc = game_tree / "game" / "localization"
    out = tmp_path / "vanilla.pdxtm"
    tm_import.build_tm_from_dirs(
        loc / "english", loc / "russian", out, name="CK3", kind="game")
    conn = sqlite3.connect(f"file:{out.as_posix()}?mode=ro", uri=True)
    sources = {r[0] for r in conn.execute("SELECT DISTINCT source FROM tm_entries")}
    conn.close()
    assert sources == {"game"}


def test_cancel_removes_partial_file(game_tree, tmp_path):
    """An interruption leaves no unfinished database behind."""
    loc = game_tree / "game" / "localization"
    out = tmp_path / "cancelled.pdxtm"
    with pytest.raises(tm_import.TmBuildCancelled):
        tm_import.build_tm_from_dirs(
            loc / "english", loc / "russian", out, name="X",
            should_cancel=lambda: True)
    assert not out.exists()
    assert not out.with_suffix(out.suffix + ".part").exists()


def test_existing_database_survives_failed_rebuild(game_tree, pairless_tree, tmp_path):
    """A failed rebuild does not spoil an already working database."""
    loc = game_tree / "game" / "localization"
    out = tmp_path / "vanilla.pdxtm"
    tm_import.build_tm_from_dirs(loc / "english", loc / "russian", out, name="CK3")
    size_before = out.stat().st_size

    with pytest.raises(ValueError):
        tm_import.build_tm_from_dirs(pairless_tree, pairless_tree, out, name="CK3")
    assert out.stat().st_size == size_before
    assert tm_meta(out)["name"] == "CK3"
