"""Похожие строки в памяти переводов и конкорданс.

Точное совпадение по хешу (`tm.lookup`) молчит, когда строки отличаются на
слово-два — а при переводе сабмода поверх мода это как раз обычный случай.
Здесь совпадение ищется по сходству текста: кандидаты отбираются полнотекстовым
индексом (он живёт внутри `.ck3tm`), а оцениваются `difflib` из стандартной
библиотеки. На корпусе в 50 тысяч пар запрос стоит пару миллисекунд.
"""
from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from ck3loc import db as db_module
from ck3loc.core import qa, tm
from ck3loc.core.models import TmHit
from ck3loc.core.tm import TmRecord

# Кандидатов на базу. Замер на живом проекте (BLA + база AGOT на 45 тыс. пар):
# 50 → 21 мс на строку и подсказка для 40% непереведённых, 100 → 23 мс и 41%,
# 200 → 28 мс и те же 41%. Берём середину.
CANDIDATES_PER_BASE = 100
MIN_SCORE = 0.6

_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)

# Служебные слова есть в каждой второй строке базы: кандидатов по ним приходят
# десятки тысяч, и их ранжирование съедало почти всё время запроса. Замер на
# ванильной базе (244 тыс. записей) плюс база мода: 68 мс со стоп-словами
# против 16 мс без них — при том же проценте найденных подсказок.
STOP_WORDS = frozenset("""
a an the and or but if of to in on at by for from with without as is are was were be been
being it its this that these those there here he she they we you your his her their our my
me him them us not no do does did done have has had will would shall should can could may
might must so than then too very just also all any some such own same each every other more
most much many
""".split())


def _tokens(text: str) -> list[str]:
    """Слова запроса без разметки CK3: теги совпадают у всех строк подряд."""
    return _WORD.findall(qa.strip_markup(text).lower())


def _match_expr(tokens: list[str]) -> str:
    """Запрос к FTS5. Кавычки — чтобы слова вроде OR не считались операторами."""
    words = [w for w in tokens if w not in STOP_WORDS] or tokens
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words[:20]))


def _normalized(text: str) -> str:
    return " ".join(qa.strip_markup(text).lower().split())


def _score(matcher: SequenceMatcher, candidate: str) -> float:
    """Сходство с отсечками: полный ratio() считается только для похожих."""
    matcher.set_seq1(candidate)
    if matcher.real_quick_ratio() < MIN_SCORE or matcher.quick_ratio() < MIN_SCORE:
        return 0.0
    return matcher.ratio()


def lookup_similar(
    conn: sqlite3.Connection,
    en_text: str,
    *,
    limit: int = 8,
    min_score: float = MIN_SCORE,
) -> list[TmHit]:
    """Похожие строки из памяти проекта и подключённых баз.

    Точное совпадение получает 1.0 и идёт первым; дальше — по убыванию
    сходства. Один перевод показывается один раз, даже если он есть в
    нескольких базах.
    """
    from ck3loc import project as project_mod

    tokens = _tokens(en_text)
    if not tokens:
        return []
    query = _normalized(en_text)
    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(query)
    expr = _match_expr(tokens)

    rows: list[tuple[sqlite3.Row, str | None, int, int]] = []   # запись, база, prio, offset
    own_fts = db_module.OWN_TM_FTS
    try:
        own = conn.execute(
            # ORDER BY rank — это bm25: берём кандидатов, где совпали редкие
            # слова, а не первые попавшиеся. Иначе лимит отсекал лучшую запись
            f"""SELECT e.id, e.en_text, e.ru_text, e.source, e.key, e.updated_at
                FROM temp.{own_fts} f
                JOIN main.tm_entries e ON e.id = f.rowid
                WHERE f.{own_fts} MATCH ?
                ORDER BY rank
                LIMIT ?""",
            (expr, CANDIDATES_PER_BASE)).fetchall()
        rows += [(r, None, 0, 0) for r in own]
    except sqlite3.Error:
        pass        # индекса памяти проекта нет — ищем только по базам

    for base in project_mod.attached_tm_bases(conn):
        if not base.has_fts:
            continue
        try:
            found = conn.execute(
                f"""SELECT e.id, e.en_text, e.ru_text, e.source, e.key, e.updated_at
                    FROM {base.alias}.tm_fts f
                    JOIN {base.alias}.tm_entries e ON e.id = f.rowid
                    WHERE f.tm_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?""",
                (expr, CANDIDATES_PER_BASE)).fetchall()
        except sqlite3.Error:
            continue
        rows += [(r, base.origin, base.prio, base.id_offset) for r in found]

    best: dict[str, TmHit] = {}
    for row, origin, prio, offset in rows:
        score = _score(matcher, _normalized(row["en_text"]))
        if score < min_score:
            continue
        current = best.get(row["ru_text"])
        if current is not None and (current.score, -current.prio) >= (score, -prio):
            continue
        best[row["ru_text"]] = TmHit(
            ru_text=row["ru_text"], source=row["source"],
            origin=origin or "Проект", key=row["key"], uses=1,
            updated_at=row["updated_at"],
            id=row["id"] if origin is None else -(row["id"] + offset),
            editable=origin is None, score=score, en_text=row["en_text"],
            prio=prio,
        )
    hits = sorted(best.values(), key=lambda h: (-h.score, h.prio))
    return hits[:limit]


def concordance(
    conn: sqlite3.Connection, fragment: str, *, limit: int = 200,
) -> list[TmRecord]:
    """Как этот кусок текста переводили раньше.

    Ищем по подстроке, а не по словам: переводчику нужно найти и «Targaryen»,
    и «of the Iron Islands» целиком.
    """
    fragment = fragment.strip()
    if len(fragment) < 2:
        return []
    pattern = f"%{tm.escape_like(fragment)}%"
    rows = conn.execute(
        """SELECT id, en_text, ru_text, source, key, origin, editable, updated_at
           FROM tm_all
           WHERE pylower(en_text) LIKE pylower(?) ESCAPE '\\'
           ORDER BY prio, LENGTH(en_text)
           LIMIT ?""",
        (pattern, limit)).fetchall()
    return [
        TmRecord(
            id=r["id"], en_text=r["en_text"], ru_text=r["ru_text"],
            source=r["source"], key=r["key"], origin=r["origin"],
            editable=bool(r["editable"]), updated_at=r["updated_at"],
        )
        for r in rows
    ]
