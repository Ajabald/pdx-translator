"""An acceptance test on vanilla Crusader Kings II and a live Russian pack.

The third live tree in the project and the first of the former format: the
localisation lies in CSV, the language is a column, the encoding is single-byte.
The numbers are taken off game version 3.3.5.1 and the mod `[BETA] CK II -
Russian 3.3.5.1 (e479)`; they stand here so that an edit of the parsing does not
silently part ways with reality.

The paths are set by the variables `PDXT_REALDATA_CK2` (the `localisation` folder
of the game) and `PDXT_REALDATA_CK2_RU` (the unpacked Russian pack); without them
the test is skipped.
"""
from __future__ import annotations

import pytest

from pdxloc.core import loc_formats, paradox_csv

from conftest import (REALDATA_CK2, REALDATA_CK2_RU, ck2_realdata_available,
                      ck2_translation_available)

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not ck2_realdata_available(),
                       reason="нет ванильного дерева CK2 (PDXT_REALDATA_CK2)"),
]

EXPECTED_FILES = 124
EXPECTED_KEYS = 92_444        # record rows in all the files together
EXPECTED_UNIQUE = 92_176      # 265 keys repeat in different files


@pytest.fixture(scope="module")
def vanilla():
    fmt = loc_formats.get(loc_formats.CSV)
    files = fmt.files(REALDATA_CK2)
    parsed = [fmt.parse_file(p, language="english", encoding="cp1252")
              for p in files]
    return files, parsed


def test_the_tree_is_recognised_as_the_old_format() -> None:
    assert loc_formats.detect(REALDATA_CK2) == loc_formats.CSV


def test_the_whole_vanilla_tree_parses(vanilla) -> None:
    files, parsed = vanilla
    assert len(files) == EXPECTED_FILES
    assert sum(len(loc.entries) for loc in parsed) == EXPECTED_KEYS
    keys = {e.key for loc in parsed for e in loc.entries}
    assert len(keys) == EXPECTED_UNIQUE
    # the parser warnings are only about rows without a separator; vanilla has none
    assert [w for loc in parsed for w in loc.warnings] == []


def test_vanilla_is_read_as_cp1252(vanilla) -> None:
    """The English tree must not be recognised as the Russian one."""
    files, _ = vanilla
    assert paradox_csv.detect_encoding(files) == "cp1252"


def test_rewriting_the_whole_tree_changes_nothing(vanilla) -> None:
    """Parsing and writing without edits are obliged to return the file character for character.

    That is the very insurance of other people's columns: 253 rows of vanilla have
    extra separators, and in 196 of them empty ones follow the `x` marker — all of
    that has to survive the round of «read — written».
    """
    files, parsed = vanilla
    fmt = loc_formats.get(loc_formats.CSV)
    for path, loc in zip(files, parsed, strict=True):
        original = path.read_bytes().decode(
            "cp1252", errors="surrogateescape").replace("\r\n", "\n")
        again = fmt.render("english", loc.entries, loc.trailing)
        # down to the last line break: nine files of vanilla break off without one,
        # and adding it is safer than dragging a flag around
        assert again.rstrip("\n") == original.rstrip("\n"), path.name


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_the_translation_is_read_as_cp1251() -> None:
    fmt = loc_formats.get(loc_formats.CSV)
    assert paradox_csv.detect_encoding(fmt.files(REALDATA_CK2_RU)) == "cp1251"


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_the_pair_matches_key_to_key() -> None:
    """The Russian pack rewrites the vanilla files row by row — the keys are the same.

    93 files out of 124 are replaced: there is no point touching the German, the
    French and the Spanish translations, nor the debug `z_*.csv`.
    """
    fmt = loc_formats.get(loc_formats.CSV)
    ru_files = {p.name: p for p in fmt.files(REALDATA_CK2_RU)}
    assert len(ru_files) == 93

    paired = 0
    diff = 0
    for en_path in fmt.files(REALDATA_CK2):
        ru_path = ru_files.get(fmt.map_relpath(en_path.name, "english", "russian"))
        if ru_path is None:
            continue
        paired += 1
        en = fmt.parse_file(en_path, language="english", encoding="cp1252")
        ru = fmt.parse_file(ru_path, language="russian", encoding="cp1251")
        diff += len({e.key for e in en.entries} ^ {e.key for e in ru.entries})
    assert paired == 88
    # 116 divergences over 92 thousand keys are the traces of the translator's work:
    # `String_Clever` → `String_clever` (the case) and `jörmungandr` →
    # `jцrmungandr` (a recoding). A key with a spoilt name the game will not find,
    # and such a row stays English in the game
    assert diff == 116


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_writing_a_translation_into_vanilla_keeps_the_other_languages() -> None:
    """The translation goes into the English column, the French and the German are intact.

    The Russian pack itself is built the same way: the format knows no Russian column.
    """
    fmt = loc_formats.get(loc_formats.CSV)
    en_path = REALDATA_CK2 / "HolyFury.csv"
    ru_path = REALDATA_CK2_RU / "HolyFury.csv"
    en = fmt.parse_file(en_path, language="english", encoding="cp1252")
    ru = {e.key: e.text for e in
          fmt.parse_file(ru_path, language="russian", encoding="cp1251").entries}

    translated = 0
    for entry in en.entries:
        if entry.key in ru:
            entry.text = ru[entry.key]
            translated += 1
    assert translated > 19_000

    out = fmt.render("russian", en.entries, en.trailing).splitlines()
    original = en_path.read_bytes().decode("cp1252").splitlines()
    assert len(out) == len(original)
    for new_line, old_line in zip(out, original, strict=True):
        if new_line == old_line or not old_line or old_line.startswith("#"):
            continue
        new_parts, old_parts = new_line.split(";"), old_line.split(";")
        assert new_parts[0] == old_parts[0]        # the key is in place
        assert new_parts[2:] == old_parts[2:]      # the other languages are untouched


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_the_ck2_preset_halves_the_noise() -> None:
    """The numbers from the note to the preset — here is where they are checked.

    The Russian CK2 declines with the functions of the game (`GetEndA` — 10,433
    occurrences, `GetLasLsya` — 1,787) and adds an address where English has none.
    The built-in set sees an error in that on every third row.
    """
    import collections

    from pdxloc.core import qa_rules

    fmt = loc_formats.get(loc_formats.CSV)
    ru_by_name = {p.name: p for p in fmt.files(REALDATA_CK2_RU)}
    pairs = []
    for en_path in fmt.files(REALDATA_CK2):
        ru_path = ru_by_name.get(en_path.name)
        if ru_path is None:
            continue
        en = fmt.parse_file(en_path, language="english", encoding="cp1252")
        ru = {e.key: e.text for e in
              fmt.parse_file(ru_path, language="russian", encoding="cp1251").entries}
        pairs += [(e.text, ru[e.key]) for e in en.entries
                  if e.key in ru and e.text and ru[e.key]]
    assert len(pairs) == 89_616

    def count(rules) -> collections.Counter:
        found = collections.Counter()
        for en_text, ru_text in pairs:
            for code in rules.check(en_text, ru_text):
                found[code] += 1
        return found

    builtin = count(qa_rules.resolve(locale="ru"))
    assert sum(builtin.values()) == 45_593
    assert builtin["brackets_mismatch"] == 21_905
    assert builtin["glued_markup"] == 13_101

    preset = count(qa_rules.resolve({"preset": "ck2_ru"}, locale="ru"))
    assert sum(preset.values()) == 24_047
    assert preset["brackets_mismatch"] == 9_924
    assert preset["glued_markup"] == 3_546
    # other people's presets are useless on this game — it has functions of its own
    assert sum(count(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")).values()) > 45_000
