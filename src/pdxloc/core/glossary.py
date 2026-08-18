"""Глоссарий терминов: статистика предлагает, человек подтверждает.

Похожие строки ищутся целиком (`core/fuzzy.py`), но подсказки уровня «в базе
есть Targaryen → Таргариен» это не даёт: имя собственное живёт внутри сотни
разных предложений, и ни одно из них не похоже на другое. Здесь оно достаётся
статистикой совстречаемости по памяти переводов.

**Автомат не пишет в перевод ничего и никогда.** Он складывает кандидатов в
таблицу `glossary` со статусом `candidate`; принять или отклонить — работа
переводчика. Принятые термины подсвечиваются в поле оригинала.

Мера — коэффициент Дайса по документной частоте: слово считается один раз на
пару строк, сколько бы раз в ней ни встретилось. Замер на живом корпусе
(AGOT + русификатор, 51 651 пара) — 0,8 с, 4024 кандидата, из них 1287 с
уверенностью ≥ 0.60: `Maester → мейстер` 0.65, `Winterfell → винтерфелл` 0.63,
`Lannister → ланнистер` 0.56.

Три вещи, которые тот замер и вскрыл; каждая здесь решена явно:

1. **Русские словоформы дробят счёт.** `таргариен` и `таргариенов` — одно
   слово, но два ключа, и каждый набирает половину веса. Лечится группировкой
   по основе (`_ru_stem`).
2. **Многословный термин разваливается.** `Kingsguard` → «Королевская
   гвардия»: ни «королевская», ни «гвардия» поодиночке не выигрывают. Лечится
   счётом биграмм на русской стороне.
3. **Шаблонный шум.** `Valyrian → эссос` набирает 0.63 просто потому, что обе
   вещи упоминаются в одних и тех же описаниях. Лечится требованием отрыва от
   второго кандидата: настоящий термин переводится одним словом, а шум идёт
   плотной группой.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from pdxloc.core import markup
from pdxloc.core.fuzzy import STOP_WORDS, WORD

# --- пороги отбора ---------------------------------------------------------
#
# Значения с того же замера. MIN_PAIRS отсекает случайную совстречаемость:
# на двух парах Дайс легко даёт единицу, и список заполняется мусором быстрее,
# чем переводчик успевает его листать.
MIN_PAIRS = 3
MIN_SCORE = 0.5

# Во сколько раз лучший кандидат обязан обойти второго. Это ответ на шаблонный
# шум: у `Maester` второй кандидат далеко позади, у `Valyrian` — вплотную,
# потому что переводится не он, а весь абзац вокруг.
GAP = 1.3

# Основа короче этого не режется: у «граф» и «град» общее начало из трёх букв,
# и стрижка до трёх слепила бы их в одно гнездо.
MIN_STEM = 4

# Русские окончания, отсортированные при применении от длинных к коротким.
# Список — не морфология языка, а рабочий минимум под наш случай: имена
# собственные и термины игр Paradox, то есть существительные и прилагательные.
# Глагольных форм здесь намеренно нет — термином глагол не бывает, а
# срезав «-ет», мы бы слепили несвязанные слова.
_RU_ENDINGS = (
    # прилагательные
    "ыми", "ими", "ого", "его", "ому", "ему", "ая", "яя", "ое", "ее",
    "ые", "ие", "ый", "ий", "ой", "ым", "им", "ом", "ем", "их", "ых",
    # существительные
    "ами", "ями", "ах", "ях", "ов", "ев", "ей", "ам", "ям", "ию", "ия",
    "ии", "ье", "ья", "ью", "ей", "ов",
    "а", "я", "о", "е", "ы", "и", "у", "ю", "ь",
)
_RU_ENDINGS = tuple(sorted(set(_RU_ENDINGS), key=len, reverse=True))

# Служебные слова русского. Роль та же, что у STOP_WORDS в fuzzy: без них
# «и», «в», «на» совстречаются со всем подряд и лезут в каждое гнездо.
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

# Английский термин из одной буквы или из цифр нам не нужен: WORD уже требует
# двух букв подряд, здесь остаётся отсечь совсем короткое.
MIN_TERM_LEN = 3

# Какую долю вхождений гнезда обязана набрать словоформа, чтобы её вообще
# рассматривали как показываемую. Защита от опечатки и обрезка: они короткие, а
# короткое мы предпочитаем (см. `_display_form`).
MIN_FORM_SHARE = 0.15

# Какую долю своих строк слово обязано отстоять с заглавной посреди фразы,
# чтобы считаться именем собственным.
#
# Порог, а не факт, и вот почему. Признак «хоть раз встретилось» на живом
# корпусе AGOT провалился на слове `Now`: **две** строки из 45 822 пишут его
# в середине фразы (там, где перевод строки схлопнулся в пробел), и этих двух
# хватало, чтобы слово попало в белый список навсегда — а следом за ним все
# 804 его пары. У настоящего имени доля близка к единице (`Targaryen` — 0.98),
# у случайного совпадения она исчезающе мала, и любой порог между ними
# разводит их одинаково хорошо.
MIN_PROPER_SHARE = 0.25

# --- статусы ---------------------------------------------------------------

CANDIDATE = "candidate"
APPROVED = "approved"
REJECTED = "rejected"

AUTO = "auto"
MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class Candidate:
    """Предложение статистики. `runner_up` — счёт второго кандидата на тот же
    английский термин: по нему в окне видно, почему предложение прошло отбор."""
    en_term: str
    ru_term: str
    score: float
    pairs: int
    runner_up: float


@dataclass(frozen=True, slots=True)
class Entry:
    """Строка глоссария как она лежит в базе."""
    id: int
    en_term: str
    ru_term: str
    status: str
    score: float | None
    pairs: int | None
    note: str
    origin: str
    updated_at: str | None


# --- разбор текста ---------------------------------------------------------


def _en_tokens(text: str) -> set[str]:
    """Английские слова строки: без разметки, без служебных, без коротких."""
    words = WORD.findall(markup.strip_markup(text).lower())
    return {w for w in words
            if w not in STOP_WORDS and len(w) >= MIN_TERM_LEN}


# Чем кончается то, что стоит перед словом, если слово открывает фразу. Точка,
# двоеточие и перевод строки — очевидны; кавычки и тире добавлены потому, что в
# локализации Paradox реплика сплошь и рядом начинается прямо с них.
#
# Типографские кавычки здесь не для красоты: описания AGOT — это цитаты из книг,
# и открываются они `“`, а не `"`. Пока их не было в списке, `“Though the…` и
# `“After the Doom…` считались серединой фразы, то есть `Though` и `After`
# проходили как имена собственные и держались в верху списка на пяти сотнях пар.
_SENTENCE_END = ('.', '!', '?', ':', ';', '\n', '"', "'", '«', '»',
                 '“', '”', '‘', '’',      # “ ” ‘ ’
                 '—', '–', '-', '(', '[')


def _proper_nouns(text: str) -> set[str]:
    """Слова, написанные с заглавной **не в начале фразы**.

    Это и есть признак имени собственного, отделяющий `Targaryen` от `Now`.
    Оба попадаются с заглавной, но `Now` — только там, где с заглавной пишется
    что угодно, а `Targaryen` стоит с большой буквы посреди предложения.

    Мера грубая и в обе стороны неточная: заголовок, набранный капслоком, сюда
    не попадёт, а первое слово после сокращения попадёт зря. Но на живом
    корпусе AGOT она убирает из верха списка `Now`, `Though`, `After`, `Even`
    и `Perhaps`, не тронув ни одного настоящего имени, — а разбирать список
    руками переводчику, и цена ошибки здесь не выше одной лишней строки.
    """
    clean = markup.strip_markup(text)
    words = WORD.findall(clean)
    if not words:
        return set()

    # Title Case не свидетельствует ни о чём. Названия черт, кнопки и заголовки
    # событий Paradox пишет с заглавной **каждое** слово, и `Now` в «The Long
    # Night Is Now» выглядит именем собственным ровно так же, как `Targaryen`.
    #
    # Пороги подобраны так, чтобы не задеть обычное предложение: «House
    # Targaryen rises» — три слова, два с заглавной, и это не Title Case, а имя
    # рода посреди фразы. Требуем и длины от четырёх слов, и трёх четвертей
    # заглавных: «The Long Night Is Now» даёт пять из пяти и отсекается, а
    # короткая фраза с именем — нет.
    capitalised = sum(1 for w in words if w[:1].isupper())
    if len(words) >= 4 and capitalised >= len(words) * 0.75:
        return set()

    found: set[str] = set()
    for m in WORD.finditer(clean):
        if not m.group(0)[:1].isupper():
            continue
        before = clean[:m.start()].rstrip()
        if not before or before.endswith(_SENTENCE_END):
            continue        # начало фразы — с заглавной здесь пишется что угодно
        found.add(m.group(0).lower())
    return found


def _display_form(forms: Counter) -> str:
    """Какую словоформу показать человеку.

    Гнездо `таргариен` собирает `таргариена`, `таргариенов`, `таргариену` — и
    подставлять в перевод любую из них нельзя. Нужна начальная, а морфологии у
    нас нет, поэтому берём **самую короткую из тех, что встречаются заметно**:
    в русском именительный падеж почти всегда короче косвенных, а порог по доле
    отсекает опечатку и обрезок, которые тоже бывают короткими.

    Порог именно доля, а не число: гнездо бывает и из четырёх вхождений, и из
    четырёхсот.
    """
    total = sum(forms.values())
    common = [w for w, n in forms.items() if n >= total * MIN_FORM_SHARE]
    return min(common or list(forms), key=lambda w: (len(w), w))


def _ru_stem(word: str) -> str:
    """Основа русского слова — срезом окончания из таблицы выше.

    Не морфологический анализ и не претендует: задача здесь одна — чтобы
    `таргариен`, `таргариена` и `таргариенов` попали в одно гнездо и сложили
    свой вес, а не разделили его на три.
    """
    for ending in _RU_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= MIN_STEM:
            return word[:-len(ending)]
    return word


def _ru_words(text: str) -> list[str]:
    """Русские слова строки в порядке следования — порядок нужен биграммам."""
    return [w for w in WORD.findall(markup.strip_markup(text).lower())
            if w not in RU_STOP_WORDS and len(w) >= MIN_TERM_LEN]


def _ru_keys(text: str) -> tuple[set[str], dict[str, str]]:
    """Ключи русской стороны и как их показывать человеку.

    Ключ — основа (или пара основ для биграммы), показываем же исходные слова:
    «мейстеров» в списке терминов выглядело бы опечаткой, а `мейстер` —
    это то, что переводчик и подтвердит.
    """
    words = _ru_words(text)
    stems = [_ru_stem(w) for w in words]
    keys: set[str] = set()
    surface: dict[str, str] = {}

    for stem, word in zip(stems, words, strict=True):
        keys.add(stem)
        surface.setdefault(stem, word)

    # биграммы соседних слов — ответ на «Kingsguard → Королевская гвардия»
    for i in range(len(stems) - 1):
        key = f"{stems[i]} {stems[i + 1]}"
        keys.add(key)
        surface.setdefault(key, f"{words[i]} {words[i + 1]}")

    return keys, surface


# --- извлечение ------------------------------------------------------------


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
    """Кандидаты в термины по всей доступной памяти переводов.

    Корпус — представление `tm_all`: память самого проекта плюс подключённые
    базы (см. `db.ensure_tm_view` и `project.py`). Отдельно их не разделяем:
    ванильная база и есть главный источник устоявшихся терминов.

    `proper_only` оставляет только слова, встреченные с заглавной посреди
    фразы. Замер на живом корпусе AGOT (45 822 пары): без него верх списка по
    охвату занимают `Now → теперь`, `Though → хотя`, `After → после` — переводы
    верные, но глоссарию мода они не нужны, а разбирать их переводчику руками.

    `progress(done, total)` и `cancelled()` — для прогона из окна: корпус
    бывает в четверть миллиона записей.
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
    """Как английский термин пишется в живом тексте.

    Считаем все написания, а выбирает потом `_display_form`. Английскому
    склонения не мешают, но регистр разъезжается: `maester` в списке выглядел
    бы небрежностью рядом с `Maester`.
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
    """Дайс, отбор лучшего перевода на термин и отсев по отрыву."""
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
        # При равном счёте побеждает более длинный перевод, и это не вкусовщина:
        # у `Kingsguard` биграмма «королевская гвардия» и обе её половины
        # набирают ровно по единице, потому что ходят строго вместе. Оставь
        # порядок на усмотрение сортировки строк — и половина термина победила
        # бы целое по алфавиту.
        hits.sort(key=lambda h: (h[0], len(h[1].split()), h[1]), reverse=True)
        score, r, pairs = hits[0]
        runner_up = _runner_up(hits, r)
        # Отрыв от второго — то, что отличает термин от шаблонного шума. Ноль
        # означает «второго нет вовсе», и это лучший из возможных отрывов.
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
    """Счёт лучшего кандидата, не родственного победителю.

    Униграмма внутри победившей биграммы вторым кандидатом не считается: у
    «королевская гвардия» второй по счёту — «гвардия», и без этой оговорки
    биграмма проваливала бы отбор по отрыву от собственной половины.
    """
    parts = set(winner.split())
    for score, term, _pairs in hits[1:]:
        if parts & set(term.split()):
            continue
        return score
    return 0.0


# --- хранение --------------------------------------------------------------


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"], en_term=row["en_term"], ru_term=row["ru_term"],
        status=row["status"], score=row["score"], pairs=row["pairs"],
        note=row["note"], origin=row["origin"], updated_at=row["updated_at"],
    )


def rows(conn: sqlite3.Connection, *, status: str | None = None,
         search: str = "") -> list[Entry]:
    """Строки глоссария; `status=None` — все."""
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
    # кандидаты — по убыванию уверенности, принятые — по алфавиту: в первом
    # списке работают сверху вниз, во втором ищут глазами
    sql.append("ORDER BY CASE status WHEN 'candidate' THEN -score ELSE 0 END, "
               "pylower(en_term)")
    return [_entry(r) for r in conn.execute(" ".join(sql), params)]


def save_candidates(conn: sqlite3.Connection, found: list[Candidate]) -> int:
    """Записать кандидатов, не трогая уже рассмотренные.

    Пропуск уже известных пар — это и есть память об отказе: принятый термин не
    откатится в кандидаты, а отклонённый не вернётся из мёртвых на следующем
    прогоне. Возвращает число действительно новых строк.

    Сверяем **без учёта регистра**, и одного `ON CONFLICT` тут мало. Написание
    английского термина выбирается по корпусу (`_remember_en_surface`), а
    корпус между прогонами меняется: стоит появиться базе, где `Maester`
    встречается только строчным, — и `UNIQUE(en_term, ru_term)` увидит новую
    пару, а переводчик увидит свой же отклонённый термин во второй раз. Дешевле
    прочитать уже известное и отсеять здесь, чем городить регистронезависимый
    индекс: `lower()` в SQLite не знает кириллицы, а свою функцию в индекс
    класть нельзя — файл перестанет открываться чем-либо, кроме нас.
    """
    known = {(r["en_term"].casefold(), r["ru_term"].casefold())
             for r in conn.execute("SELECT en_term, ru_term FROM glossary")}
    fresh = []
    for c in found:
        key = (c.en_term.casefold(), c.ru_term.casefold())
        if key in known:
            continue
        known.add(key)                  # и от дублей внутри самой пачки
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
    """Термин, заведённый руками, — сразу принятый: его никто не предлагал."""
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
    """Сколько строк в каждом статусе — для нижней полосы окна."""
    found = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM glossary GROUP BY status")}
    return {s: found.get(s, 0) for s in (CANDIDATE, APPROVED, REJECTED)}


# --- подсветка -------------------------------------------------------------


def approved_terms(conn: sqlite3.Connection) -> dict[str, str]:
    """Принятые термины: английский в нижнем регистре → русский, как показывать."""
    return {r["en_term"].lower(): r["ru_term"] for r in conn.execute(
        "SELECT en_term, ru_term FROM glossary WHERE status = 'approved'")}


def build_index(terms: dict[str, str]) -> re.Pattern | None:
    """Скомпилированный поиск всех терминов разом.

    Длинные раньше коротких: иначе `Kings` внутри `Kingsguard` заберёт
    совпадение первым, и подсветится половина термина. Пустой словарь даёт
    None — регулярка из пустой альтернативы совпадает с чем угодно.
    """
    if not terms:
        return None
    ordered = sorted(terms, key=len, reverse=True)
    alternatives = "|".join(re.escape(t) for t in ordered)
    return re.compile(rf"\b(?:{alternatives})\b", re.IGNORECASE)


def find_terms(text: str, index: re.Pattern | None,
               terms: dict[str, str]) -> list[tuple[int, int, str]]:
    """Вхождения принятых терминов: (начало, конец, перевод).

    Куски разметки пропускаются целиком — подчёркивать нутро `[GetTrait…]` или
    имя иконки в `@gold!` незачем, там не проза.
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
