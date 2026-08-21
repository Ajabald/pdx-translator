"""An acceptance test on the vanilla tree of Stellaris.

The third live game in the project and the first whose grammar lives right inside
the row: since version 3.6 Stellaris declines generated names with the tags
`&!fem` and the variants `|||gen:` (described in
`localisation/99_README_GRAMMAR.txt`). The numbers are taken off the installed
game; they stand here so that an edit of the registry or of the rules does not
silently part ways with reality.

The path is the variable `PDXT_REALDATA_STELLARIS` (the `localisation` folder).
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
EXPECTED_RU_ENTRIES = 150_899      # 12 keys were duplicated by the translator


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


# --- the parsing --------------------------------------------------------


def test_the_tree_is_recognised_and_parsed(trees) -> None:
    """The format is recognised by the content, and the parsing goes without a single complaint."""
    assert loc_formats.detect(REALDATA_STELLARIS / "english") == loc_formats.YML

    parsed, warnings = trees
    assert warnings == []
    assert len(parsed["english"][0]) == EXPECTED_EN_FILES
    assert parsed["english"][2] == EXPECTED_EN_ENTRIES
    assert len(parsed["russian"][0]) == EXPECTED_RU_FILES
    assert parsed["russian"][2] == EXPECTED_RU_ENTRIES


def test_the_translation_is_complete_and_adds_case_forms(trees) -> None:
    """Not one English key without a pair; the extra ones are case forms."""
    parsed, _ = trees
    en, ru = parsed["english"][1], parsed["russian"][1]
    assert set(en) - set(ru) == set()
    assert len(set(ru) - set(en)) == 1_670


# --- the grammar system of 3.6 ------------------------------------------


def test_how_much_grammar_there_is(trees) -> None:
    """The system is sharpened for languages with cases — the numbers show it."""
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
    """`энергия&!fem|||gen:энергии` used to travel to the translator as it is."""
    parsed, _ = trees
    for text in parsed["russian"][1].values():
        shielded, mapping = mt.shield_tags(text)
        assert "&!" not in shielded and "|||" not in shielded
        assert mt.unshield(shielded, mapping) == text


def test_markup_of_the_other_games_covers_stellaris(trees) -> None:
    """`§`, `£` and `$…$` were in the registry already — here is where they are checked.

    Twelve rows out of 149,217 stay with a bare symbol, and not one of them
    through our fault:

    * ten are stubs Paradox forgot, `§_TODO CD§!` and `§_Not working…`; `§_` is no
      colour, and pretending that it is markup means hiding somebody else's
      oversight;
    * `£unity £§YUnity§!` — an extra `£` in a tutorial text, a typo as well;
    * `£leader_skill|$LEVEL$£` — an icon whose name is assembled from a variable
      with a flag; there is one such row in the whole tree, and changing the regex
      for its sake costs more than leaving it as it is.
    """
    parsed, _ = trees
    leftovers = [t for t in parsed["english"][1].values()
                 if "§" in markup.strip_markup(t) or "£" in markup.strip_markup(t)]
    assert len(leftovers) == 12
    assert sum(1 for t in leftovers if "§_" in t) == 10
    assert sum(1 for t in leftovers if re.search(r"£[a-z_]+\|\$", t)) == 1


# --- the checks ---------------------------------------------------------


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
    """502 rows where a gender tag was lost in the translation.

    `Agrippa&!masc` → `Агриппа`: in the game the name stops counting as masculine,
    and everything it is substituted into declines wrongly.
    """
    preset = _codes(qa_rules.resolve({"preset": "stellaris_ru"}, locale="ru"), pairs)
    assert preset["grammar_mismatch"] == 502
