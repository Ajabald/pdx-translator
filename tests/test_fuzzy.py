"""Similar rows in the translation memory, and the concordance.

An exact match by hash keeps quiet when the rows differ by a word or two — and
when translating a submod on top of a mod that is an ordinary case.
"""
from __future__ import annotations

import sqlite3

import pytest

from pdxloc import db as db_module
from pdxloc import project
from pdxloc.core import fuzzy, tm, tm_import

SEED = [
    ("I am Targaryen", "Я Таргариен"),
    ("You are Targaryen", "Ты Таргариен"),
    ("The Bridge Must Be Paid", "Мост должен быть оплачен"),
    ("Completely unrelated sentence about goats", "Совсем про другое, про коз"),
]


@pytest.fixture
def conn(tmp_path):
    """A connection as in a real project: ATTACH of databases works only that way."""
    c = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=tmp_path / "en", tgt_root=tmp_path / "ru")
    yield c
    c.close()


@pytest.fixture
def memory(conn):
    for en, ru in SEED:
        tm.upsert(conn, en, ru)
    conn.commit()
    return conn


def _old_schema_base(path, name="Старая", pairs=(("The Bridge Must Be Paid", "Старый перевод"),)):
    """A database of schema v1 — without the index of similar rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(tm_import.TM_DDL)
    conn.executemany(
        "INSERT INTO tm_meta (key, value) VALUES (?, ?)",
        [("format", "pdxtm"), ("schema_version", "1"), ("name", name),
         ("src_lang", "english"), ("tgt_lang", "russian"), ("kind", "import")])
    conn.executemany(
        "INSERT INTO tm_entries (en_hash, en_text, ru_text, source) VALUES (?, ?, ?, 'import')",
        [(tm.en_hash(en), en, ru) for en, ru in pairs])
    conn.commit()
    conn.close()
    return path


def test_exact_match_scores_one_and_comes_first(memory):
    hits = fuzzy.lookup_similar(memory, "You are Targaryen")
    assert hits[0].ru_text == "Ты Таргариен"
    assert hits[0].score == 1.0
    assert hits[0].en_text == "You are Targaryen"


def test_similar_string_found(memory):
    """That is what the whole thing was started for: the row differs by a couple of words."""
    hits = fuzzy.lookup_similar(memory, "You are Targaryen")
    similar = {h.ru_text: h.score for h in hits}
    assert "Я Таргариен" in similar
    assert 0.6 <= similar["Я Таргариен"] < 1.0


def test_markup_does_not_break_match(memory):
    """The CK3 markup is the same in hundreds of rows and only gets in the way of the comparison."""
    hits = fuzzy.lookup_similar(memory, "#bold The Bridge Must Be Paid#!")
    assert hits and hits[0].ru_text == "Мост должен быть оплачен"
    assert hits[0].score == 1.0


def test_unrelated_string_filtered_out(memory):
    assert fuzzy.lookup_similar(memory, "Sail to Braavos at dawn") == []


def test_threshold_respected(memory):
    loose = fuzzy.lookup_similar(memory, "Targaryen", min_score=0.2)
    strict = fuzzy.lookup_similar(memory, "Targaryen", min_score=0.9)
    assert len(loose) > len(strict)


def test_fresh_translation_is_searchable_at_once(memory):
    """The index of the project memory lives on triggers — without them a new record
    would be found only after a restart."""
    tm.upsert(memory, "We are Targaryen", "Мы Таргариены")
    memory.commit()
    assert any(h.ru_text == "Мы Таргариены"
               for h in fuzzy.lookup_similar(memory, "We are Targaryen"))


def test_empty_query(memory):
    assert fuzzy.lookup_similar(memory, "   ") == []
    assert fuzzy.lookup_similar(memory, "[GetTitle]$VAR$") == []


def test_concordance_finds_fragment(memory):
    found = fuzzy.concordance(memory, "targaryen")      # the case does not matter
    assert {r.ru_text for r in found} == {"Я Таргариен", "Ты Таргариен"}
    assert fuzzy.concordance(memory, "x") == []         # too short a piece


# --- the search over the attached databases ---

@pytest.fixture
def base_path(tmp_path):
    """A ready .pdxtm database with an index."""
    path = tmp_path / "Bdd" / "mod_english-russian.pdxtm"
    conn = tm_import.create_tm_database(
        path, name="Мод", src_lang="english", tgt_lang="russian", kind="import")
    conn.executemany(
        "INSERT INTO tm_entries (en_hash, en_text, ru_text, source) VALUES (?, ?, ?, 'import')",
        [(tm.en_hash(en), en, ru, ) for en, ru in
         [("The Bridge Must Be Paid", "Мост должен быть оплачен"),
          ("The Bridge Must Be Repaired", "Мост должен быть починен")]])
    conn.execute("INSERT INTO tm_fts(tm_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    return path


def test_similar_from_attached_base(conn, base_path):
    project.attach_tm_sources(conn, [base_path])

    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Repaid")

    texts = {h.ru_text: h.score for h in hits}
    assert "Мост должен быть оплачен" in texts
    assert "Мост должен быть починен" in texts
    assert all(h.origin == "Мод" and not h.editable for h in hits)


def test_base_without_index_does_not_break_search(conn, base_path, tmp_path):
    """A database of the old schema simply takes no part in the search for
    similar ones — it does not bring the search down."""
    old = _old_schema_base(tmp_path / "Bdd" / "old_english-russian.pdxtm")
    project.attach_tm_sources(conn, [old, base_path])

    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Repaid")

    assert hits                                        # the search works
    assert "Старый перевод" not in {h.ru_text for h in hits}
    # …while an exact match by hash still comes from it
    assert "Старый перевод" in {h.ru_text for h in tm.lookup(conn, "The Bridge Must Be Paid")}


def test_build_index_upgrades_old_base(conn, tmp_path):
    old = _old_schema_base(tmp_path / "Bdd" / "old_english-russian.pdxtm")

    assert tm_import.build_fts_index(old) == 1
    assert tm_import.build_fts_index(old) == 1      # a repeated call is harmless

    project.attach_tm_sources(conn, [old])
    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Repaid")
    assert [h.ru_text for h in hits] == ["Старый перевод"]


def test_own_memory_wins_over_base(conn, base_path):
    """With equal similarity one's own translation matters more than a foreign database."""
    tm.upsert(conn, "The Bridge Must Be Paid", "Мой перевод моста")
    conn.commit()
    project.attach_tm_sources(conn, [base_path])

    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Paid")

    assert hits[0].ru_text == "Мой перевод моста"
    assert hits[0].editable


def test_fts5_available():
    assert db_module.fts5_available() is True      # the standard build of Python
