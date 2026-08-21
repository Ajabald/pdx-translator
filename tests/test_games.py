"""The game of a project: the registry, the schema, the pens, and the guard against a foreign pen.

The localisation format is one for the whole Paradox series, so the application
could translate mods for Stellaris or HOI4 before this too. One thing was
missing — saying which game a project belongs to: without that the memory
databases of different games lie in one common heap and prompt vanilla CK3 rows
to a Victoria 3 translator.
"""
from __future__ import annotations

import pytest

from pdxloc import db, project, settings
from pdxloc.core import games
from pdxloc.core.languages import PARADOX_LANGUAGES

EN = 'l_english:\n a:0 "Hello"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def tree(make_tree):
    return make_tree({"m_l_english.yml": EN}, "en"), make_tree(
        {"m_l_russian.yml": RU}, "ru")


# --- the registry ---------------------------------------------------------


def test_every_game_is_described_completely() -> None:
    for game_id, game in games.GAMES.items():
        assert game.id == game_id
        assert game.title and game.folder
        assert game.languages, f"{game_id}: пустой набор языковых папок"
        assert "english" in game.languages    # the original of a mod is always English


def test_ids_and_folders_do_not_collide() -> None:
    """A pen is a folder: two identical names would tip the games into one heap."""
    folders = [g.folder.casefold() for g in games.GAMES.values()]
    assert len(folders) == len(set(folders))


def test_language_sets_differ_between_games() -> None:
    """Otherwise the registry is not needed: the list of languages would be common."""
    assert games.languages("eu4") != games.languages("vic3")
    assert "russian" not in games.languages("eu4")     # EU4 really does not have it
    assert "russian" in games.languages("ck3")


def test_eu5_stands_apart_from_eu4() -> None:
    """Two «Europas» are two games: a common pen would mix their memory databases."""
    assert games.title("eu5") == "Europa Universalis V"
    assert games.folder("eu5") != games.folder("eu4")
    assert games.by_folder("EU5") == "eu5"


def test_an_unknown_game_is_a_game_of_its_own() -> None:
    """The identifier arrives from a project file — falling over on an unknown one will not do."""
    own = games.get("victoria_2", "Victoria 2")
    assert own.title == "Victoria 2"
    assert own.languages == tuple(PARADOX_LANGUAGES)


@pytest.mark.parametrize("name,expected", [
    ("Victoria 2", "victoria_2"),
    ("Крестоносцы", "game"),           # without Latin letters no slug can be built
    ("  ", "game"),
    ("CK3", "ck3_own"),                # a game of one's own does not pretend to be built-in
])
def test_slug_is_usable_as_a_file_name(name, expected) -> None:
    assert games.slug(name) == expected


def test_own_game_pen_is_named_after_its_id() -> None:
    """The name of a game is not stored in a project — by the folder «Victoria 2»
    there would be nothing left to recognise the project `victoria_2` by."""
    assert games.get("victoria_2", "Victoria 2").folder == "victoria_2"


def test_pen_is_recognised_by_its_folder() -> None:
    assert games.by_folder("CK3") == "ck3"
    assert games.by_folder("ck3") == "ck3"        # the case of the folder does not matter
    assert games.by_folder("Projects") is None


# --- the schema -----------------------------------------------------------


def test_new_project_remembers_its_game(tmp_path, tree) -> None:
    en, ru = tree
    conn = project.create_project(tmp_path / "p.pdxproj", name="P", game="stellaris",
                                  src_root=en, tgt_root=ru)
    try:
        assert project.game(conn) == "stellaris"
    finally:
        conn.close()


def test_default_game_is_ck3(tmp_path, tree) -> None:
    """Until this version the application was called CK3 Translator and knew no other games."""
    en, ru = tree
    conn = project.create_project(tmp_path / "p.pdxproj", name="P",
                                  src_root=en, tgt_root=ru)
    try:
        assert project.game(conn) == games.CK3
    finally:
        conn.close()


def test_migration_v6_to_v7_adds_the_column_without_touching_rows(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "old.pdxproj"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.execute("INSERT INTO projects (id, name, en_root, ru_root) "
                 "VALUES (1, 'P', 'en', 'ru')")
    conn.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f')")
    conn.execute("INSERT INTO units (file_id, key, en_text) VALUES (1, 'k', 'Hello')")
    # we roll the schema back to the sixth and remove the column, as it was before v7
    conn.execute("ALTER TABLE projects DROP COLUMN game")
    conn.execute("UPDATE schema_meta SET value = '6' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    conn = project.open_project(path, [])
    try:
        assert project.game(conn) == games.CK3
        assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 1
    finally:
        conn.close()


def test_the_game_can_be_changed(tmp_path, tree) -> None:
    en, ru = tree
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    project.set_game(conn, "hoi4")
    conn.close()

    conn = project.open_project(path, [])
    try:
        assert project.game(conn) == "hoi4"
    finally:
        conn.close()


# --- the pens and the guard -----------------------------------------------


def test_pens_live_inside_the_usual_folders(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    assert settings.projects_pen("ck3") == tmp_path / "Projects" / "CK3"
    assert settings.bdd_pen("vic3") == tmp_path / "Bdd" / "Victoria 3"


def test_game_is_read_without_opening_the_project(tmp_path, tree) -> None:
    """It is asked before opening: an open project holds a `-wal`, and moving is then too late."""
    en, ru = tree
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", game="eu4",
                                  src_root=en, tgt_root=ru)
    conn.close()
    assert project.read_game(path) == "eu4"


def test_reading_the_game_of_a_foreign_file_is_not_a_crash(tmp_path) -> None:
    junk = tmp_path / "не-проект.pdxproj"
    junk.write_bytes(b"\x00\x01 not a database")
    assert project.read_game(junk) is None


def test_moving_a_project_takes_its_journal_along(tmp_path, tree) -> None:
    """A file that has left without its `-wal` will lose the unwritten or pick up a foreign one."""
    en, ru = tree
    path = tmp_path / "Projects" / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.execute("INSERT INTO files (project_id, rel_path) VALUES (1, 'x')")
    conn.commit()
    companions = {p.name for p in project.project_companions(path)}
    conn.close()

    target = project.move_project_file(path, tmp_path / "Projects" / "CK3")
    assert target.is_file()
    assert not path.exists()
    for name in companions:
        assert not (tmp_path / "Projects" / name).exists(), name

    conn = project.open_project(target, [])
    try:
        assert project.project_name(conn) == "P"
    finally:
        conn.close()


# --- the guard in the main window -----------------------------------------


@pytest.fixture
def guard(tmp_path, tree, qtbot, monkeypatch):
    """The main window with the projects folder in a temporary directory."""
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    monkeypatch.setattr(settings, "recent_projects", lambda: [])
    monkeypatch.setattr(settings, "last_project_path", lambda: None)
    monkeypatch.setattr(settings, "remember_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "forget_project", lambda *a, **k: None)
    monkeypatch.setattr(settings, "set_last_project_path", lambda p: None)

    from PySide6.QtWidgets import QMessageBox

    from pdxloc.gui import main_window as mw

    monkeypatch.setattr(mw.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    win = mw.MainWindow()
    qtbot.addWidget(win)

    def make(name: str, game: str, where) -> object:
        en, ru = tree
        folder = tmp_path / "Projects" / where if where else tmp_path / "Projects"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.pdxproj"
        conn = project.create_project(path, name=name, game=game,
                                      src_root=en, tgt_root=ru)
        conn.close()
        return path

    return win, make


def test_a_project_in_the_wrong_pen_is_offered_a_move(guard, tmp_path) -> None:
    win, make = guard
    path = make("Мод", "stellaris", "CK3")
    moved = win._offer_right_pen(path)
    assert moved == tmp_path / "Projects" / "Stellaris" / "Мод.pdxproj"
    assert moved.is_file() and not path.exists()


def test_a_project_lying_loose_among_the_pens_is_taken_in(guard, tmp_path) -> None:
    """A file in the root of the projects folder is out of place too: it has a pen."""
    win, make = guard
    path = make("Мод", "hoi4", None)
    moved = win._offer_right_pen(path)
    assert moved == tmp_path / "Projects" / "HOI4" / "Мод.pdxproj"


def test_a_project_in_its_own_pen_is_left_alone(guard) -> None:
    win, make = guard
    path = make("Мод", "ck3", "CK3")
    assert win._offer_right_pen(path) == path


def test_a_project_outside_the_projects_folder_is_none_of_our_business(
        guard, tmp_path, tree) -> None:
    """A project file is put next to the mod on purpose — pestering about that will not do."""
    win, _ = guard
    en, ru = tree
    path = tmp_path / "Мой мод" / "перевод.pdxproj"
    path.parent.mkdir(parents=True)
    conn = project.create_project(path, name="M", game="stellaris",
                                  src_root=en, tgt_root=ru)
    conn.close()
    assert win._offer_right_pen(path) == path
    assert path.is_file()


def test_a_stranger_folder_inside_projects_is_left_alone(guard, tmp_path) -> None:
    """A folder that is not a pen is somebody's own order, and that is not our business."""
    win, make = guard
    path = make("Мод", "stellaris", "Черновики")
    assert win._offer_right_pen(path) == path


def test_a_project_of_an_own_game_lives_in_its_own_pen(guard, tmp_path) -> None:
    """The pen of a game of one's own is named like its identifier — otherwise there is no recognising it."""
    win, make = guard
    path = make("Мод", "victoria_2", "victoria_2")
    assert win._offer_right_pen(path) == path


# --- the game in the lists and in the header ------------------------------


def test_game_travels_with_the_recent_list(tmp_path, monkeypatch) -> None:
    """Otherwise the start screen would have to open twenty databases for a redraw."""
    store: dict[str, str] = {}

    class Fake:
        def value(self, key, default=""):
            return store.get(key, default)

        def setValue(self, key, value):
            store[key] = value

    monkeypatch.setattr(settings, "qsettings", lambda: Fake())
    settings.remember_project(tmp_path / "p.pdxproj", "P", 1, 2, game="hoi4")
    assert settings.recent_projects()[0]["game"] == "hoi4"


def test_the_pen_tells_the_game_of_an_old_record(tmp_path) -> None:
    """The records of former versions hold no game, but a project in a pen speaks for itself."""
    old = {"path": str(tmp_path / "Projects" / "CK3" / "p.pdxproj"), "name": "P"}
    assert settings.project_game_hint(old) == "ck3"
    loose = {"path": str(tmp_path / "где-то" / "p.pdxproj"), "name": "P"}
    assert settings.project_game_hint(loose) == ""


def test_start_screen_groups_projects_by_game(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import Qt

    from pdxloc.gui.start_screen import StartScreen

    monkeypatch.setattr(settings, "recent_projects", lambda: [
        {"path": str(tmp_path / "a.pdxproj"), "name": "A", "game": "stellaris"},
        {"path": str(tmp_path / "b.pdxproj"), "name": "B", "game": "ck3"},
        {"path": str(tmp_path / "c.pdxproj"), "name": "C", "game": "stellaris"},
    ])
    screen = StartScreen()
    qtbot.addWidget(screen)

    rows = [screen.list.item(i) for i in range(screen.list.count())]
    headers = [r.text() for r in rows if not r.data(Qt.UserRole)]
    # the order of the groups is by freshness: the game of the most recent project on top
    assert headers == ["Stellaris", "Crusader Kings III"]
    assert not (rows[0].flags() & Qt.ItemIsSelectable)
    # the row of the project becomes the selected one, not the header
    assert screen.list.currentItem().data(Qt.UserRole)
    assert screen._selected_path() is not None


def test_the_header_of_a_group_is_not_a_project(qtbot, tmp_path, monkeypatch) -> None:
    """Commands over a header are meaningless — it has no path."""
    from pdxloc.gui.start_screen import StartScreen

    monkeypatch.setattr(settings, "recent_projects", lambda: [
        {"path": str(tmp_path / "a.pdxproj"), "name": "A", "game": "ck3"},
    ])
    screen = StartScreen()
    qtbot.addWidget(screen)
    screen.list.setCurrentRow(0)          # the header
    assert screen._selected_path() is None


# --- the memory databases and the game ------------------------------------


def test_a_built_database_carries_its_game(tmp_path, make_tree) -> None:
    from pdxloc.core import tm_import

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    out = tmp_path / "base.pdxtm"
    tm_import.build_tm_from_dirs(en, ru, out, name="База", game="stellaris")

    meta = project.tm_meta(out)
    assert meta["game"] == "stellaris"


def test_a_database_from_before_the_games_says_nothing(tmp_path, make_tree) -> None:
    """Unknown is not the same as wrong: such a database keeps quiet, it does not lie."""
    from pdxloc.core import tm_import

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    out = tmp_path / "base.pdxtm"
    tm_import.build_tm_from_dirs(en, ru, out, name="База")
    assert project.tm_meta(out)["game"] == ""


def test_moving_onto_an_existing_file_is_refused(tmp_path, tree) -> None:
    en, ru = tree
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.close()
    pen = tmp_path / "CK3"
    pen.mkdir()
    (pen / "p.pdxproj").write_text("занято", encoding="utf-8")

    with pytest.raises(FileExistsError):
        project.move_project_file(path, pen)
    assert path.is_file()          # the source one is in place
