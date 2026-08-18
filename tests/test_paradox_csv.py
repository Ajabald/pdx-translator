"""Формат старых игр серии: таблица с точкой с запятой.

Главное свойство, которое здесь стережётся: **чужие колонки неприкосновенны**.
В одной строке с переводом живут французская, немецкая и испанская, маркер `x`
и хвостовой комментарий; собери мы строку заново по своим правилам — всё это
исчезло бы, и мод, собранный переводчиком, увёл бы у игроков три языка разом.
"""
from __future__ import annotations

import pytest

from pdxloc.core import paradox_csv as csv

VANILLA = (
    "#CODE;ENGLISH;FRENCH;GERMAN;;SPANISH;;;;;;;;;x\n"
    "#a note left by the author\n"
    "d_cornwall;Cornwall;Cornouailles;Cornwall;;Cornualles;;;;;;;;;x\n"
    "b_truro;Truro;Truro;Truro;;Truro;;;;;;;;;x\n"
)


def test_parse_reads_the_english_column() -> None:
    loc = csv.parse_text(VANILLA)
    assert [e.key for e in loc.entries] == ["d_cornwall", "b_truro"]
    assert loc.entries[0].text == "Cornwall"
    assert loc.warnings == []
    # комментарии и шапка не теряются — они уедут обратно в файл
    assert loc.entries[0].comment_before.startswith("#CODE;")


def test_parse_reads_another_language_by_column() -> None:
    loc = csv.parse_text(VANILLA, language="french")
    assert loc.entries[0].text == "Cornouailles"
    loc = csv.parse_text(VANILLA, language="spanish")
    assert loc.entries[0].text == "Cornualles"


def test_an_unknown_language_falls_back_to_english() -> None:
    """Русского в формате нет — и деть перевод больше некуда.

    Ровно так поступает живой русификатор CK2: колонка английского становится
    колонкой перевода, остальные языки остаются на местах.
    """
    assert csv.column_of("russian") == csv.column_of("english") == 1
    assert csv.parse_text(VANILLA, language="russian").entries[0].text == "Cornwall"


def test_rewriting_without_edits_returns_the_file_unchanged() -> None:
    loc = csv.parse_text(VANILLA)
    assert csv.render("english", loc.entries, loc.trailing) == VANILLA


def test_only_the_translated_column_changes() -> None:
    loc = csv.parse_text(VANILLA, language="russian")
    loc.entries[0].text = "Корнуолл"
    out = csv.render("russian", loc.entries, loc.trailing).splitlines()
    changed = out[2].split(";")
    original = VANILLA.splitlines()[2].split(";")
    assert changed[1] == "Корнуолл"
    assert changed[2:] == original[2:]      # французская и далее — байт в байт


def test_a_row_with_extra_separators_survives() -> None:
    """В ванильной CK2 253 строки имеют лишние колонки, в 196 хвост после «x»."""
    line = "PROV1452;Beshbaliq;Beshbaliq;;;;;;;;x;;;;"
    loc = csv.parse_text(line + "\n")
    assert loc.entries[0].text == "Beshbaliq"
    assert csv.render("english", loc.entries, loc.trailing) == line + "\n"


def test_a_trailing_comment_after_the_marker_survives() -> None:
    """Русификатор дописывает за «x» английский оригинал — это его заметки."""
    line = "EVTTITLE20366;Коронация;x #[coronation_ruler.GetTitledFirstName];x"
    loc = csv.parse_text(line + "\n", language="russian")
    loc.entries[0].text = "Венчание на царство"
    out = csv.render("russian", loc.entries, loc.trailing)
    assert out.startswith("EVTTITLE20366;Венчание на царство;x #[coronation")
    assert out.rstrip("\n").endswith(";x")


def test_a_line_without_a_separator_is_reported_not_swallowed() -> None:
    loc = csv.parse_text("d_cornwall;Cornwall;x\nмусор без разделителя\n")
    assert len(loc.entries) == 1
    assert len(loc.warnings) == 1
    assert "мусор" in loc.warnings[0]


def test_a_new_key_gets_a_row_of_its_own() -> None:
    """Ключа не было в оригинале — исходной строке взяться неоткуда."""
    from pdxloc.core.models import LocEntry

    entry = LocEntry(key="my_key", version="", text="Мой текст")
    assert csv.render("russian", [entry]) == "my_key;Мой текст;x\n"


# --- экранирование -------------------------------------------------------


def test_a_semicolon_in_the_translation_would_shift_the_columns() -> None:
    """Разделитель внутри текста формат не переживает — меняем на запятую."""
    assert csv.escape_value("раз; два") == "раз, два"


def test_a_real_newline_becomes_the_paradox_one() -> None:
    assert csv.escape_value("раз\nдва") == "раз\\nдва"
    assert csv.unescape("раз\\nдва") == "раз\nдва"


# --- кодировки -----------------------------------------------------------


def test_encoding_is_told_by_the_content_of_the_tree(tmp_path) -> None:
    """cp1251 и cp1252 декодируют что угодно, поэтому смотрим на текст.

    Порог берётся с запасом: у ванильной CK2 доля строк с русским словом не
    превышает 0,0006 (одиночные `ö` и `é`, прочитанные как кириллица), у
    перевода доходит до 0,99.
    """
    english = tmp_path / "en"
    english.mkdir()
    (english / "a.csv").write_bytes(
        "k;Grand Duchy of Königsberg;x\n".encode("cp1252"))
    assert csv.detect_encoding(csv.files(english)) == "cp1252"

    russian = tmp_path / "ru"
    russian.mkdir()
    (russian / "a.csv").write_bytes("k;Великое княжество;x\n".encode("cp1251"))
    assert csv.detect_encoding(csv.files(russian)) == "cp1251"


def test_a_file_of_links_alone_does_not_decide_for_the_tree(tmp_path) -> None:
    """В русификаторе CK2 есть `WikipediaLinks.csv` из одной латиницы.

    Реши мы по нему, вывод был бы обратный — поэтому кодировку определяет
    дерево целиком, а не первый попавшийся файл.
    """
    tree = tmp_path / "ru"
    tree.mkdir()
    (tree / "WikipediaLinks.csv").write_bytes(b"k;https://example.org/Kiev;x\n")
    (tree / "text.csv").write_bytes("k;Русский текст;x\n".encode("cp1251"))
    assert csv.detect_encoding(csv.files(tree)) == "cp1251"


def test_written_file_keeps_the_encoding_and_the_line_endings(tmp_path) -> None:
    """Игра читает cp1251 своими шрифтами, а все её файлы — CRLF."""
    from pdxloc.core.models import LocEntry

    path = tmp_path / "out.csv"
    csv.write_file(path, "russian", [LocEntry("k", "", "Текст")],
                   encoding="cp1251")
    raw = path.read_bytes()
    assert raw == "k;Текст;x\r\n".encode("cp1251")


# --- опознание формата ---------------------------------------------------


def test_detect_knows_localisation_from_a_data_table(tmp_path) -> None:
    loc = tmp_path / "loc"
    loc.mkdir()
    (loc / "text.csv").write_text(VANILLA, encoding="cp1252")
    assert csv.detect(loc)

    empty = tmp_path / "empty"
    empty.mkdir()
    assert not csv.detect(empty)


@pytest.mark.parametrize("language,column", [
    ("english", 1), ("french", 2), ("german", 3), ("spanish", 5),
])
def test_column_order_matches_the_vanilla_header(language, column) -> None:
    """Пятая колонка пропущена в самой игре: `GERMAN;;SPANISH`."""
    assert csv.column_of(language) == column
    assert csv.column_of(language, VANILLA.splitlines()[0]) == column


def test_other_languages_are_kept_only_if_the_encoding_allows(tmp_path) -> None:
    """Французскую колонку сохраняем, пока она переживает кодировку перевода.

    В cp1251 нет ни `ê`, ни `ü`: сохрани мы там французский текст, `Reconquête`
    молча стало бы `Reconquкte` — и записалось бы обратно без единой ошибки.
    Поэтому такая строка ужимается до «ключ; перевод; x», ровно как делает
    живой русификатор CK2. Строку, которая в кодировку лезет, не трогаем.
    """
    from pdxloc.core.models import LocEntry

    latin = "k1;Reconquest;Reconquete de Castille;Rueckeroberung;;Reconquista;;;;;x"
    accented = "k2;Reconquest;Reconquête de Castille;Rückeroberung;;Reconquista;;;;;x"
    entries = [LocEntry("k1", "", "Реконкиста", raw=latin),
               LocEntry("k2", "", "Реконкиста", raw=accented)]

    out = csv.render("russian", entries, encoding="cp1251").splitlines()
    assert out[0].split(";")[2:] == latin.split(";")[2:]     # уцелела целиком
    assert out[1] == "k2;Реконкиста;x"                       # ужата

    # перевод на язык той же кодировки ничего не ужимает
    entries[1].text = "Reconquête de Castille"
    french = csv.render("french", entries[1:], encoding="cp1252").splitlines()
    assert french[0].split(";")[3:] == accented.split(";")[3:]


def test_bytes_foreign_to_the_encoding_survive_the_round_trip(tmp_path) -> None:
    """В ванильной CK2 есть чешские строки в cp1250 посреди cp1252-файла.

    Читаем с `surrogateescape` и пишем так же — иначе перевод одной строки
    испортил бы соседние языки во всём файле.
    """
    path = tmp_path / "text1.csv"
    original = b"k;Peace;Mir;;;;;;;;x\r\nk2;War;V\x9dlka;;;;;;;;x\r\n"
    path.write_bytes(original)

    loc = csv.parse_file(path, language="english", encoding="cp1252")
    assert [e.text for e in loc.entries] == ["Peace", "War"]

    csv.write_file(path, "english", loc.entries, loc.trailing, encoding="cp1252")
    assert path.read_bytes() == original
