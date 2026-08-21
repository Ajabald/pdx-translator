"""An acceptance test on the vanilla tree of Hearts of Iron IV.

The second live tree in the project and the first not from CK3. The tokens
`§Y…§!` and `£icon` were checked on it, and the preset «HOI4 · Русский» was set up
on it too: the numbers below are taken off the game version of 14.08.2026 and
stand here so that an edit of a regex or of a rule does not silently part ways
with reality.

The path to the `localisation` folder is set by the variable
`PDXT_REALDATA_HOI4`; without it the test is skipped — not every machine has the
game.
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
EXPECTED_RU_ENTRIES = 148_026     # the Russian tree is bigger: the case forms


@pytest.fixture(scope="module")
def trees():
    """The parsed trees: {key: text} per language plus the parser warnings."""
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
    """The pairs «original — translation» by the matching keys."""
    parsed, _ = trees
    en, ru = parsed["english"][0], parsed["russian"][0]
    return [(text, ru[key]) for key, text in en.items() if key in ru]


# --- the parsing ---------------------------------------------------------


def test_the_parser_reads_vanilla_hoi4_without_a_single_complaint(trees) -> None:
    """The format is common to the series — and a parser written for CK3 confirms it."""
    parsed, warnings = trees
    assert warnings == []
    assert len(parsed["english"][1]) == EXPECTED_EN_FILES
    assert len(parsed["english"][0]) == EXPECTED_EN_ENTRIES
    assert len(parsed["russian"][0]) == EXPECTED_RU_ENTRIES


def test_the_russian_tree_only_adds_keys(trees) -> None:
    """Not a single English key is lost; the extra ones are Russian case forms.

    There are 18,939 of them, and they live in `RU_LOCKEYS_l_russian.yml` and the
    `WUW_*` files, which the English tree does not have at all. The scanner puts
    such into the archive (`legacy_translations`).
    """
    parsed, _ = trees
    en, ru = parsed["english"][0], parsed["russian"][0]
    assert set(en) - set(ru) == set()
    extra = set(ru) - set(en)
    assert len(extra) == 18_939
    assert sum(1 for key in extra if "_RU_" in key or key.endswith("_RU_lower")) > 15_000


# --- the markup ----------------------------------------------------------


def test_every_colour_and_icon_is_covered_by_the_registry(trees) -> None:
    """After the markup is cleaned out, neither a § nor a £ must be left.

    A bare symbol means the token is parsed by halves: a stump will travel into
    the machine translation, and the comparison of lengths will count markup as
    text.
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
    """The figures from the head of `core/markup.py` — here is where they are checked."""
    en = trees[0]["english"][0]
    counts = collections.Counter()
    for text in en.values():
        for token_id in ("color_open", "color_close", "icon_pound", "icon_var"):
            if markup.pattern(token_id).search(text):
                counts[token_id] += 1
    assert counts["color_open"] == 11_290
    assert counts["color_close"] == 11_294
    assert counts["icon_pound"] + counts["icon_var"] > 1_200


# --- the checks ----------------------------------------------------------


def _codes(rules, pairs) -> collections.Counter:
    found = collections.Counter()
    for en_text, ru_text in pairs:
        for code in rules.check(en_text, ru_text):
            found[code] += 1
    return found


def test_the_builtin_ruleset_is_noisy_on_russian_hoi4(pairs) -> None:
    """The built-in set counts a device of the game as an error — hence the preset."""
    found = _codes(qa_rules.resolve(locale="ru"), pairs)
    assert found["brackets_mismatch"] == 5_028
    assert found["glued_markup"] == 1_249


def test_the_hoi4_preset_leaves_only_the_suspicious(pairs) -> None:
    """5,028 → 746 and 1,249 → 5. The rest are candidates for real errors.

    The total number here is bigger than in the note to the preset (9,464 against
    5,269): there the measurement is over the rows of a project, and here over the
    whole tree, together with those a project would mark «nothing to translate».
    The difference is entirely in `same_as_en`: the names of equipment and the
    abbreviations need no translating.
    """
    found = _codes(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru"), pairs)
    assert found["brackets_mismatch"] == 746
    assert found["glued_markup"] == 5
    assert sum(found.values()) == 9_464
    assert found["same_as_en"] == 8_181


def test_the_colour_rule_is_quiet_on_a_professional_translation(pairs) -> None:
    """25 colour divergences over 124,893 rows — the rule will do switched on."""
    found = _codes(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru"), pairs)
    assert found["color_mismatch"] == 25


def test_paradox_did_lose_variables(pairs) -> None:
    """326 rows where a substitution was lost or swapped for another.

    It is for finds like these that the rules are written: `$JAP_zaibatsu_faction$`
    became `$JAP_naval_faction$` in the translation — in the game that shows as a
    foreign requirement.
    """
    found = _codes(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru"), pairs)
    assert found["dollar_mismatch"] == 326
