"""Term glossary: statistics propose, a human confirms.

Similar strings are matched whole (`core/fuzzy.py`), but that yields no hint of
the kind "the database already holds Targaryen → Таргариен": a proper name lives
inside a hundred different sentences, and no two of them are alike. Here it is
dug out by co-occurrence statistics over the translation memory.

**The automaton never writes anything into a translation.** It piles candidates
into the `glossary` table with status `candidate`; accepting or rejecting them
is the translator's work. Accepted terms are highlighted in the source field.

The measure is the Dice coefficient over document frequency: a word counts once
per pair of strings, however many times it occurs inside it. Measured on a live
corpus (AGOT + the Russian translation, 51,651 pairs) — 0.8 s, 4024 candidates,
1287 of them with confidence ≥ 0.60: `Maester → мейстер` 0.65,
`Winterfell → винтерфелл` 0.63, `Lannister → ланнистер` 0.56.

Three things that measurement laid bare; each is answered here explicitly:

1. **Russian word forms split the count.** `таргариен` and `таргариенов` are
   one word but two keys, and each collects half the weight. Cured by grouping
   on the stem (`_ru_stem`).
2. **A multi-word term falls apart.** `Kingsguard` → «Королевская гвардия»:
   neither «королевская» nor «гвардия» wins on its own. Cured by counting
   bigrams on the Russian side.
3. **Boilerplate noise.** `Valyrian → эссос` scores 0.63 simply because both
   things are mentioned in the same descriptions. Cured by demanding a gap over
   the runner-up: a real term is translated by one word, while noise arrives as
   a dense group.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from pdxloc.core import markup
from pdxloc.core.fuzzy import STOP_WORDS, WORD

# --- selection thresholds --------------------------------------------------
#
# Values from that same measurement. MIN_PAIRS cuts off accidental
# co-occurrence: on two pairs Dice easily gives one, and the list fills with
# rubbish faster than the translator can page through it.
MIN_PAIRS = 3
MIN_SCORE = 0.5

# How many times over the runner-up the best candidate is obliged to score.
# This is the answer to boilerplate noise: `Maester` leaves its runner-up far
# behind, `Valyrian` is shadowed by one — because what gets translated is not
# the word but the whole paragraph around it.
GAP = 1.3

# A stem shorter than this is not cut: «граф» and «град» share a three-letter
# beginning, and trimming to three would glue them into one nest.
MIN_STEM = 4

# Russian endings, sorted longest-first when applied. The list is not the
# morphology of the language but a working minimum for our case: proper names
# and Paradox game terms, that is, nouns and adjectives. Verb forms are
# deliberately absent — a verb is never a term, and by cutting «-ет» we would
# glue unrelated words together.
_RU_ENDINGS = (
    # adjectives
    "ыми", "ими", "ого", "его", "ому", "ему", "ая", "яя", "ое", "ее",
    "ые", "ие", "ый", "ий", "ой", "ым", "им", "ом", "ем", "их", "ых",
    # nouns
    "ами", "ями", "ах", "ях", "ов", "ев", "ей", "ам", "ям", "ию", "ия",
    "ии", "ье", "ья", "ью", "ей", "ов",
    "а", "я", "о", "е", "ы", "и", "у", "ю", "ь",
)
_RU_ENDINGS = tuple(sorted(set(_RU_ENDINGS), key=len, reverse=True))

# Russian function words. Same role as STOP_WORDS in fuzzy: without them «и»,
# «в», «на» co-occur with everything and crawl into every nest.
RU_STOP_WORDS = frozenset([
    "и", "а", "но", "или", "да", "же", "ли", "бы", "не", "ни",
    "в", "во", "на", "за", "по", "из", "от", "до", "к", "ко", "с", "со",
    "у", "о", "об", "обо", "для", "при", "про", "над", "под", "перед", "без",
    "через", "между", "около",
    "это", "этот", "эта", "эти", "тот", "та", "те", "то", "там", "тут",
    "он", "она", "оно", "они", "его", "её", "их", "им", "ему", "ей", "ним",
    "вы", "ты", "мы", "я", "вас", "нас", "вам", "нам", "меня", "тебя",
    "ваш", "ваша", "ваши", "наш", "наша", "наши", "мой", "моя", "мои", "свой",
    "весь", "вся", "все", "всё", "всех", "всем", "также", "уже", "ещё", "еще",
    "как", "что", "чем", "чтобы", "если", "когда", "который", "которая",
    "быть", "был", "была", "было", "были", "есть", "будет", "будут",
    "может", "можно", "нужно", "надо", "очень", "только", "более", "менее",
])

# An English term of one letter or of digits is of no use to us: WORD already
# demands two letters in a row, what is left here is to cut off the very short.
MIN_TERM_LEN = 3

# What share of a nest's occurrences a word form is obliged to collect to be
# considered for display at all. Protection against a typo and a truncation:
# they are short, and short is what we prefer (see `_display_form`).
MIN_FORM_SHARE = 0.15

# What share of its strings a word is obliged to hold capitalised mid-phrase
# to count as a proper noun.
#
# A threshold, not a fact, and here is why. The test "occurred at least once"
# failed on the live AGOT corpus on the word `Now`: **two** strings out of
# 45,822 write it in the middle of a phrase (there, where a line break
# collapsed into a space), and those two were enough for the word to land on
# the allow-list forever — and all 804 of its pairs behind it. For a real name
# the share is close to one (`Targaryen` — 0.98), for a chance match it is
# vanishingly small, and any threshold between them parts them equally well.
MIN_PROPER_SHARE = 0.25

# --- statuses --------------------------------------------------------------

CANDIDATE = "candidate"
APPROVED = "approved"
REJECTED = "rejected"

AUTO = "auto"
MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class Candidate:
    """A proposal from the statistics. `runner_up` is the score of the second
    candidate for the same English term: by it the window shows why the
    proposal passed selection."""
    en_term: str
    ru_term: str
    score: float
    pairs: int
    runner_up: float


@dataclass(frozen=True, slots=True)
class Entry:
    """A glossary row as it lies in the database."""
    id: int
    en_term: str
    ru_term: str
    status: str
    score: float | None
    pairs: int | None
    note: str
    origin: str
    updated_at: str | None


# --- parsing the text ------------------------------------------------------


def _en_tokens(text: str) -> set[str]:
    """The English words of a string: no markup, no stop words, nothing short."""
    words = WORD.findall(markup.strip_markup(text).lower())
    return {w for w in words
            if w not in STOP_WORDS and len(w) >= MIN_TERM_LEN}


# What the text before a word ends with when the word opens a phrase. Full
# stop, colon and line break are obvious; quotes and dashes are here because in
# Paradox localisation a line of speech starts right with them all the time.
#
# The typographic quotes are not here for beauty: AGOT descriptions are
# quotations from the books, and they open with `“`, not `"`. While those were
# missing from the list, `“Though the…` and `“After the Doom…` counted as
# mid-phrase, that is, `Though` and `After` passed as proper nouns and held the
# top of the list on five hundred pairs.
_SENTENCE_END = ('.', '!', '?', ':', ';', '\n', '"', "'", '«', '»',
                 '“', '”', '‘', '’',      # “ ” ‘ ’
                 '—', '–', '-', '(', '[')


def _proper_nouns(text: str) -> set[str]:
    """Words written with a capital **not at the start of a phrase**.

    That is the mark of a proper noun, the one separating `Targaryen` from
    `Now`. Both turn up capitalised, but `Now` only there, where anything at
    all is capitalised, while `Targaryen` stands with a capital mid-sentence.

    The measure is crude and inexact in both directions: a heading set in caps
    will not get in here, and the first word after an abbreviation will get in
    for nothing. But on the live AGOT corpus it removes `Now`, `Though`,
    `After`, `Even` and `Perhaps` from the top of the list without touching a
    single real name — and it is the translator who sorts the list out by hand,
    so the price of an error here is no higher than one extra row.
    """
    clean = markup.strip_markup(text)
    words = WORD.findall(clean)
    if not words:
        return set()

    # Title Case is evidence of nothing. Trait names, buttons and event titles
    # Paradox writes with **every** word capitalised, and `Now` in "The Long
    # Night Is Now" looks a proper noun exactly as much as `Targaryen` does.
    #
    # The thresholds are picked so as not to catch an ordinary sentence: "House
    # Targaryen rises" is three words, two capitalised, and that is not Title
    # Case but a house name mid-phrase. We demand both a length of four words
    # and three quarters capitalised: "The Long Night Is Now" gives five out of
    # five and is cut off, while a short phrase with a name is not.
    capitalised = sum(1 for w in words if w[:1].isupper())
    if len(words) >= 4 and capitalised >= len(words) * 0.75:
        return set()

    found: set[str] = set()
    for m in WORD.finditer(clean):
        if not m.group(0)[:1].isupper():
            continue
        before = clean[:m.start()].rstrip()
        if not before or before.endswith(_SENTENCE_END):
            continue        # phrase start — anything at all is capitalised here
        found.add(m.group(0).lower())
    return found


def _display_form(forms: Counter) -> str:
    """Which word form to show a human.

    The nest `таргариен` gathers `таргариена`, `таргариенов`, `таргариену` —
    and none of them may be pasted into a translation. The base form is what is
    needed, and morphology we have none, so we take **the shortest of those
    that occur noticeably**: in Russian the nominative is almost always shorter
    than the oblique cases, and the share threshold cuts off the typo and the
    truncation, which also happen to be short.

    The threshold is a share and not a count on purpose: a nest may hold four
    occurrences, or four hundred.
    """
    total = sum(forms.values())
    common = [w for w, n in forms.items() if n >= total * MIN_FORM_SHARE]
    return min(common or list(forms), key=lambda w: (len(w), w))


def _ru_stem(word: str) -> str:
    """The stem of a Russian word — by cutting an ending from the table above.

    Not morphological analysis and makes no such claim: the one task here is
    for `таргариен`, `таргариена` and `таргариенов` to land in one nest and add
    up their weight instead of splitting it three ways.
    """
    for ending in _RU_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= MIN_STEM:
            return word[:-len(ending)]
    return word


def _ru_words(text: str) -> list[str]:
    """The Russian words of a string in order — the order is for bigrams."""
    return [w for w in WORD.findall(markup.strip_markup(text).lower())
            if w not in RU_STOP_WORDS and len(w) >= MIN_TERM_LEN]


def _ru_keys(text: str) -> tuple[set[str], dict[str, str]]:
    """The keys of the Russian side and how to show them to a human.

    The key is a stem (or a pair of stems for a bigram), what we show is the
    original words: «мейстеров» in a list of terms would look like a typo,
    whereas `мейстер` is what the translator will confirm.
    """
    words = _ru_words(text)
    stems = [_ru_stem(w) for w in words]
    keys: set[str] = set()
    surface: dict[str, str] = {}

    for stem, word in zip(stems, words, strict=True):
        keys.add(stem)
        surface.setdefault(stem, word)

    # bigrams of adjacent words — the answer to «Kingsguard → Королевская гвардия»
    for i in range(len(stems) - 1):
        key = f"{stems[i]} {stems[i + 1]}"
        keys.add(key)
        surface.setdefault(key, f"{words[i]} {words[i + 1]}")

    return keys, surface


# --- extraction ------------------------------------------------------------


def extract(
    conn: sqlite3.Connection,
    *,
    min_pairs: int = MIN_PAIRS,
    min_score: float = MIN_SCORE,
    gap: float = GAP,
    proper_only: bool = True,
    progress=None,
    cancelled=None,
) -> list[Candidate]:
    """Term candidates over all the available translation memory.

    The corpus is the `tm_all` view: the project's own memory plus the attached
    databases (see `db.ensure_tm_view` and `project.py`). We do not separate
    them: the vanilla database is itself the main source of settled terms.

    `proper_only` keeps only words met capitalised mid-phrase. Measured on the
    live AGOT corpus (45,822 pairs): without it the top of the list by coverage
    is taken by `Now → теперь`, `Though → хотя`, `After → после` — correct
    translations, but a mod glossary has no need of them, and sorting them out
    is the translator's work by hand.

    `progress(done, total)` and `cancelled()` are for a run from the window:
    a corpus happens to be a quarter of a million records.
    """
    rows = conn.execute("SELECT en_text, ru_text FROM tm_all").fetchall()
    total = len(rows)

    df_en: dict[str, int] = defaultdict(int)
    df_ru: dict[str, int] = defaultdict(int)
    df_pair: dict[tuple[str, str], int] = defaultdict(int)
    en_forms: dict[str, Counter] = defaultdict(Counter)
    ru_forms: dict[str, Counter] = defaultdict(Counter)
    proper_hits: dict[str, int] = defaultdict(int)

    for done, row in enumerate(rows, 1):
        if cancelled is not None and cancelled():
            return []
        if progress is not None and done % 2000 == 0:
            progress(done, total)

        en_text, ru_text = row["en_text"], row["ru_text"]
        if not en_text or not ru_text:
            continue
        en_keys = _en_tokens(en_text)
        if not en_keys:
            continue
        ru_keys, surface = _ru_keys(ru_text)
        if not ru_keys:
            continue

        for key, word in surface.items():
            ru_forms[key][word] += 1
        _remember_en_forms(en_forms, en_text, en_keys)
        for e in _proper_nouns(en_text) & en_keys:
            proper_hits[e] += 1

        for e in en_keys:
            df_en[e] += 1
        for r in ru_keys:
            df_ru[r] += 1
        for e in en_keys:
            for r in ru_keys:
                df_pair[(e, r)] += 1

    if progress is not None:
        progress(total, total)

    en_surface = {k: _display_form(c) for k, c in en_forms.items()}
    ru_surface = {k: _display_form(c) for k, c in ru_forms.items()}
    proper = {e for e, hits in proper_hits.items()
              if hits >= df_en[e] * MIN_PROPER_SHARE}
    return _rank(df_en, df_ru, df_pair, en_surface, ru_surface,
                 allowed=proper if proper_only else None,
                 min_pairs=min_pairs, min_score=min_score, gap=gap)


def _remember_en_forms(forms: dict[str, Counter], text: str, keys: set[str]) -> None:
    """How an English term is written in live text.

    We count every spelling, and `_display_form` picks later. English is not
    troubled by declension, but the case drifts apart: `maester` in the list
    would look like sloppiness next to `Maester`.
    """
    for word in WORD.findall(markup.strip_markup(text)):
        key = word.lower()
        if key in keys:
            forms[key][word] += 1


def _rank(
    df_en: dict[str, int],
    df_ru: dict[str, int],
    df_pair: dict[tuple[str, str], int],
    en_surface: dict[str, str],
    ru_surface: dict[str, str],
    *,
    allowed: set[str] | None,
    min_pairs: int,
    min_score: float,
    gap: float,
) -> list[Candidate]:
    """Dice, the pick of the best translation per term, and the gap cut-off."""
    best: dict[str, list[tuple[float, str, int]]] = defaultdict(list)
    for (e, r), pairs in df_pair.items():
        if pairs < min_pairs:
            continue
        if allowed is not None and e not in allowed:
            continue
        score = 2 * pairs / (df_en[e] + df_ru[r])
        if score < min_score:
            continue
        best[e].append((score, r, pairs))

    out: list[Candidate] = []
    for e, hits in best.items():
        # On an equal score the longer translation wins, and that is not a
        # matter of taste: for `Kingsguard` the bigram «королевская гвардия»
        # and both its halves score exactly one, because they travel strictly
        # together. Leave the order to the string sort — and half the term
        # would beat the whole of it alphabetically.
        hits.sort(key=lambda h: (h[0], len(h[1].split()), h[1]), reverse=True)
        score, r, pairs = hits[0]
        runner_up = _runner_up(hits, r)
        # The gap over the runner-up is what tells a term from boilerplate
        # noise. Zero means "there is no runner-up at all", and that is the
        # best gap there can be.
        if runner_up and score < gap * runner_up:
            continue
        out.append(Candidate(
            en_term=en_surface.get(e, e),
            ru_term=ru_surface.get(r, r),
            score=round(score, 4),
            pairs=pairs,
            runner_up=round(runner_up, 4),
        ))
    out.sort(key=lambda c: (-c.score, c.en_term.casefold()))
    return out


def _runner_up(hits: list[tuple[float, str, int]], winner: str) -> float:
    """The score of the best candidate not related to the winner.

    A unigram inside the winning bigram does not count as the runner-up: for
    «королевская гвардия» the second by score is «гвардия», and without this
    proviso the bigram would fail the gap test against its own half.
    """
    parts = set(winner.split())
    for score, term, _pairs in hits[1:]:
        if parts & set(term.split()):
            continue
        return score
    return 0.0


# --- storage ---------------------------------------------------------------


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"], en_term=row["en_term"], ru_term=row["ru_term"],
        status=row["status"], score=row["score"], pairs=row["pairs"],
        note=row["note"], origin=row["origin"], updated_at=row["updated_at"],
    )


def rows(conn: sqlite3.Connection, *, status: str | None = None,
         search: str = "") -> list[Entry]:
    """Glossary rows; `status=None` — all of them."""
    sql = ["SELECT * FROM glossary"]
    where, params = [], []
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if search.strip():
        where.append("(pylower(en_term) LIKE pylower(?) "
                     "OR pylower(ru_term) LIKE pylower(?))")
        pattern = f"%{search.strip()}%"
        params += [pattern, pattern]
    if where:
        sql.append("WHERE " + " AND ".join(where))
    # candidates by descending confidence, accepted ones alphabetically: the
    # first list is worked through top to bottom, the second is searched by eye
    sql.append("ORDER BY CASE status WHEN 'candidate' THEN -score ELSE 0 END, "
               "pylower(en_term)")
    return [_entry(r) for r in conn.execute(" ".join(sql), params)]


def save_candidates(conn: sqlite3.Connection, found: list[Candidate]) -> int:
    """Write the candidates down without touching the ones already reviewed.

    Skipping pairs already known is exactly what memory of a refusal is: an
    accepted term will not roll back into candidates, and a rejected one will
    not return from the dead on the next run. Returns the number of genuinely
    new rows.

    We compare **case-insensitively**, and one `ON CONFLICT` is not enough
    here. The spelling of the English term is chosen from the corpus
    (`_remember_en_surface`), and the corpus changes between runs: let a
    database turn up where `Maester` occurs only in lower case — and
    `UNIQUE(en_term, ru_term)` sees a new pair, while the translator sees their
    own rejected term a second time. Reading what is already known and sifting
    it out here is cheaper than fencing in a case-insensitive index: `lower()`
    in SQLite knows no Cyrillic, and our own function cannot be put into an
    index — the file would stop opening in anything but us.
    """
    known = {(r["en_term"].casefold(), r["ru_term"].casefold())
             for r in conn.execute("SELECT en_term, ru_term FROM glossary")}
    fresh = []
    for c in found:
        key = (c.en_term.casefold(), c.ru_term.casefold())
        if key in known:
            continue
        known.add(key)                  # and against duplicates inside the batch
        fresh.append((c.en_term, c.ru_term, c.score, c.pairs))
    conn.executemany(
        """INSERT INTO glossary (en_term, ru_term, status, score, pairs, origin)
           VALUES (?, ?, 'candidate', ?, ?, 'auto')
           ON CONFLICT(en_term, ru_term) DO NOTHING""", fresh)
    conn.commit()
    return len(fresh)


def set_status(conn: sqlite3.Connection, ids: list[int], status: str) -> None:
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE glossary SET status = ?, updated_at = datetime('now') "
        f"WHERE id IN ({placeholders})", [status, *ids])
    conn.commit()


def upsert_manual(conn: sqlite3.Connection, en_term: str, ru_term: str,
                  *, note: str = "") -> None:
    """A term entered by hand is accepted at once: nobody proposed it."""
    conn.execute(
        """INSERT INTO glossary (en_term, ru_term, status, note, origin, updated_at)
           VALUES (?, ?, 'approved', ?, 'manual', datetime('now'))
           ON CONFLICT(en_term, ru_term) DO UPDATE SET
               status = 'approved', note = excluded.note,
               updated_at = datetime('now')""",
        (en_term.strip(), ru_term.strip(), note.strip()))
    conn.commit()


def update_entry(conn: sqlite3.Connection, entry_id: int, *,
                 en_term: str | None = None, ru_term: str | None = None,
                 note: str | None = None) -> None:
    sets, params = [], []
    for column, value in (("en_term", en_term), ("ru_term", ru_term), ("note", note)):
        if value is not None:
            sets.append(f"{column} = ?")
            params.append(value.strip())
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    conn.execute(f"UPDATE glossary SET {', '.join(sets)} WHERE id = ?",
                 [*params, entry_id])
    conn.commit()


def delete(conn: sqlite3.Connection, ids: list[int]) -> None:
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM glossary WHERE id IN ({placeholders})", ids)
    conn.commit()


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many rows are in each status — for the bottom bar of the window."""
    found = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM glossary GROUP BY status")}
    return {s: found.get(s, 0) for s in (CANDIDATE, APPROVED, REJECTED)}


# --- highlighting ----------------------------------------------------------


def approved_terms(conn: sqlite3.Connection) -> dict[str, str]:
    """Accepted terms: English in lower case → Russian, as it is to be shown."""
    return {r["en_term"].lower(): r["ru_term"] for r in conn.execute(
        "SELECT en_term, ru_term FROM glossary WHERE status = 'approved'")}


def build_index(terms: dict[str, str]) -> re.Pattern | None:
    """One compiled search for all the terms at once.

    Long ones before short: otherwise `Kings` inside `Kingsguard` takes the
    match first, and half a term is highlighted. An empty dictionary gives
    None — a regex out of an empty alternation matches anything at all.
    """
    if not terms:
        return None
    ordered = sorted(terms, key=len, reverse=True)
    alternatives = "|".join(re.escape(t) for t in ordered)
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def find_terms(text: str, index: re.Pattern | None,
               terms: dict[str, str]) -> list[tuple[int, int, str]]:
    """Occurrences of accepted terms: (start, end, translation).

    Pieces of markup are skipped whole — there is no point underlining the
    innards of `[GetTrait…]` or an icon name in `@gold!`, there is no prose
    there.
    """
    if index is None or not text:
        return []
    skip = markup.spans(text, markup.strip_tokens())
    out: list[tuple[int, int, str]] = []
    for m in index.finditer(text):
        if any(s < m.end() and m.start() < e for s, e in skip):
            continue
        ru = terms.get(m.group(0).lower())
        if ru:
            out.append((m.start(), m.end(), ru))
    return out
