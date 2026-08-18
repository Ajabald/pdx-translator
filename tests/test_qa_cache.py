"""Кеш замечаний: строка помнит свою проверку до следующей правки.

Повод — замер на ванильной HOI4: полный проход по 124 893 парам занимает
3,35 с, и раньше он шёл при каждом открытии проекта в потоке интерфейса.
Здесь проверяется не скорость, а то, ради чего кеш вообще можно держать: он
обязан обесцениваться сам — от правки перевода, от новой редакции оригинала и
от смены набора правил. Кеш, который врёт, хуже отсутствующего.
"""
from __future__ import annotations

import sqlite3

import pytest

from pdxloc.core import qa, qa_rules
from pdxloc.db import init_schema

SQL = ("SELECT id, en_text, ru_text, qa_hash, qa_codes FROM units "
       "WHERE is_deleted = 0")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_schema(c)
    c.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    c.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f.yml')")
    c.executemany(
        "INSERT INTO units (file_id, key, en_text, ru_text, status) VALUES (1,?,?,?,?)",
        [("good", "Cost: $VALUE$", "Цена: $VALUE$", "translated"),
         ("bad", "Cost: $VALUE$", "Цена без переменной", "translated"),
         ("empty", "Cost: $VALUE$", None, "untranslated")])
    c.commit()
    yield c
    c.close()


def issues(conn, rules=None):
    return qa.cached_issues(conn, conn.execute(SQL).fetchall(),
                            rules or qa_rules.default_ruleset())


def stored(conn, key: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT qa_hash, qa_codes FROM units WHERE key = ?", (key,)).fetchone()
    return row["qa_hash"], row["qa_codes"]


def test_first_pass_counts_and_remembers(conn) -> None:
    found = issues(conn)
    assert list(found.values()) == [["dollar_mismatch"]]

    hash_bad, codes_bad = stored(conn, "bad")
    assert codes_bad == "dollar_mismatch" and hash_bad
    # «проверено, замечаний нет» — тоже результат, иначе чистые строки
    # пересчитывались бы каждый раз
    hash_good, codes_good = stored(conn, "good")
    assert hash_good and codes_good == ""
    # строке без перевода проверять нечего
    assert stored(conn, "empty") == (None, None)


def test_second_pass_does_not_recount(conn) -> None:
    """Тот же ответ, но правила уже не зовутся — их подменяем ловушкой."""
    first = issues(conn)

    class Trap(qa_rules.RuleSet):
        def check(self, en_text, ru_text):        # pragma: no cover — не должен зваться
            raise AssertionError("правила пересчитаны, хотя кеш годен")

    assert issues(conn, Trap(qa_rules.BUILTIN_RULES)) == first


def test_an_edited_translation_invalidates_itself(conn) -> None:
    issues(conn)
    conn.execute("UPDATE units SET ru_text = 'Цена: $VALUE$' WHERE key = 'bad'")
    conn.commit()
    assert issues(conn) == {}          # замечание ушло вместе с ошибкой


def test_a_new_source_revision_invalidates_itself(conn) -> None:
    issues(conn)
    conn.execute("UPDATE units SET en_text = 'Cost: $VALUE$ and $OTHER$' "
                 "WHERE key = 'good'")
    conn.commit()
    found = issues(conn)
    assert found[conn.execute(
        "SELECT id FROM units WHERE key='good'").fetchone()[0]] == ["dollar_mismatch"]


def test_a_changed_ruleset_invalidates_everything(conn) -> None:
    """Отпечаток набора входит в хеш, поэтому чистить таблицу не нужно."""
    strict = qa_rules.default_ruleset()
    assert len(issues(conn, strict)) == 1

    quiet = strict.restricted_to({"double_space"})
    assert issues(conn, quiet) == {}
    # и обратно: прежний ответ восстанавливается
    assert len(issues(conn, strict)) == 1


def test_severity_alone_does_not_invalidate(conn) -> None:
    """Серьёзность красит колонку, но не меняет кодов — пересчёт был бы обиден."""
    from dataclasses import replace

    base = qa_rules.default_ruleset()
    issues(conn, base)
    louder = base.with_rule(
        replace(base.get("dollar_mismatch"), severity=qa_rules.INFO))
    assert qa.ruleset_fingerprint(louder) == qa.ruleset_fingerprint(base)


def test_recheck_one_updates_the_row(conn) -> None:
    issues(conn)
    unit_id = conn.execute("SELECT id FROM units WHERE key='bad'").fetchone()[0]
    conn.execute("UPDATE units SET ru_text = 'Цена: $VALUE$' WHERE id = ?", (unit_id,))
    conn.commit()
    assert qa.recheck_one(conn, unit_id, qa_rules.default_ruleset()) == []
    assert stored(conn, "bad")[1] == ""


def test_a_read_only_connection_still_gets_answers(tmp_path) -> None:
    """Фоновые замеры открывают базу только на чтение — считать они вправе."""
    path = tmp_path / "p.sqlite3"
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    init_schema(c)
    c.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    c.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'f.yml')")
    c.execute("INSERT INTO units (file_id, key, en_text, ru_text, status) "
              "VALUES (1,'k','Cost: $VALUE$','Цена','translated')")
    c.commit()
    c.close()

    ro = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    try:
        found = qa.cached_issues(ro, ro.execute(SQL).fetchall(),
                                 qa_rules.default_ruleset())
        assert list(found.values()) == [["dollar_mismatch"]]
    finally:
        ro.close()


def test_a_query_without_cache_columns_still_works(conn) -> None:
    """Старый запрос без qa_hash — считаем всё заново, но отвечаем правильно."""
    rows = conn.execute(
        "SELECT id, en_text, ru_text FROM units WHERE is_deleted = 0").fetchall()
    found = qa.cached_issues(conn, rows, qa_rules.default_ruleset())
    assert list(found.values()) == [["dollar_mismatch"]]
    assert stored(conn, "bad") == (None, None)      # писать было некуда


def test_cache_dies_with_the_row(conn) -> None:
    """Колонки живут в самой строке, так что чистить за собой нечего."""
    issues(conn)
    conn.execute("DELETE FROM files WHERE id = 1")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0
