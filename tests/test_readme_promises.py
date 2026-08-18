"""README обещает числа — код обязан их подтверждать.

Правило бэклога: «возможность считается сделанной, когда она названа в README».
У правила есть обратная сторона, на которой уже обожглись: названное в README
устаревает молча. Ошибки не возникает ни одной — просто в описании написано
«15 встроенных правил», а их семнадцать, и человек, выбирающий инструмент,
читает неправду.

Числа тут проверяются те, что **меняются вместе с кодом**: правила и наборы
добавляются, и каждый раз забыть про README ничего не стоит. Замеры на живых
корпусах (41 713 замечаний и прочие) сюда не входят намеренно — они привязаны к
дате замера, стоящей рядом в тексте, и устаревать им положено.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pdxloc.core import games, qa_rules

ROOT = Path(__file__).resolve().parents[1]
READMES = {"en": ROOT / "README.md", "ru": ROOT / "README.ru.md"}

# сколько чего есть на самом деле
BUILTIN_RULES = len(qa_rules.BUILTIN_RULES)
PRESETS = len(qa_rules.PRESETS)

# «17 built-in rules» / «17 встроенных правил»
RULES_RE = {
    "en": re.compile(r"\*\*(\d+) built-in rules"),
    "ru": re.compile(r"\*\*(\d+) встроенных правил"),
}
# «Seven ready-made sets» / «Семь готовых наборов» — число словом
PRESETS_RE = {
    "en": re.compile(r"\*\*(\w+) ready-made sets"),
    "ru": re.compile(r"\*\*(\w+) готовых наборов"),
}
WORDS = {
    "en": {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10},
    "ru": {"три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
           "девять": 9, "десять": 10},
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
}


@pytest.mark.parametrize("lang", sorted(READMES))
def test_game_count_matches_the_registry(lang: str) -> None:
    """CK2 появилась 2026-08-15 и не была названа ни в одном README до 08-19."""
    found = GAMES_RE[lang].search(text(lang))
    assert found, f"в {READMES[lang].name} не нашлось обещания про число игр"
    said = WORDS[lang].get(found.group(1).lower())
    assert said == len(games.GAMES), (
        f"{READMES[lang].name} обещает игр: {said}, а в реестре {len(games.GAMES)}")


@pytest.mark.parametrize("lang", sorted(READMES))
def test_every_game_is_named_in_the_readme(lang: str) -> None:
    """Игра, о которой не сказано, для пользователя не существует.

    Пробелы схлопываем: README свёрстан под 80 колонок, и «Europa Universalis
    IV» законно разъезжается по двум строкам. Перенос — не смысл.
    """
    said = " ".join(text(lang).split())
    missing = [g for g in games.ORDER if games.title(g) not in said]
    assert not missing, f"{READMES[lang].name}: игры не названы — {missing}"


@pytest.mark.parametrize("lang", sorted(READMES))
def test_every_game_preset_is_named_in_the_readme(lang: str) -> None:
    """Игровой набор, о котором не сказано, для пользователя не существует.

    Три набора (HOI4, CK2, Stellaris) появились вместе с играми, а README
    продолжал перечислять четыре штуки времён одной CK3 — и обещание «семь игр
    серии» этим себе же противоречило.

    Проверяются только наборы вида «игра_язык»: их имя содержит слаг игры,
    который в тексте стоит буквально. У `strict`, `quiet` и `custom` имя
    человеческое и в каждом языке своё («Строгий», «Только поломки»), сверять
    его с идентификатором нечестно — их считает тест выше, по числу.
    """
    said = text(lang).lower()
    game_presets = [p for p in qa_rules.PRESETS if "_" in p]
    assert game_presets, "игровых наборов не осталось — проверка потеряла смысл"
    missing = [p for p in game_presets if p.split("_")[0] not in said]
    assert not missing, (
        f"{READMES[lang].name}: игровые наборы не названы — {missing}")
