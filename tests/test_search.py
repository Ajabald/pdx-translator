"""Тесты поиска: регистронезависимость для кириллицы и экранирование LIKE."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pdxloc.db import register_functions  # noqa: E402
from pdxloc.gui.units_model import UnitFilters, UnitsTableModel, escape_like  # noqa: E402


def seed(db):
    register_functions(db)
    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'p', 'e', 'r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'a_l_english.yml')")
    rows = [
        ("greet", "Hello World", "Привет Мир"),
        ("shout", "HELLO THERE", "ЗДРАВСТВУЙТЕ"),
        ("agot_bla_key", "Some text", "Некий текст"),
        ("agotXbla_key", "Other text", "Другой текст"),
        ("percent", "100% done", "100% готово"),
    ]
    for key, en, ru in rows:
        db.execute(
            "INSERT INTO units (file_id, key, en_text, ru_text, status) "
            "VALUES (1, ?, ?, ?, 'translated')", (key, en, ru))
    db.commit()


def found_keys(db, needle):
    model = UnitsTableModel(db)
    model.reload(1, UnitFilters(search=needle))
    return {model.row_data(i)["key"] for i in range(model.rowCount())}


def test_cyrillic_case_insensitive(db, qtbot):
    seed(db)
    assert found_keys(db, "привет") == {"greet"}
    assert found_keys(db, "ПРИВЕТ") == {"greet"}
    assert found_keys(db, "ПрИвЕт") == {"greet"}
    assert found_keys(db, "здравствуйте") == {"shout"}


def test_latin_case_insensitive(db, qtbot):
    seed(db)
    assert found_keys(db, "hello") == {"greet", "shout"}
    assert found_keys(db, "HELLO") == {"greet", "shout"}


def test_underscore_is_literal(db, qtbot):
    seed(db)
    # '_' не должен работать как «любой символ»
    assert found_keys(db, "agot_bla") == {"agot_bla_key"}


def test_percent_is_literal(db, qtbot):
    seed(db)
    assert found_keys(db, "100%") == {"percent"}
    assert found_keys(db, "%") == {"percent"}


def test_escape_like():
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("c:\\path") == "c:\\\\path"
