"""Similar rows in the translation memory, and the concordance.

An exact match by hash (`tm.lookup`) stays silent when two rows differ by a word
or two — and when translating a submod on top of a mod that is the ordinary case.
Here a match is looked for by similarity of the text: the candidates are selected
by a full-text index (which lives inside the `.pdxtm`) and scored with `difflib`
from the standard library. On a corpus of fifty thousand pairs a query costs a
couple of milliseconds.
"""
from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from pdxloc import db as db_module
from pdxloc.db import OWN_ORIGIN
from pdxloc.core import markup, tm
from pdxloc.core.models import TmHit
from pdxloc.core.tm import TmRecord

# Candidates per database. Measured on a live project (BLA plus the AGOT
# database of 45 000 pairs): 50 gives 21 ms per row and a suggestion for 40% of
# the untranslated ones, 100 gives 23 ms and 41%, 200 gives 28 ms and the same
# 41%. We take the middle.
CANDIDATES_PER_BASE = 100
MIN_SCORE = 0.6

# A word is two or more letters in a row, no digits and no underscores. The
# name is public: the glossary (`core/glossary.py`) cuts text on the same word
# boundary, and two tokenisations in one application would drift apart on the
# first refinement.
WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)

# Stop words appear in every other row of a database: tens of thousands of
# candidates come back on them, and ranking those ate almost the whole query.
# Measured on the vanilla database (244 000 entries) plus a mod database: 68 ms
# with stop words against 16 ms without, at the same share of suggestions
# found.
STOP_WORDS = frozenset([
    # articles, conjunctions, prepositions
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at",
    "by", "for", "from", "with", "without", "as", "so", "than", "then",
    # copulas and auxiliaries
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "done", "have", "has", "had", "will", "would", "shall", "should", "can",
    "could", "may", "might", "must",
    # pronouns
    "it", "its", "this", "that", "these", "those", "there", "here", "he",
    "she", "they", "we", "you", "your", "his", "her", "their", "our", "my",
    "me", "him", "them", "us",
    # negations and quantifiers
    "not", "no", "too", "very", "just", "also", "all", "any", "some", "such",
    "own", "same", "each", "every", "other", "more", "most", "much", "many",
])


def _tokens(text: str) -> list[str]:
    """The query words without CK3 markup: the tags match in every row alike."""
    return WORD.findall(markup.strip_markup(text).lower())


def _match_expr(tokens: list[str]) -> str:
    """The FTS5 query. The quotes keep words like OR from becoming operators."""
    words = [w for w in tokens if w not in STOP_WORDS] or tokens
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words[:20]))


def _normalized(text: str) -> str:
    return " ".join(markup.strip_markup(text).lower().split())


def _score(matcher: SequenceMatcher, candidate: str) -> float:
    """Similarity with cut-offs: the full ratio() is computed for close pairs only."""
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
    """Similar rows from the project memory and from the attached databases.

    An exact match scores 1.0 and comes first; the rest follow by descending
    similarity. One translation is shown once even when several databases hold
    it.
    """
    from pdxloc import project as project_mod

    tokens = _tokens(en_text)
    if not tokens:
        return []
    query = _normalized(en_text)
    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(query)
    expr = _match_expr(tokens)

    rows: list[tuple[sqlite3.Row, str | None, int, int]] = []   # entry, database, prio, offset
    own_fts = db_module.OWN_TM_FTS
    db_module.ensure_own_tm_index(conn)     # built on the first similarity query
    try:
        own = conn.execute(
            # ORDER BY rank is bm25: we take the candidates where the rare words matched
            # rather than the first that came along. Otherwise the limit cut off the best
            # entry
            f"""SELECT e.id, e.en_text, e.ru_text, e.source, e.key, e.updated_at
                FROM temp.{own_fts} f
                JOIN main.tm_entries e ON e.id = f.rowid
                WHERE f.{own_fts} MATCH ?
                ORDER BY rank
                LIMIT ?""",
            (expr, CANDIDATES_PER_BASE)).fetchall()
        rows += [(r, None, 0, 0) for r in own]
    except sqlite3.Error:
        pass        # the project memory has no index: search the databases only

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
            origin=origin or OWN_ORIGIN, key=row["key"], uses=1,
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
    """How this piece of text was translated before.

    The search goes by substring rather than by words: a translator needs to find
    both «Targaryen» and «of the Iron Islands» whole.
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
