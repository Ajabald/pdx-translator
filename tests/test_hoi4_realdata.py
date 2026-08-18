"""Приёмочный тест на ванильном дереве Hearts of Iron IV.

Второе живое дерево в проекте и первое не от CK3. На нём сверены токены
`§Y…§!` и `£icon`, на нём же настроен пресет «HOI4 · Русский»: числа ниже сняты
с версии игры от 14.08.2026 и стоят здесь затем, чтобы правка регулярки или
правила не разъехалась с реальностью молча.

Путь к папке `localisation` задаётся переменной `PDXT_REALDATA_HOI4`; без неё
тест пропускается — игра есть не на всякой машине.
"""
from __future__ import annotations

import collections

import pytest

from pdxloc.core import markup, mt, paradox_yaml, qa_rules

from conftest import REALDATA_HOI4, hoi4_realdata_available

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not hoi4_realdata_available(),
                       reason="нет ванильного дерева HOI4 (PDXT_REALDATA_HOI4)"),
]

SECTION = "§"      # §
POUND = "£"        # £

EXPECTED_EN_FILES = 206
EXPECTED_EN_ENTRIES = 129_087
EXPECTED_RU_ENTRIES = 148_026     # русское дерево больше: падежные формы


@pytest.fixture(scope="module")
def trees():
    """Разобранные деревья: {ключ: текст} на язык плюс предупреждения парсера."""
    parsed = {}
    warnings: list[str] = []
    for lang in ("english", "russian"):
        entries: dict[str, str] = {}
        files = sorted((REALDATA_HOI4 / lang).rglob("*.yml"))
        for path in files:
            loc = paradox_yaml.parse_file(path)
            warnings.extend(loc.warnings)
            for entry in loc.entries:
                entries[entry.key] = entry.text
        parsed[lang] = (entries, files)
    return parsed, warnings


@pytest.fixture(scope="module")
def pairs(trees):
    """Пары «оригинал — перевод» по совпадающим ключам."""
    parsed, _ = trees
    en, ru = parsed["english"][0], parsed["russian"][0]
    return [(text, ru[key]) for key, text in en.items() if key in ru]


# --- разбор --------------------------------------------------------------


def test_the_parser_reads_vanilla_hoi4_without_a_single_complaint(trees) -> None:
    """Формат у серии общий — и парсер, написанный под CK3, это подтверждает."""
    parsed, warnings = trees
    assert warnings == []
    assert len(parsed["english"][1]) == EXPECTED_EN_FILES
    assert len(parsed["english"][0]) == EXPECTED_EN_ENTRIES
    assert len(parsed["russian"][0]) == EXPECTED_RU_ENTRIES


def test_the_russian_tree_only_adds_keys(trees) -> None:
    """Ни один английский ключ не потерян; лишние — русские падежные формы.

    Их 18 939, и живут они в `RU_LOCKEYS_l_russian.yml` и файлах `WUW_*`,
    которых в английском дереве нет вовсе. Сканер кладёт такие в архив
    (`legacy_translations`).
    """
    parsed, _ = trees
    en, ru = parsed["english"][0], parsed["russian"][0]
    assert set(en) - set(ru) == set()
    extra = set(ru) - set(en)
    assert len(extra) == 18_939
    assert sum(1 for key in extra if "_RU_" in key or key.endswith("_RU_lower")) > 15_000


# --- разметка ------------------------------------------------------------


def test_every_colour_and_icon_is_covered_by_the_registry(trees) -> None:
    """После вычистки разметки не должно остаться ни § , ни £.

    Голый символ значит, что токен разобран наполовину: в машинный перевод
    уедет обрубок, а сравнение длин посчитает разметку текстом.
    """
    en = trees[0]["english"][0]
    leftovers = [text for text in en.values()
                 if SECTION in markup.strip_markup(text)
                 or POUND in markup.strip_markup(text)]
    assert leftovers == []


def test_nothing_of_the_markup_reaches_the_translator(trees) -> None:
    en = trees[0]["english"][0]
    for text in en.values():
        shielded, mapping = mt.shield_tags(text)
        assert SECTION not in shielded and POUND not in shielded
        assert mt.unshield(shielded, mapping) == text


def test_how_much_colour_and_icon_there_is(trees) -> None:
    """Цифры из шапки `core/markup.py` — здесь они и проверяются."""
    en = trees[0]["english"][0]
    counts = collections.Counter()
    for text in en.values():
        for token_id in ("color_open", "color_close", "icon_pound", "icon_var"):
            if markup.pattern(token_id).search(text):
                counts[token_id] += 1
    assert counts["color_open"] == 11_290
    assert counts["color_close"] == 11_294
    assert counts["icon_pound"] + counts["icon_var"] > 1_200


# --- проверки ------------------------------------------------------------


def _codes(rules, pairs) -> collections.Counter:
    found = collections.Counter()
    for en_text, ru_text in pairs:
        for code in rules.check(en_text, ru_text):
            found[code] += 1
    return found


def test_the_builtin_ruleset_is_noisy_on_russian_hoi4(pairs) -> None:
    """Встроенный набор считает приём игры ошибкой — отсюда и пресет."""
    found = _codes(qa_rules.resolve(locale="ru"), pairs)
    assert found["brackets_mismatch"] == 5_028
    assert found["glued_markup"] == 1_249


def test_the_hoi4_preset_leaves_only_the_suspicious(pairs) -> None:
    """5 028 → 746 и 1 249 → 5. Остальное — кандидаты в настоящие ошибки.

    Общее число здесь больше, чем в примечании к пресету (9 464 против 5 269):
    там замер по строкам проекта, а тут — по всему дереву, вместе с теми, что
    проект пометил бы «нечего переводить». Разница целиком в `same_as_en`:
    названия техники и аббревиатуры переводить и не нужно.
    """
    found = _codes(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru"), pairs)
    assert found["brackets_mismatch"] == 746
    assert found["glued_markup"] == 5
    assert sum(found.values()) == 9_464
    assert found["same_as_en"] == 8_181


def test_the_colour_rule_is_quiet_on_a_professional_translation(pairs) -> None:
    """25 расхождений по цвету на 124 893 строки — правило годится включённым."""
    found = _codes(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru"), pairs)
    assert found["color_mismatch"] == 25


def test_paradox_did_lose_variables(pairs) -> None:
    """326 строк, где подстановка потерялась или подменена другой.

    Ради таких находок правила и написаны: `$JAP_zaibatsu_faction$` в переводе
    стал `$JAP_naval_faction$` — в игре это видно как чужое требование.
    """
    found = _codes(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru"), pairs)
    assert found["dollar_mismatch"] == 326
