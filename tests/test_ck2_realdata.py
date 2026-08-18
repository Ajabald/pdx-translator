"""Приёмочный тест на ванильной Crusader Kings II и живом русификаторе.

Третье живое дерево в проекте и первое прежнего формата: локализация лежит в
CSV, язык — колонка, кодировка однобайтовая. Числа сняты с версии игры 3.3.5.1
и мода `[BETA] CK II - Russian 3.3.5.1 (e479)`; стоят здесь затем, чтобы правка
разбора не разъехалась с реальностью молча.

Пути задаются переменными `PDXT_REALDATA_CK2` (папка `localisation` игры) и
`PDXT_REALDATA_CK2_RU` (распакованный русификатор); без них тест пропускается.
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
EXPECTED_KEYS = 92_444        # строк-записей во всех файлах вместе
EXPECTED_UNIQUE = 92_176      # 265 ключей повторяются в разных файлах


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
    # предупреждения парсера — только про строки без разделителя; в ванили их нет
    assert [w for loc in parsed for w in loc.warnings] == []


def test_vanilla_is_read_as_cp1252(vanilla) -> None:
    """Английское дерево не должно опознаваться как русское."""
    files, _ = vanilla
    assert paradox_csv.detect_encoding(files) == "cp1252"


def test_rewriting_the_whole_tree_changes_nothing(vanilla) -> None:
    """Разбор и запись без правок обязаны вернуть файл символ в символ.

    Это и есть страховка чужих колонок: 253 строки ванили имеют лишние
    разделители, в 196 после маркера `x` идут ещё пустые — всё это должно
    пережить круг «прочитали — записали».
    """
    files, parsed = vanilla
    fmt = loc_formats.get(loc_formats.CSV)
    for path, loc in zip(files, parsed, strict=True):
        original = path.read_bytes().decode(
            "cp1252", errors="surrogateescape").replace("\r\n", "\n")
        again = fmt.render("english", loc.entries, loc.trailing)
        # с точностью до последнего переноса строки: девять файлов ванили
        # обрываются без него, и дописать его безопаснее, чем тащить признак
        assert again.rstrip("\n") == original.rstrip("\n"), path.name


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_the_translation_is_read_as_cp1251() -> None:
    fmt = loc_formats.get(loc_formats.CSV)
    assert paradox_csv.detect_encoding(fmt.files(REALDATA_CK2_RU)) == "cp1251"


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_the_pair_matches_key_to_key() -> None:
    """Русификатор переписывает ванильные файлы построчно — ключи те же.

    Заменены 93 файла из 124: немецкий, французский и испанский переводы
    трогать незачем, отладочные `z_*.csv` тоже.
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
    # 116 расхождений на 92 тысячи ключей — это следы работы переводчика:
    # `String_Clever` → `String_clever` (регистр) и `jörmungandr` →
    # `jцrmungandr` (перекодировка). Ключ с испорченным именем игра не найдёт,
    # и такая строка останется в игре английской
    assert diff == 116


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_writing_a_translation_into_vanilla_keeps_the_other_languages() -> None:
    """Перевод ложится в колонку английского, французский и немецкий целы.

    Так устроен и сам русификатор: русской колонки формат не знает.
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
        assert new_parts[0] == old_parts[0]        # ключ на месте
        assert new_parts[2:] == old_parts[2:]      # прочие языки нетронуты


@pytest.mark.skipif(not ck2_translation_available(),
                    reason="нет распакованного русификатора (PDXT_REALDATA_CK2_RU)")
def test_the_ck2_preset_halves_the_noise() -> None:
    """Числа из примечания к пресету — здесь они и проверяются.

    Русская CK2 склоняет функциями игры (`GetEndA` — 10 433 вхождения,
    `GetLasLsya` — 1 787) и дописывает обращение там, где по-английски его нет.
    Встроенный набор видит в этом ошибку на каждой третьей строке.
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
    # чужие пресеты на этой игре бесполезны — у неё свои функции
    assert sum(count(qa_rules.resolve({"preset": "hoi4_ru"}, locale="ru")).values()) > 45_000
