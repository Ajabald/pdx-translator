"""Похожие строки в памяти переводов и конкорданс.

Точное совпадение по хешу молчит, когда строки отличаются на слово-два — а при
переводе сабмода поверх мода это обычный случай.
"""
from __future__ import annotations

import sqlite3

import pytest

from ck3loc import db as db_module
from ck3loc import project
from ck3loc.core import fuzzy, tm, tm_import

SEED = [
    ("I am Targaryen", "Я Таргариен"),
    ("You are Targaryen", "Ты Таргариен"),
    ("The Bridge Must Be Paid", "Мост должен быть оплачен"),
    ("Completely unrelated sentence about goats", "Совсем про другое, про коз"),
]


@pytest.fixture
def conn(tmp_path):
    """Соединение как у настоящего проекта: ATTACH баз работает только так."""
    c = project.create_project(
        tmp_path / "p.ck3proj", name="P", src_root=tmp_path / "en", tgt_root=tmp_path / "ru")
    yield c
    c.close()


@pytest.fixture
def memory(conn):
    for en, ru in SEED:
        tm.upsert(conn, en, ru)
    conn.commit()
    return conn


def _old_schema_base(path, name="Старая", pairs=(("The Bridge Must Be Paid", "Старый перевод"),)):
    """База схемы v1 — без индекса похожих строк."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(tm_import.TM_DDL)
    conn.executemany(
        "INSERT INTO tm_meta (key, value) VALUES (?, ?)",
        [("format", "ck3tm"), ("schema_version", "1"), ("name", name),
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
    """Ради этого всё и затевалось: строка отличается на пару слов."""
    hits = fuzzy.lookup_similar(memory, "You are Targaryen")
    similar = {h.ru_text: h.score for h in hits}
    assert "Я Таргариен" in similar
    assert 0.6 <= similar["Я Таргариен"] < 1.0


def test_markup_does_not_break_match(memory):
    """Разметка CK3 одинакова у сотен строк и сравнению только мешает."""
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
    """Индекс памяти проекта живёт на триггерах — без них новая запись
    находилась бы только после перезапуска."""
    tm.upsert(memory, "We are Targaryen", "Мы Таргариены")
    memory.commit()
    assert any(h.ru_text == "Мы Таргариены"
               for h in fuzzy.lookup_similar(memory, "We are Targaryen"))


def test_empty_query(memory):
    assert fuzzy.lookup_similar(memory, "   ") == []
    assert fuzzy.lookup_similar(memory, "[GetTitle]$VAR$") == []


def test_concordance_finds_fragment(memory):
    found = fuzzy.concordance(memory, "targaryen")      # регистр не важен
    assert {r.ru_text for r in found} == {"Я Таргариен", "Ты Таргариен"}
    assert fuzzy.concordance(memory, "x") == []         # слишком короткий кусок


# --- поиск по подключённым базам ---

@pytest.fixture
def base_path(tmp_path):
    """Готовая база .ck3tm с индексом."""
    path = tmp_path / "Bdd" / "mod_english-russian.ck3tm"
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
    """База старой схемы просто не участвует в поиске похожих, а не роняет его."""
    old = _old_schema_base(tmp_path / "Bdd" / "old_english-russian.ck3tm")
    project.attach_tm_sources(conn, [old, base_path])

    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Repaid")

    assert hits                                        # поиск работает
    assert "Старый перевод" not in {h.ru_text for h in hits}
    # …а точное совпадение по хешу от неё по-прежнему приходит
    assert "Старый перевод" in {h.ru_text for h in tm.lookup(conn, "The Bridge Must Be Paid")}


def test_build_index_upgrades_old_base(conn, tmp_path):
    old = _old_schema_base(tmp_path / "Bdd" / "old_english-russian.ck3tm")

    assert tm_import.build_fts_index(old) == 1
    assert tm_import.build_fts_index(old) == 1      # повторный вызов безвреден

    project.attach_tm_sources(conn, [old])
    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Repaid")
    assert [h.ru_text for h in hits] == ["Старый перевод"]


def test_own_memory_wins_over_base(conn, base_path):
    """При равном сходстве свой перевод важнее чужой базы."""
    tm.upsert(conn, "The Bridge Must Be Paid", "Мой перевод моста")
    conn.commit()
    project.attach_tm_sources(conn, [base_path])

    hits = fuzzy.lookup_similar(conn, "The Bridge Must Be Paid")

    assert hits[0].ru_text == "Мой перевод моста"
    assert hits[0].editable


def test_fts5_available():
    assert db_module.fts5_available() is True      # стандартная сборка Python
