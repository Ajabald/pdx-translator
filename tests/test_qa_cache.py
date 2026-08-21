"""The cache of remarks: a row remembers its check until the next edit.

The reason is a measurement on vanilla HOI4: a full pass over 124,893 pairs takes
3.35 s, and it used to go at every opening of a project in the interface thread.
What is checked here is not the speed but what makes it possible to keep a cache
at all: it is obliged to invalidate itself — from an edit of the translation, from
a new revision of the original and from a change of the rule set. A cache that
lies is worse than none.
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
    # «checked, no remarks» is a result too, otherwise clean rows would be
    # recounted every time
    hash_good, codes_good = stored(conn, "good")
    assert hash_good and codes_good == ""
    # a row without a translation has nothing to check
    assert stored(conn, "empty") == (None, None)


def test_second_pass_does_not_recount(conn) -> None:
    """The same answer, but the rules are no longer called — we substitute a trap for them."""
    first = issues(conn)

    class Trap(qa_rules.RuleSet):
        def check(self, en_text, ru_text):        # pragma: no cover — must not be called
            raise AssertionError("правила пересчитаны, хотя кеш годен")

    assert issues(conn, Trap(qa_rules.BUILTIN_RULES)) == first


def test_an_edited_translation_invalidates_itself(conn) -> None:
    issues(conn)
    conn.execute("UPDATE units SET ru_text = 'Цена: $VALUE$' WHERE key = 'bad'")
    conn.commit()
    assert issues(conn) == {}          # the remark went away together with the error


def test_a_new_source_revision_invalidates_itself(conn) -> None:
    issues(conn)
    conn.execute("UPDATE units SET en_text = 'Cost: $VALUE$ and $OTHER$' "
                 "WHERE key = 'good'")
    conn.commit()
    found = issues(conn)
    assert found[conn.execute(
        "SELECT id FROM units WHERE key='good'").fetchone()[0]] == ["dollar_mismatch"]


def test_a_changed_ruleset_invalidates_everything(conn) -> None:
    """The fingerprint of the set goes into the hash, so there is no need to clear the table."""
    strict = qa_rules.default_ruleset()
    assert len(issues(conn, strict)) == 1

    quiet = strict.restricted_to({"double_space"})
    assert issues(conn, quiet) == {}
    # and back: the former answer is restored
    assert len(issues(conn, strict)) == 1


def test_severity_alone_does_not_invalidate(conn) -> None:
    """The severity paints the column but does not change the codes — a recount would be insulting."""
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
    """The background counters open the database read-only — they are entitled to count."""
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
    """An old query without qa_hash — we count everything anew, but we answer rightly."""
    rows = conn.execute(
        "SELECT id, en_text, ru_text FROM units WHERE is_deleted = 0").fetchall()
    found = qa.cached_issues(conn, rows, qa_rules.default_ruleset())
    assert list(found.values()) == [["dollar_mismatch"]]
    assert stored(conn, "bad") == (None, None)      # there was nowhere to write


def test_cache_dies_with_the_row(conn) -> None:
    """The columns live in the row itself, so there is nothing to clear up after."""
    issues(conn)
    conn.execute("DELETE FROM files WHERE id = 1")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 0
