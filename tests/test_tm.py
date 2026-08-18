"""Тесты памяти переводов."""
from __future__ import annotations

from pdxloc.core import tm


def test_upsert_and_lookup(db):
    tm.upsert(db, "Hello", "Привет", key="k1")
    hits = tm.lookup(db, "Hello")
    assert len(hits) == 1
    assert hits[0].ru_text == "Привет"


def test_upsert_skips_empty_and_same(db):
    tm.upsert(db, "Hello", "")
    tm.upsert(db, "Hello", "Hello")
    assert tm.lookup(db, "Hello") == []


def test_lookup_user_before_vanilla(db):
    tm.upsert(db, "Gold", "Золото (ваниль)", source="vanilla")
    tm.upsert(db, "Gold", "Золото", source="user")
    hits = tm.lookup(db, "Gold")
    assert hits[0].ru_text == "Золото"
    assert hits[0].source == "user"
    assert hits[1].source == "vanilla"


def test_lookup_groups_duplicates(db):
    tm.upsert(db, "Hello", "Привет", key="a")
    tm.upsert(db, "Hello", "Привет", key="b")   # тот же перевод -> conflict update
    hits = tm.lookup(db, "Hello")
    assert len(hits) == 1
