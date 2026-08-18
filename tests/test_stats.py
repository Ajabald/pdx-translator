"""Тесты единой статистики."""
from __future__ import annotations

from pdxloc.core.stats import file_stats, format_status_bar, project_stats


def seed(db):
    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'p', 'e', 'r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'a_l_english.yml')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (2, 1, 'sub/b_l_english.yml')")
    rows = [
        # file, key, status, ru
        (1, "k1", "translated", "р1"),
        (1, "k2", "reviewed", "р2"),
        (1, "k3", "untranslated", None),
        (1, "k4", "auto", "р4"),
        (1, "k5", "stale", "р5"),
        (1, "k6", "ignored", None),
        (1, "k7", "custom", "р7"),
        (1, "k8", "custom", None),      # custom без RU -> не done
        (2, "m1", "translated", "р"),
        (2, "m2", "untranslated", None),
    ]
    for f, k, st, ru in rows:
        db.execute(
            "INSERT INTO units (file_id, key, en_text, ru_text, status) VALUES (?, ?, 'e', ?, ?)",
            (f, k, ru, st))
    # удалённая строка не считается
    db.execute("INSERT INTO units (file_id, key, en_text, status, is_deleted) "
               "VALUES (1, 'dead', 'e', 'translated', 1)")
    db.commit()


def test_project_stats(db):
    seed(db)
    s = project_stats(db, 1)
    # total: все живые кроме ignored (1) = 10 - 1 = 9
    assert s.total == 9
    # done: translated(2) + reviewed(1) + custom с RU (1) = 4
    assert s.done == 4
    assert s.remaining == 5
    assert s.pct == round(100 * 4 / 9, 1)
    assert s.counts["ignored"] == 1


def test_file_stats(db):
    seed(db)
    fs = {f.rel_path: f for f in file_stats(db, 1)}
    assert fs["a_l_english.yml"].total == 7          # 8 живых строк файла - ignored
    assert fs["a_l_english.yml"].done == 3           # translated+reviewed+custom(RU)
    assert fs["sub/b_l_english.yml"].total == 2
    assert fs["sub/b_l_english.yml"].done == 1


def test_pct_decimal(db):
    seed(db)
    s = project_stats(db, 1)
    assert isinstance(s.pct, float)
    text = format_status_bar(s)
    assert "44.4%" in text
    assert "left 5" in text


def test_empty_project(db):
    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (2, 'x', 'e', 'r')")
    s = project_stats(db, 2)
    assert s.total == 0 and s.pct == 0.0
