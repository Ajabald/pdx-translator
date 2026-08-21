"""The README promises numbers — the code is obliged to confirm them.

A rule of the backlog: «a capability counts as done once it is named in the
README». The rule has a reverse side we have already been burned by: what is
named in the README goes stale silently. Not a single error arises — it is simply
that the description says «15 built-in rules» while there are seventeen, and the
person choosing a tool reads an untruth.

The numbers checked here are the ones that **change together with the code**:
rules and sets get added, and forgetting about the README each time costs
nothing. The measurements on live corpora (41,713 remarks and the rest) are
deliberately not here — they are tied to the date of the measurement standing
next to them in the text, and going stale is proper to them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pdxloc.core import games, qa_rules

ROOT = Path(__file__).resolve().parents[1]
READMES = {"en": ROOT / "README.md", "ru": ROOT / "README.ru.md",
           "zh": ROOT / "README.zh-CN.md"}

# how much of what there actually is
BUILTIN_RULES = len(qa_rules.BUILTIN_RULES)
PRESETS = len(qa_rules.PRESETS)

# «17 built-in rules» / «17 встроенных правил»
RULES_RE = {
    "en": re.compile(r"\*\*(\d+) built-in rules"),
    "ru": re.compile(r"\*\*(\d+) встроенных правил"),
    # In Chinese the measure word stands by the number and not by the noun, and
    # the number is written in figures — as in all technical prose in that language.
    "zh": re.compile(r"\*\*(\d+) 条内置规则"),
}
# «Seven ready-made sets» / «Семь готовых наборов» — the number as a word
PRESETS_RE = {
    "en": re.compile(r"\*\*(\w+) ready-made sets"),
    "ru": re.compile(r"\*\*(\w+) готовых наборов"),
    # A non-greedy capture: the characters of the number and of the measure word
    # stand right together, and a greedy `\w+` would swallow the whole bunch.
    "zh": re.compile(r"\*\*(\w+?)套现成的规则集"),
}
WORDS = {
    "en": {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10},
    "ru": {"три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
           "девять": 9, "десять": 10},
    "zh": {"三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
           "九": 9, "十": 10},
}


def text(lang: str) -> str:
    return READMES[lang].read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", sorted(READMES))
def test_builtin_rule_count_matches_the_registry(lang: str) -> None:
    found = RULES_RE[lang].search(text(lang))
    assert found, f"в {READMES[lang].name} не нашлось обещания про встроенные правила"
    assert int(found.group(1)) == BUILTIN_RULES, (
        f"{READMES[lang].name} обещает {found.group(1)} встроенных правил, "
        f"а в реестре {BUILTIN_RULES}")


@pytest.mark.parametrize("lang", sorted(READMES))
def test_preset_count_matches_the_registry(lang: str) -> None:
    found = PRESETS_RE[lang].search(text(lang))
    assert found, f"в {READMES[lang].name} не нашлось обещания про наборы правил"
    said = WORDS[lang].get(found.group(1).lower())
    assert said is not None, (
        f"{READMES[lang].name}: число наборов записано словом «{found.group(1)}», "
        f"которого нет в таблице — допишите его в WORDS")
    assert said == PRESETS, (
        f"{READMES[lang].name} обещает наборов: {said}, а в реестре {PRESETS}")


GAMES_RE = {
    "en": re.compile(r"\*\*(\w+) games of the series"),
    "ru": re.compile(r"\*\*(\w+) игр серии"),
    "zh": re.compile(r"\*\*系列中的(\w+?)款游戏"),
}


@pytest.mark.parametrize("lang", sorted(READMES))
def test_game_count_matches_the_registry(lang: str) -> None:
    """CK2 appeared on 2026-08-15 and was named in no README until 08-19."""
    found = GAMES_RE[lang].search(text(lang))
    assert found, f"в {READMES[lang].name} не нашлось обещания про число игр"
    said = WORDS[lang].get(found.group(1).lower())
    assert said == len(games.GAMES), (
        f"{READMES[lang].name} обещает игр: {said}, а в реестре {len(games.GAMES)}")


@pytest.mark.parametrize("lang", sorted(READMES))
def test_every_game_is_named_in_the_readme(lang: str) -> None:
    """A game that is not spoken of does not exist for the user.

    We collapse the spaces: the README is set to 80 columns, and «Europa
    Universalis IV» lawfully comes apart over two lines. A line break is not a
    meaning.
    """
    said = " ".join(text(lang).split())
    missing = [g for g in games.ORDER if games.title(g) not in said]
    assert not missing, f"{READMES[lang].name}: игры не названы — {missing}"


@pytest.mark.parametrize("lang", sorted(READMES))
def test_every_game_preset_is_named_in_the_readme(lang: str) -> None:
    """A game set that is not spoken of does not exist for the user.

    Three sets (HOI4, CK2, Stellaris) appeared together with the games, while the
    README went on listing four of them from the times of CK3 alone — and the
    promise of «seven games of the series» thereby contradicted itself.

    Only the sets named after a game are checked: since 0.1.2 their name is the
    slug of the game, and that stands in the text literally. `strict`, `quiet` and
    `custom` have a human name, different in every language («Строгий», «Только
    поломки»), and checking it against the identifier would be dishonest — those
    are counted by the test above, by number.
    """
    said = text(lang).lower()
    game_presets = [p for p in qa_rules.PRESETS if p in games.ORDER]
    assert game_presets, "игровых наборов не осталось — проверка потеряла смысл"
    missing = [p for p in game_presets if p.split("_")[0] not in said]
    assert not missing, (
        f"{READMES[lang].name}: игровые наборы не названы — {missing}")
