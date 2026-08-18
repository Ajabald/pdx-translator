"""Игра проекта: реестр, схема, загоны и защита от чужого загона.

Формат локализации у всей серии Paradox один, поэтому переводить моды к
Stellaris или HOI4 приложение умело и раньше. Не хватало одного — сказать, к
какой игре относится проект: без этого базы памяти разных игр лежат общей кучей
и подсказывают ванильные строки CK3 переводчику Victoria 3.
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


# --- реестр ---------------------------------------------------------------


def test_every_game_is_described_completely() -> None:
    for game_id, game in games.GAMES.items():
        assert game.id == game_id
        assert game.title and game.folder
        assert game.languages, f"{game_id}: пустой набор языковых папок"
        assert "english" in game.languages    # оригинал у модов всегда английский


def test_ids_and_folders_do_not_collide() -> None:
    """Загон — это папка: два одинаковых имени свалили бы игры в одну кучу."""
    folders = [g.folder.casefold() for g in games.GAMES.values()]
    assert len(folders) == len(set(folders))


def test_language_sets_differ_between_games() -> None:
    """Иначе реестр не нужен: список языков и был бы общим."""
    assert games.languages("eu4") != games.languages("vic3")
    assert "russian" not in games.languages("eu4")     # у EU4 её и правда нет
    assert "russian" in games.languages("ck3")


def test_eu5_stands_apart_from_eu4() -> None:
    """Две «Европы» — две игры: общий загон смешал бы их базы памяти."""
    assert games.title("eu5") == "Europa Universalis V"
    assert games.folder("eu5") != games.folder("eu4")
    assert games.by_folder("EU5") == "eu5"


def test_an_unknown_game_is_a_game_of_its_own() -> None:
    """Идентификатор приезжает из файла проекта — падать на незнакомом нельзя."""
    own = games.get("victoria_2", "Victoria 2")
    assert own.title == "Victoria 2"
    assert own.languages == tuple(PARADOX_LANGUAGES)


@pytest.mark.parametrize("name,expected", [
    ("Victoria 2", "victoria_2"),
    ("Крестоносцы", "game"),           # без латиницы слаг не собрать
    ("  ", "game"),
    ("CK3", "ck3_own"),                # своя игра не притворяется встроенной
])
def test_slug_is_usable_as_a_file_name(name, expected) -> None:
    assert games.slug(name) == expected


def test_own_game_pen_is_named_after_its_id() -> None:
    """Имя игры в проекте не хранится — по папке «Victoria 2» опознать
    проект `victoria_2` было бы уже нечем."""
    assert games.get("victoria_2", "Victoria 2").folder == "victoria_2"


def test_pen_is_recognised_by_its_folder() -> None:
    assert games.by_folder("CK3") == "ck3"
    assert games.by_folder("ck3") == "ck3"        # регистр папки не значим
    assert games.by_folder("Projects") is None


# --- схема ----------------------------------------------------------------


def test_new_project_remembers_its_game(tmp_path, tree) -> None:
    en, ru = tree
    conn = project.create_project(tmp_path / "p.pdxproj", name="P", game="stellaris",
                                  src_root=en, tgt_root=ru)
    try:
        assert project.game(conn) == "stellaris"
    finally:
        conn.close()


def test_default_game_is_ck3(tmp_path, tree) -> None:
    """До этой версии приложение звалось CK3 Translator и других игр не знало."""
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
    # откатываем схему к шестой и убираем колонку, как было до v7
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


# --- загоны и защита ------------------------------------------------------


def test_pens_live_inside_the_usual_folders(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "projects_dir", lambda: tmp_path / "Projects")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tmp_path / "Bdd")
    assert settings.projects_pen("ck3") == tmp_path / "Projects" / "CK3"
    assert settings.bdd_pen("vic3") == tmp_path / "Bdd" / "Victoria 3"


def test_game_is_read_without_opening_the_project(tmp_path, tree) -> None:
    """Спрашивают до открытия: открытый проект держит `-wal`, и переносить поздно."""
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
    """Файл, уехавший без `-wal`, потеряет незаписанное или подхватит чужой."""
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


# --- защита в главном окне ------------------------------------------------


@pytest.fixture
def guard(tmp_path, tree, qtbot, monkeypatch):
    """Главное окно с папкой проектов во временном каталоге."""
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
    """Файл в корне папки проектов — тоже не на месте: загон у него есть."""
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
    """Файл проекта нарочно кладут рядом с модом — приставать к такому нельзя."""
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
    """Папка, которая не загон, — чей-то свой порядок, и он не наше дело."""
    win, make = guard
    path = make("Мод", "stellaris", "Черновики")
    assert win._offer_right_pen(path) == path


def test_a_project_of_an_own_game_lives_in_its_own_pen(guard, tmp_path) -> None:
    """Загон своей игры зовётся как её идентификатор — иначе не опознать."""
    win, make = guard
    path = make("Мод", "victoria_2", "victoria_2")
    assert win._offer_right_pen(path) == path


# --- игра в списках и в шапке ---------------------------------------------


def test_game_travels_with_the_recent_list(tmp_path, monkeypatch) -> None:
    """Иначе стартовому экрану пришлось бы открывать двадцать баз на перерисовку."""
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
    """Записи прежних версий игры не содержат, но проект в загоне говорит сам."""
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
    # порядок групп — по свежести: сверху игра самого недавнего проекта
    assert headers == ["Stellaris", "Crusader Kings III"]
    assert not (rows[0].flags() & Qt.ItemIsSelectable)
    # выбранной становится строка проекта, а не заголовок
    assert screen.list.currentItem().data(Qt.UserRole)
    assert screen._selected_path() is not None


def test_the_header_of_a_group_is_not_a_project(qtbot, tmp_path, monkeypatch) -> None:
    """Команды над заголовком бессмысленны — пути у него нет."""
    from pdxloc.gui.start_screen import StartScreen

    monkeypatch.setattr(settings, "recent_projects", lambda: [
        {"path": str(tmp_path / "a.pdxproj"), "name": "A", "game": "ck3"},
    ])
    screen = StartScreen()
    qtbot.addWidget(screen)
    screen.list.setCurrentRow(0)          # заголовок
    assert screen._selected_path() is None


# --- базы памяти и игра ---------------------------------------------------


def test_a_built_database_carries_its_game(tmp_path, make_tree) -> None:
    from pdxloc.core import tm_import

    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    out = tmp_path / "base.pdxtm"
    tm_import.build_tm_from_dirs(en, ru, out, name="База", game="stellaris")

    meta = project.tm_meta(out)
    assert meta["game"] == "stellaris"


def test_a_database_from_before_the_games_says_nothing(tmp_path, make_tree) -> None:
    """Неизвестно — не то же самое, что неверно: такая база молчит, а не врёт."""
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
    assert path.is_file()          # исходный на месте
