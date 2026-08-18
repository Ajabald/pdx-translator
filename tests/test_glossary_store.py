"""Хранение глоссария: приём, отказ и память об отказе."""
from __future__ import annotations

import pytest

from pdxloc.core import glossary
from pdxloc.core.glossary import APPROVED, CANDIDATE, REJECTED, Candidate
from pdxloc.db import get_connection


@pytest.fixture
def conn(tmp_path):
    c = get_connection(tmp_path / "p.sqlite3")
    c.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    c.commit()
    yield c
    c.close()


def candidate(en="Maester", ru="мейстер", score=0.65, pairs=12) -> Candidate:
    return Candidate(en_term=en, ru_term=ru, score=score, pairs=pairs, runner_up=0.2)


def test_candidates_are_saved_once(conn):
    assert glossary.save_candidates(conn, [candidate()]) == 1
    assert glossary.save_candidates(conn, [candidate()]) == 0
    assert len(glossary.rows(conn)) == 1


def test_a_rejected_term_does_not_come_back(conn):
    """Главное свойство таблицы: отказ переводчика — это данные.

    Без него каждый следующий прогон возвращал бы тот же мусор, и курировать
    список стало бы бессмысленно.
    """
    glossary.save_candidates(conn, [candidate()])
    entry = glossary.rows(conn)[0]
    glossary.set_status(conn, [entry.id], REJECTED)

    assert glossary.save_candidates(conn, [candidate()]) == 0
    assert [e.status for e in glossary.rows(conn)] == [REJECTED]
    assert glossary.rows(conn, status=CANDIDATE) == []


def test_an_approved_term_does_not_fall_back_to_candidate(conn):
    glossary.save_candidates(conn, [candidate()])
    glossary.set_status(conn, [glossary.rows(conn)[0].id], APPROVED)
    glossary.save_candidates(conn, [candidate()])
    assert [e.status for e in glossary.rows(conn)] == [APPROVED]


def test_a_different_spelling_is_still_the_same_term(conn):
    """Корпус меняется, и написание термина вместе с ним.

    Отклонили `Maester → мейстер` — значит отклонили и `maester → Мейстер`.
    Иначе переводчик увидит свой же отказ во второй раз.
    """
    glossary.save_candidates(conn, [candidate()])
    glossary.set_status(conn, [glossary.rows(conn)[0].id], REJECTED)
    assert glossary.save_candidates(conn, [candidate(en="maester", ru="Мейстер")]) == 0
    assert len(glossary.rows(conn)) == 1


def test_duplicates_inside_one_batch_are_collapsed(conn):
    assert glossary.save_candidates(conn, [candidate(), candidate(en="MAESTER")]) == 1


def test_manual_terms_are_approved_on_arrival(conn):
    """Ручной термин никто не предлагал — подтверждать его нечего."""
    glossary.upsert_manual(conn, "Winterfell", "Винтерфелл", note="имя собственное")
    entry = glossary.rows(conn)[0]
    assert entry.status == APPROVED
    assert entry.origin == "manual"
    assert entry.note == "имя собственное"
    assert entry.score is None


def test_manual_upsert_revives_a_rejected_term(conn):
    """Переводчик передумал — руками это должно быть можно.

    Память об отказе защищает от повторных предложений автомата, а не от
    решения человека.
    """
    glossary.save_candidates(conn, [candidate()])
    glossary.set_status(conn, [glossary.rows(conn)[0].id], REJECTED)
    glossary.upsert_manual(conn, "Maester", "мейстер")
    assert [e.status for e in glossary.rows(conn)] == [APPROVED]


def test_only_approved_terms_reach_the_highlighter(conn):
    glossary.save_candidates(conn, [candidate(), candidate(en="Citadel", ru="цитадель")])
    rows = {e.en_term: e.id for e in glossary.rows(conn)}
    glossary.set_status(conn, [rows["Maester"]], APPROVED)
    glossary.set_status(conn, [rows["Citadel"]], REJECTED)
    assert glossary.approved_terms(conn) == {"maester": "мейстер"}


def test_editing_and_deleting(conn):
    glossary.save_candidates(conn, [candidate()])
    entry = glossary.rows(conn)[0]
    glossary.update_entry(conn, entry.id, ru_term="мейстеры", note="во множественном")
    edited = glossary.rows(conn)[0]
    assert edited.ru_term == "мейстеры" and edited.note == "во множественном"
    assert edited.en_term == "Maester"          # не тронуто

    glossary.delete(conn, [entry.id])
    assert glossary.rows(conn) == []


def test_counts_report_every_status(conn):
    glossary.save_candidates(conn, [candidate(), candidate(en="Citadel", ru="цитадель")])
    glossary.set_status(conn, [glossary.rows(conn)[0].id], APPROVED)
    assert glossary.counts(conn) == {CANDIDATE: 1, APPROVED: 1, REJECTED: 0}


def test_search_looks_at_both_sides_and_ignores_case(conn):
    glossary.save_candidates(conn, [candidate(), candidate(en="Citadel", ru="Цитадель")])
    assert len(glossary.rows(conn, search="МЕЙСТ")) == 1
    assert len(glossary.rows(conn, search="citadel")) == 1


def test_empty_calls_do_nothing(conn):
    """Пустой список приходит из окна при пустом выделении — не повод падать."""
    glossary.set_status(conn, [], APPROVED)
    glossary.delete(conn, [])
    assert glossary.save_candidates(conn, []) == 0
