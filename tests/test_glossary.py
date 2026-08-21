"""Extracting terms: the arithmetic, the word forms, the bigrams, the noise.

The corpora here are put together by hand and are small on purpose — each checks
exactly one of the three problems the measurement on a live corpus laid bare (see
the head of `core/glossary.py`). The numbers on live trees are pinned down by
`test_glossary_realdata.py`.
"""
from __future__ import annotations

from collections import Counter

import pytest

from pdxloc.core import glossary
from pdxloc.db import get_connection


@pytest.fixture
def conn(tmp_path):
    """A project with an empty memory: we shall write straight into tm_entries."""
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


# --- parsing the text ------------------------------------------------------


def test_stop_words_and_markup_are_not_terms():
    """Stop words and markup do not count: they are in every single row."""
    tokens = glossary._en_tokens("The [GetTitle] of $NAME$ has @gold! and the Wall")
    assert "wall" in tokens
    assert "the" not in tokens and "has" not in tokens
    # nothing out of the markup seeped through
    assert "gettitle" not in tokens and "name" not in tokens and "gold" not in tokens


@pytest.mark.parametrize("word", ["таргариен", "таргариена", "таргариенов",
                                  "таргариенам", "таргариены"])
def test_russian_word_forms_share_one_stem(word):
    """The word forms are obliged to add their weight up, not to split it five ways."""
    assert glossary._ru_stem(word) == "таргариен"


def test_short_words_keep_their_stem():
    """A stem shorter than MIN_STEM is not cut: «граф» and «град» would stick together."""
    assert glossary._ru_stem("граф") == "граф"
    assert glossary._ru_stem("дом") == "дом"


def test_bigrams_are_counted_next_to_single_words():
    keys, surface = glossary._ru_keys("Королевская гвардия")
    assert "королевск гвард" in keys          # a bigram of stems
    assert surface["королевск гвард"] == "королевская гвардия"


# --- the arithmetic --------------------------------------------------------


def test_dice_score_is_two_over_the_sum(conn):
    """A term met exactly together with its translation gives one."""
    fill(conn, [("The Maester waits", "Мейстер ждёт"),
                ("A Maester speaks", "Мейстер говорит"),
                ("Maester arrives now", "Мейстер приходит")])
    found = {c.en_term.lower(): c for c in glossary.extract(conn, min_pairs=3)}
    assert found["maester"].ru_term == "мейстер"
    assert found["maester"].score == pytest.approx(1.0)
    assert found["maester"].pairs == 3


def test_rare_co_occurrence_is_below_the_floor(conn):
    """Two pairs are not statistics: MIN_PAIRS cuts off a chance neighbourhood."""
    fill(conn, [("The Maester waits", "Мейстер ждёт"),
                ("A Maester speaks", "Мейстер говорит")])
    assert glossary.extract(conn, min_pairs=3) == []
    assert glossary.extract(conn, min_pairs=2) != []


def test_capitalised_spelling_wins_for_display(conn):
    """A term is shown as it is written in the text, not in lower case.

    `proper_only` is off on purpose: what is checked here is the choice of
    spelling and not the selection of proper nouns — and the capital here stands
    at the start of a phrase, that is, by our mark the word is no proper noun.
    """
    fill(conn, [("the maester waits", "мейстер ждёт"),
                ("a maester speaks", "мейстер говорит"),
                ("Maester arrives now", "мейстер приходит")])
    found = glossary.extract(conn, min_pairs=3, proper_only=False)
    assert [c.en_term for c in found if c.en_term.lower() == "maester"] == ["Maester"]


# --- the three known problems ----------------------------------------------


def test_word_forms_do_not_split_the_score(conn):
    """`таргариен` and `таргариенов` are one nest, and its weight is the full one.

    Without grouping by the stem each form would collect its half and both would
    fall through the threshold.
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
    """`Kingsguard` is translated by two words, and both have to be offered."""
    fill(conn, [("The Kingsguard stands", "Королевская гвардия стоит"),
                ("Kingsguard oath taken", "Королевская гвардия принесла клятву"),
                ("A Kingsguard knight", "Рыцарь Королевской гвардии"),
                ("Kingsguard white cloaks", "Белые плащи Королевской гвардии")])
    found = {c.en_term.lower(): c for c in glossary.extract(conn, min_pairs=4)}
    assert "kingsguard" in found
    assert len(found["kingsguard"].ru_term.split()) == 2


def test_template_noise_is_rejected_for_lack_of_a_gap(conn):
    """A word whose "translation" cannot be told from its neighbour is not offered.

    Here `Valyrian` and `Essos` travel strictly as a pair, and the statistics are
    equally happy with either variant. A real term does not behave like that — it
    has one translation and a noticeable gap over the runner-up.
    """
    fill(conn, [("Valyrian steel from Essos", "Валирийская сталь из Эссоса"),
                ("Valyrian roads of Essos", "Валирийские дороги Эссоса"),
                ("Valyrian ruins in Essos", "Валирийские руины в Эссосе"),
                ("Valyrian fire of Essos", "Валирийский огонь Эссоса")])
    found = {c.en_term.lower() for c in glossary.extract(conn, min_pairs=4, gap=1.3)}
    # without demanding a gap, the same corpus of candidates gives
    loose = {c.en_term.lower() for c in glossary.extract(conn, min_pairs=4, gap=0)}
    assert loose - found, "порог отрыва обязан что-то отсеять на таком корпусе"


def test_a_bigram_is_not_its_own_runner_up(conn):
    """Half of a winning bigram does not count as the runner-up.

    Otherwise «королевская гвардия» would fail the gap test against «гвардия»,
    that is, against itself.
    """
    hits = [(0.9, "королевск гвард", 4), (0.85, "гвард", 4), (0.2, "рыцар", 4)]
    assert glossary._runner_up(hits, "королевск гвард") == 0.2


def test_runner_up_is_zero_when_there_is_no_rival():
    assert glossary._runner_up([(0.9, "мейстер", 3)], "мейстер") == 0.0


# --- a proper noun against a frequent word ---------------------------------
#
# Everything in this block is taken off the live AGOT corpus (45,822 pairs): each
# check closes a hole through which an ordinary word crawled to the top of the list.


def test_a_word_capitalised_mid_sentence_is_a_proper_noun():
    assert "targaryen" in glossary._proper_nouns("The heir of Targaryen blood")


def test_a_word_capitalised_only_at_the_start_is_not():
    assert glossary._proper_nouns("Now the war begins") == set()


def test_title_case_is_no_evidence_at_all():
    """«The Long Night Is Now» makes a proper noun of every word.

    Trait names, buttons and event titles Paradox writes exactly like that, and
    without this proviso `Now` passed as a name.
    """
    assert glossary._proper_nouns("The Long Night Is Now") == set()


def test_a_typographic_quote_opens_a_sentence():
    """AGOT descriptions are quotations from books, and they open with `“`, not `\"`.

    While the quote did not count as the end of a phrase, `Though` and `After`
    held the top of the list on five hundred pairs each.
    """
    found = glossary._proper_nouns("“Though Norvos stands, its walls are old")
    assert "though" not in found
    assert "norvos" in found        # while a real name next to it is in place


def test_one_sighting_does_not_make_a_proper_noun(conn):
    """The mark is a share, not a fact.

    On the live corpus `Now` stood mid-phrase in two rows out of 45,822 (there,
    where a line break collapsed into a space), and those two were enough for the
    word to land on the allow-list forever, and all 804 of its pairs with it.
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


# --- the word form on display ----------------------------------------------


def test_the_nominative_wins_over_oblique_cases():
    """A translator is not going to paste «таргариена» into a translation.

    The nest gathers every case; what has to be shown is the base form, and
    morphology we have none — we take the shortest of the noticeable ones.
    """
    forms = Counter({"таргариена": 40, "таргариенов": 30, "таргариен": 25})
    assert glossary._display_form(forms) == "таргариен"


def test_a_rare_short_form_is_not_trusted():
    """A truncation and a typo are short as well — the share threshold quiets them."""
    forms = Counter({"мейстер": 100, "мей": 1})
    assert glossary._display_form(forms) == "мейстер"


def test_a_capitalised_spelling_wins_a_tie():
    assert glossary._display_form(Counter({"maester": 5, "Maester": 5})) == "Maester"


# --- highlighting ----------------------------------------------------------


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
    """The argument of a scripted call is not prose, there is nothing to underline.

    The case is not invented and a word boundary does not close it: in
    `[GetTrait('maester').GetName]` the term is framed by quotes, that is, `\\b`
    matches on both sides. Only skipping the pieces of markup whole saves us.
    """
    terms = {"maester": "мейстер"}
    index = glossary.build_index(terms)
    assert glossary.find_terms("[GetTrait('maester').GetName] speaks", index, terms) == []
    # while a live word next to markup is found
    found = glossary.find_terms("[GetName] the Maester", index, terms)
    assert len(found) == 1


def test_partial_words_are_not_terms():
    terms = {"maester": "мейстер"}
    index = glossary.build_index(terms)
    assert glossary.find_terms("Maesterly grandmaester", index, terms) == []


def test_empty_glossary_builds_no_index():
    """An empty alternation in a regex would match anything at all."""
    assert glossary.build_index({}) is None
    assert glossary.find_terms("anything", None, {}) == []
