"""The format of the older games of the series: a table with semicolons.

The main property watched over here: **other people's columns are untouchable**.
In one row with the translation live the French, the German and the Spanish ones,
the `x` marker and a trailing comment; were we to assemble the row anew by our own
rules, all of that would vanish, and a mod assembled by a translator would take
three languages away from the players at once.
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
    # the comments and the header are not lost — they will travel back into the file
    assert loc.entries[0].comment_before.startswith("#CODE;")


def test_parse_reads_another_language_by_column() -> None:
    loc = csv.parse_text(VANILLA, language="french")
    assert loc.entries[0].text == "Cornouailles"
    loc = csv.parse_text(VANILLA, language="spanish")
    assert loc.entries[0].text == "Cornualles"


def test_an_unknown_language_falls_back_to_english() -> None:
    """The format has no Russian — and there is nowhere else to put the translation.

    That is exactly what the live CK2 Russian pack does: the English column
    becomes the column of the translation, the other languages stay where they are.
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
    assert changed[2:] == original[2:]      # the French one and onwards — byte for byte


def test_a_row_with_extra_separators_survives() -> None:
    """In vanilla CK2 253 rows have extra columns, and 196 have a tail after the «x»."""
    line = "PROV1452;Beshbaliq;Beshbaliq;;;;;;;;x;;;;"
    loc = csv.parse_text(line + "\n")
    assert loc.entries[0].text == "Beshbaliq"
    assert csv.render("english", loc.entries, loc.trailing) == line + "\n"


def test_a_trailing_comment_after_the_marker_survives() -> None:
    """The Russian pack writes the English original after the «x» — those are its notes."""
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
    """The key was not in the original — there is nowhere for a source row to come from."""
    from pdxloc.core.models import LocEntry

    entry = LocEntry(key="my_key", version="", text="Мой текст")
    assert csv.render("russian", [entry]) == "my_key;Мой текст;x\n"


# --- escaping ------------------------------------------------------------


def test_a_semicolon_in_the_translation_would_shift_the_columns() -> None:
    """A separator inside the text the format does not survive — we change it for a comma."""
    assert csv.escape_value("раз; два") == "раз, два"


def test_a_real_newline_becomes_the_paradox_one() -> None:
    assert csv.escape_value("раз\nдва") == "раз\\nдва"
    assert csv.unescape("раз\\nдва") == "раз\nдва"


# --- the encodings -------------------------------------------------------


def test_encoding_is_told_by_the_content_of_the_tree(tmp_path) -> None:
    """cp1251 and cp1252 decode anything at all, so we look at the text.

    The threshold is taken with room to spare: in vanilla CK2 the share of rows
    with a Russian word does not exceed 0.0006 (single `ö` and `é` read as
    Cyrillic), while in the translation it reaches 0.99.
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
    """In the CK2 Russian pack there is a `WikipediaLinks.csv` of Latin letters alone.

    Were we to decide by it, the conclusion would be the opposite — that is why the
    encoding is decided by the tree whole and not by the first file that turns up.
    """
    tree = tmp_path / "ru"
    tree.mkdir()
    (tree / "WikipediaLinks.csv").write_bytes(b"k;https://example.org/Kiev;x\n")
    (tree / "text.csv").write_bytes("k;Русский текст;x\n".encode("cp1251"))
    assert csv.detect_encoding(csv.files(tree)) == "cp1251"


def test_written_file_keeps_the_encoding_and_the_line_endings(tmp_path) -> None:
    """The game reads cp1251 with its own fonts, and all of its files are CRLF."""
    from pdxloc.core.models import LocEntry

    path = tmp_path / "out.csv"
    csv.write_file(path, "russian", [LocEntry("k", "", "Текст")],
                   encoding="cp1251")
    raw = path.read_bytes()
    assert raw == "k;Текст;x\r\n".encode("cp1251")


# --- recognising the format ----------------------------------------------


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
    """The fifth column is skipped in the game itself: `GERMAN;;SPANISH`."""
    assert csv.column_of(language) == column
    assert csv.column_of(language, VANILLA.splitlines()[0]) == column


def test_other_languages_are_kept_only_if_the_encoding_allows(tmp_path) -> None:
    """We keep the French column as long as it survives the encoding of the translation.

    cp1251 has neither `ê` nor `ü`: were we to keep the French text there,
    `Reconquête` would silently become `Reconquкte` — and would be written back
    without a single error. That is why such a row is squeezed down to «key;
    translation; x», exactly as the live CK2 Russian pack does. A row that fits the
    encoding we leave alone.
    """
    from pdxloc.core.models import LocEntry

    latin = "k1;Reconquest;Reconquete de Castille;Rueckeroberung;;Reconquista;;;;;x"
    accented = "k2;Reconquest;Reconquête de Castille;Rückeroberung;;Reconquista;;;;;x"
    entries = [LocEntry("k1", "", "Реконкиста", raw=latin),
               LocEntry("k2", "", "Реконкиста", raw=accented)]

    out = csv.render("russian", entries, encoding="cp1251").splitlines()
    assert out[0].split(";")[2:] == latin.split(";")[2:]     # survived whole
    assert out[1] == "k2;Реконкиста;x"                       # squeezed

    # a translation into a language of the same encoding squeezes nothing
    entries[1].text = "Reconquête de Castille"
    french = csv.render("french", entries[1:], encoding="cp1252").splitlines()
    assert french[0].split(";")[3:] == accented.split(";")[3:]


def test_bytes_foreign_to_the_encoding_survive_the_round_trip(tmp_path) -> None:
    """In vanilla CK2 there are Czech rows in cp1250 in the middle of a cp1252 file.

    We read with `surrogateescape` and write the same way — otherwise translating
    one row would spoil the neighbouring languages in the whole file.
    """
    path = tmp_path / "text1.csv"
    original = b"k;Peace;Mir;;;;;;;;x\r\nk2;War;V\x9dlka;;;;;;;;x\r\n"
    path.write_bytes(original)

    loc = csv.parse_file(path, language="english", encoding="cp1252")
    assert [e.text for e in loc.entries] == ["Peace", "War"]

    csv.write_file(path, "english", loc.entries, loc.trailing, encoding="cp1252")
    assert path.read_bytes() == original
