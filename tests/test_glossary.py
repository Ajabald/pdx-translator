"""Извлечение терминов: арифметика, словоформы, биграммы, шум.

Корпуса здесь собраны руками и малы намеренно — каждый проверяет ровно одну
из трёх проблем, которые вскрыл замер на живом корпусе (см. шапку
`core/glossary.py`). Числа на живых деревьях закрепляет
`test_glossary_realdata.py`.
"""
from __future__ import annotations

from collections import Counter

import pytest

from pdxloc.core import glossary
from pdxloc.db import get_connection


@pytest.fixture
def conn(tmp_path):
    """Проект с пустой памятью: писать будем прямо в tm_entries."""
    c = get_connection(tmp_path / "p.sqlite3")
    c.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1,'p','e','r')")
    c.commit()
    yield c
    c.close()


def fill(conn, pairs: list[tuple[str, str]]) -> None:
    conn.executemany(
        "INSERT INTO tm_entries (en_hash, en_text, ru_text) VALUES (?, ?, ?)",
        [(f"h{i}", en, ru) for i, (en, ru) in enumerate(pairs)])
    conn.commit()


# --- разбор текста ---------------------------------------------------------


def test_stop_words_and_markup_are_not_terms():
    """Служебные слова и разметка в счёт не идут: они есть в каждой строке."""
    tokens = glossary._en_tokens("The [GetTitle] of $NAME$ has @gold! and the Wall")
    assert "wall" in tokens
    assert "the" not in tokens and "has" not in tokens
    # ничего из разметки не просочилось
    assert "gettitle" not in tokens and "name" not in tokens and "gold" not in tokens


@pytest.mark.parametrize("word", ["таргариен", "таргариена", "таргариенов",
                                  "таргариенам", "таргариены"])
def test_russian_word_forms_share_one_stem(word):
    """Словоформы обязаны сложить вес, а не разделить его на пять."""
    assert glossary._ru_stem(word) == "таргариен"


def test_short_words_keep_their_stem():
    """Основа короче MIN_STEM не режется: иначе «граф» и «град» слиплись бы."""
    assert glossary._ru_stem("граф") == "граф"
    assert glossary._ru_stem("дом") == "дом"


def test_bigrams_are_counted_next_to_single_words():
    keys, surface = glossary._ru_keys("Королевская гвардия")
    assert "королевск гвард" in keys          # биграмма основ
    assert surface["королевск гвард"] == "королевская гвардия"


# --- арифметика ------------------------------------------------------------


def test_dice_score_is_two_over_the_sum(conn):
    """Термин, встречающийся ровно вместе со своим переводом, даёт единицу."""
    fill(conn, [("The Maester waits", "Мейстер ждёт"),
                ("A Maester speaks", "Мейстер говорит"),
                ("Maester arrives now", "Мейстер приходит")])
    found = {c.en_term.lower(): c for c in glossary.extract(conn, min_pairs=3)}
    assert found["maester"].ru_term == "мейстер"
    assert found["maester"].score == pytest.approx(1.0)
    assert found["maester"].pairs == 3


def test_rare_co_occurrence_is_below_the_floor(conn):
    """Две пары — не статистика: MIN_PAIRS отсекает случайное соседство."""
    fill(conn, [("The Maester waits", "Мейстер ждёт"),
                ("A Maester speaks", "Мейстер говорит")])
    assert glossary.extract(conn, min_pairs=3) == []
    assert glossary.extract(conn, min_pairs=2) != []


def test_capitalised_spelling_wins_for_display(conn):
    """Термин показывается так, как его пишут в тексте, а не в нижнем регистре.

    `proper_only` выключен намеренно: здесь проверяется выбор написания, а не
    отбор имён собственных, — а заглавная тут стоит в начале фразы, то есть
    именем собственным слово по нашему признаку не является.
    """
    fill(conn, [("the maester waits", "мейстер ждёт"),
                ("a maester speaks", "мейстер говорит"),
                ("Maester arrives now", "мейстер приходит")])
    found = glossary.extract(conn, min_pairs=3, proper_only=False)
    assert [c.en_term for c in found if c.en_term.lower() == "maester"] == ["Maester"]


# --- три известные проблемы ------------------------------------------------


def test_word_forms_do_not_split_the_score(conn):
    """`таргариен` и `таргариенов` — одно гнездо, и вес у него полный.

    Без группировки по основе каждая форма набрала бы свою половину и обе
    провалились бы под порог.
    """
    fill(conn, [("House Targaryen rises", "Дом Таргариенов поднимается"),
                ("Targaryen blood burns", "Кровь Таргариенов горит"),
                ("The Targaryen heir", "Наследник Таргариена"),
                ("Targaryen banners fly", "Знамёна Таргариенов реют")])
    found = {c.en_term.lower(): c for c in glossary.extract(conn, min_pairs=4)}
    assert "targaryen" in found
    assert found["targaryen"].ru_term.startswith("таргариен")
    assert found["targaryen"].pairs == 4


def test_bigram_beats_its_own_halves(conn):
    """`Kingsguard` переводится двумя словами, и предложить надо оба."""
    fill(conn, [("The Kingsguard stands", "Королевская гвардия стоит"),
                ("Kingsguard oath taken", "Королевская гвардия принесла клятву"),
                ("A Kingsguard knight", "Рыцарь Королевской гвардии"),
                ("Kingsguard white cloaks", "Белые плащи Королевской гвардии")])
    found = {c.en_term.lower(): c for c in glossary.extract(conn, min_pairs=4)}
    assert "kingsguard" in found
    assert len(found["kingsguard"].ru_term.split()) == 2


def test_template_noise_is_rejected_for_lack_of_a_gap(conn):
    """Слово, у которого «перевод» неотличим от соседа, не предлагается.

    Здесь `Valyrian` и `Essos` ходят строго парой, и статистика одинаково рада
    обоим вариантам. Настоящий термин так себя не ведёт — у него один перевод
    и заметный отрыв от второго.
    """
    fill(conn, [("Valyrian steel from Essos", "Валирийская сталь из Эссоса"),
                ("Valyrian roads of Essos", "Валирийские дороги Эссоса"),
                ("Valyrian ruins in Essos", "Валирийские руины в Эссосе"),
                ("Valyrian fire of Essos", "Валирийский огонь Эссоса")])
    found = {c.en_term.lower() for c in glossary.extract(conn, min_pairs=4, gap=1.3)}
    # без требования отрыва тот же корпус кандидатов даёт
    loose = {c.en_term.lower() for c in glossary.extract(conn, min_pairs=4, gap=0)}
    assert loose - found, "порог отрыва обязан что-то отсеять на таком корпусе"


def test_a_bigram_is_not_its_own_runner_up(conn):
    """Половина победившей биграммы вторым кандидатом не считается.

    Иначе «королевская гвардия» проваливала бы отбор по отрыву от «гвардии»,
    то есть от самой себя.
    """
    hits = [(0.9, "королевск гвард", 4), (0.85, "гвард", 4), (0.2, "рыцар", 4)]
    assert glossary._runner_up(hits, "королевск гвард") == 0.2


def test_runner_up_is_zero_when_there_is_no_rival():
    assert glossary._runner_up([(0.9, "мейстер", 3)], "мейстер") == 0.0


# --- имя собственное против частого слова ----------------------------------
#
# Всё в этом блоке снято с живого корпуса AGOT (45 822 пары): каждая проверка
# закрывает дыру, через которую в верх списка пролезало обычное слово.


def test_a_word_capitalised_mid_sentence_is_a_proper_noun():
    assert "targaryen" in glossary._proper_nouns("The heir of Targaryen blood")


def test_a_word_capitalised_only_at_the_start_is_not():
    assert glossary._proper_nouns("Now the war begins") == set()


def test_title_case_is_no_evidence_at_all():
    """«The Long Night Is Now» делает именем собственным каждое слово.

    Названия черт, кнопки и заголовки событий Paradox пишет именно так, и без
    этой оговорки `Now` проходил как имя.
    """
    assert glossary._proper_nouns("The Long Night Is Now") == set()


def test_a_typographic_quote_opens_a_sentence():
    """Описания AGOT — цитаты из книг, и открываются они `“`, а не `\"`.

    Пока кавычка не считалась концом фразы, `Though` и `After` держались в
    верху списка на пяти сотнях пар каждое.
    """
    found = glossary._proper_nouns("“Though Norvos stands, its walls are old")
    assert "though" not in found
    assert "norvos" in found        # а настоящее имя рядом — на месте


def test_one_sighting_does_not_make_a_proper_noun(conn):
    """Признак — доля, а не факт.

    На живом корпусе `Now` посреди фразы стоял в двух строках из 45 822 (там,
    где перевод строки схлопнулся в пробел), и этих двух хватало, чтобы слово
    попало в белый список навсегда, а с ним все 804 его пары.
    """
    pairs = [(f"The wall stands now {i}", f"Стена стоит сейчас {i}") for i in range(20)]
    pairs.append(("Beyond the wall  Now, we ride", "За стеной  Сейчас мы едем"))
    fill(conn, pairs)
    found = {c.en_term.lower() for c in glossary.extract(conn, min_pairs=3)}
    assert "now" not in found


def test_the_filter_can_be_switched_off(conn):
    fill(conn, [(f"The war goes on {i}", f"Война продолжается {i}") for i in range(6)])
    assert glossary.extract(conn, min_pairs=3, proper_only=True) == []
    assert glossary.extract(conn, min_pairs=3, proper_only=False) != []


# --- показываемая словоформа -----------------------------------------------


def test_the_nominative_wins_over_oblique_cases():
    """Подставлять «таргариена» в перевод переводчик не станет.

    Гнездо собирает все падежи; показать надо начальную форму, а морфологии у
    нас нет — берём самую короткую из заметных.
    """
    forms = Counter({"таргариена": 40, "таргариенов": 30, "таргариен": 25})
    assert glossary._display_form(forms) == "таргариен"


def test_a_rare_short_form_is_not_trusted():
    """Обрезок и опечатка тоже короткие — их гасит порог по доле."""
    forms = Counter({"мейстер": 100, "мей": 1})
    assert glossary._display_form(forms) == "мейстер"


def test_a_capitalised_spelling_wins_a_tie():
    assert glossary._display_form(Counter({"maester": 5, "Maester": 5})) == "Maester"


# --- подсветка -------------------------------------------------------------


def test_terms_are_found_case_insensitively():
    terms = {"maester": "мейстер"}
    index = glossary.build_index(terms)
    found = glossary.find_terms("A MAESTER and a Maester", index, terms)
    assert [(s, e) for s, e, _ in found] == [(2, 9), (16, 23)]
    assert {ru for _, _, ru in found} == {"мейстер"}


def test_longer_terms_win_over_their_prefixes():
    terms = {"kings": "короли", "kingsguard": "королевская гвардия"}
    index = glossary.build_index(terms)
    found = glossary.find_terms("The Kingsguard rides", index, terms)
    assert [ru for _, _, ru in found] == ["королевская гвардия"]


def test_markup_internals_are_not_highlighted():
    """Аргумент скриптового вызова — не проза, подчёркивать там нечего.

    Случай не выдуманный и границей слова не закрывается: в
    `[GetTrait('maester').GetName]` термин обрамлён кавычками, то есть `\\b`
    совпадает с обеих сторон. Спасает только пропуск кусков разметки целиком.
    """
    terms = {"maester": "мейстер"}
    index = glossary.build_index(terms)
    assert glossary.find_terms("[GetTrait('maester').GetName] speaks", index, terms) == []
    # а живое слово рядом с разметкой — находится
    found = glossary.find_terms("[GetName] the Maester", index, terms)
    assert len(found) == 1


def test_partial_words_are_not_terms():
    terms = {"maester": "мейстер"}
    index = glossary.build_index(terms)
    assert glossary.find_terms("Maesterly grandmaester", index, terms) == []


def test_empty_glossary_builds_no_index():
    """Пустая альтернатива в регулярке совпала бы с чем угодно."""
    assert glossary.build_index({}) is None
    assert glossary.find_terms("anything", None, {}) == []
