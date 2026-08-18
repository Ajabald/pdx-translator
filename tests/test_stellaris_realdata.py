"""Приёмочный тест на ванильном дереве Stellaris.

Третья живая игра в проекте и первая, у которой грамматика живёт прямо в
строке: с версии 3.6 Stellaris склоняет генерируемые имена тегами `&!fem` и
вариантами `|||gen:` (описано в `localisation/99_README_GRAMMAR.txt`). Числа
сняты с установленной игры; стоят здесь затем, чтобы правка реестра или правил
не разъехалась с реальностью молча.

Путь — переменная `PDXT_REALDATA_STELLARIS` (папка `localisation` игры).
"""
from __future__ import annotations

import collections
import re

import pytest

from pdxloc.core import loc_formats, markup, mt, qa_rules

from conftest import REALDATA_STELLARIS, stellaris_realdata_available

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not stellaris_realdata_available(),
                       reason="нет дерева Stellaris (PDXT_REALDATA_STELLARIS)"),
]

EXPECTED_EN_FILES = 231
EXPECTED_EN_ENTRIES = 149_217
EXPECTED_RU_FILES = 233
EXPECTED_RU_ENTRIES = 150_899      # 12 ключей задублированы переводчиком


@pytest.fixture(scope="module")
def trees():
    fmt = loc_formats.get(loc_formats.YML)
    parsed = {}
    warnings: list[str] = []
    for lang in ("english", "russian"):
        files = fmt.files(REALDATA_STELLARIS / lang, lang)
        entries: dict[str, str] = {}
        count = 0
        for path in files:
            loc = fmt.parse_file(path, language=lang)
            warnings.extend(loc.warnings)
            count += len(loc.entries)
            for entry in loc.entries:
                entries[entry.key] = entry.text
        parsed[lang] = (files, entries, count)
    return parsed, warnings


@pytest.fixture(scope="module")
def pairs(trees):
    parsed, _ = trees
    en, ru = parsed["english"][1], parsed["russian"][1]
    return [(text, ru[key]) for key, text in en.items() if key in ru and text and ru[key]]


# --- разбор --------------------------------------------------------------


def test_the_tree_is_recognised_and_parsed(trees) -> None:
    """Формат опознаётся по содержимому, а разбор идёт без единой жалобы."""
    assert loc_formats.detect(REALDATA_STELLARIS / "english") == loc_formats.YML

    parsed, warnings = trees
    assert warnings == []
    assert len(parsed["english"][0]) == EXPECTED_EN_FILES
    assert parsed["english"][2] == EXPECTED_EN_ENTRIES
    assert len(parsed["russian"][0]) == EXPECTED_RU_FILES
    assert parsed["russian"][2] == EXPECTED_RU_ENTRIES


def test_the_translation_is_complete_and_adds_case_forms(trees) -> None:
    """Ни одного английского ключа без пары; лишние — падежные формы."""
    parsed, _ = trees
    en, ru = parsed["english"][1], parsed["russian"][1]
    assert set(en) - set(ru) == set()
    assert len(set(ru) - set(en)) == 1_670


# --- грамматическая система 3.6 -----------------------------------------


def test_how_much_grammar_there_is(trees) -> None:
    """Система заточена под языки с падежами — по числам это и видно."""
    parsed, _ = trees
    counts = {}
    for lang in ("english", "russian"):
        texts = parsed[lang][1].values()
        counts[lang] = (
            sum(1 for t in texts if markup.pattern("grammar_variant").search(t)),
            sum(1 for t in texts if markup.pattern("grammar_tags").search(t)),
        )
    assert counts["russian"] == (6_327, 2_278)
    assert counts["english"] == (463, 39)


def test_grammar_never_reaches_the_translator(trees) -> None:
    """`энергия&!fem|||gen:энергии` уезжал в переводчик как есть."""
    parsed, _ = trees
    for text in parsed["russian"][1].values():
        shielded, mapping = mt.shield_tags(text)
        assert "&!" not in shielded and "|||" not in shielded
        assert mt.unshield(shielded, mapping) == text


def test_markup_of_the_other_games_covers_stellaris(trees) -> None:
    """`§`, `£` и `$…$` уже были в реестре — здесь они и проверяются.

    Двенадцать строк из 149 217 остаются с голым символом, и ни одна не по
    нашей вине:

    * десять — забытые Paradox заглушки `§_TODO CD§!` и `§_Not working…`;
      `§_` не цвет, и делать вид, что это разметка, значит прятать чужой
      недосмотр;
    * `£unity £§YUnity§!` — лишняя `£` в тексте обучения, тоже опечатка;
    * `£leader_skill|$LEVEL$£` — иконка, имя которой собирается из переменной
      с флагом; строка одна на всё дерево, и менять ради неё регулярку дороже,
      чем оставить как есть.
    """
    parsed, _ = trees
    leftovers = [t for t in parsed["english"][1].values()
                 if "§" in markup.strip_markup(t) or "£" in markup.strip_markup(t)]
    assert len(leftovers) == 12
    assert sum(1 for t in leftovers if "§_" in t) == 10
    assert sum(1 for t in leftovers if re.search(r"£[a-z_]+\|\$", t)) == 1


# --- проверки ------------------------------------------------------------


def _codes(rules, pairs) -> collections.Counter:
    found = collections.Counter()
    for en_text, ru_text in pairs:
        for code in rules.check(en_text, ru_text):
            found[code] += 1
    return found


def test_the_preset_takes_the_edge_off(pairs) -> None:
    assert len(pairs) == 148_751
    builtin = _codes(qa_rules.resolve(locale="ru"), pairs)
    assert sum(builtin.values()) == 32_969
    assert builtin["same_as_en"] == 17_156
    assert builtin["brackets_mismatch"] == 7_973

    preset = _codes(qa_rules.resolve({"preset": "stellaris_ru"}, locale="ru"), pairs)
    assert sum(preset.values()) == 29_525
    assert preset["brackets_mismatch"] == 5_328
    assert preset["dollar_mismatch"] == 4_689


def test_paradox_lost_gender_tags(pairs) -> None:
    """502 строки, где тег рода потерялся при переводе.

    `Agrippa&!masc` → `Агриппа`: в игре это имя перестанет считаться мужским, и
    просклоняется неверно всё, куда оно подставится.
    """
    preset = _codes(qa_rules.resolve({"preset": "stellaris_ru"}, locale="ru"), pairs)
    assert preset["grammar_mismatch"] == 502
