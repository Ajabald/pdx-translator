"""Tests of the parser and writer of the Paradox format."""
from __future__ import annotations

import pytest

from pdxloc.core import paradox_yaml as py_
from pdxloc.core.models import LocEntry

from conftest import REALDATA_EN, REALDATA_RU, realdata_available, requires_realdata

SAMPLE = '''l_english:

#Rule
rule_agot_buildings_bla:0 "Bloodlines' Special Buildings"
 setting_enabled:0 "Enabled"
 agot_blackwood_bow_bla.0001.a.tt: "Some event text with [GetTrait('brave').GetName] and $VALUE$"
 key_with_escapes:1 "He said \\"hi\\"\\nNew line"
 key_inline_comment:0 "Text" # trailing comment
 key-with-dash:0 "Dash"
# trailing block
'''


def parse_sample():
    return py_.parse_text(SAMPLE, source_name="sample.yml")


def test_header_language():
    assert parse_sample().language == "english"


def test_entry_count_and_keys():
    lf = parse_sample()
    assert [e.key for e in lf.entries] == [
        "rule_agot_buildings_bla", "setting_enabled",
        "agot_blackwood_bow_bla.0001.a.tt", "key_with_escapes",
        "key_inline_comment", "key-with-dash",
    ]
    assert not lf.warnings


def test_versions_preserved():
    lf = parse_sample()
    by_key = {e.key: e for e in lf.entries}
    assert by_key["rule_agot_buildings_bla"].version == "0"
    assert by_key["agot_blackwood_bow_bla.0001.a.tt"].version == ""  # without a version
    assert by_key["key_with_escapes"].version == "1"


def test_raw_text_not_unescaped():
    lf = parse_sample()
    by_key = {e.key: e for e in lf.entries}
    assert by_key["key_with_escapes"].text == 'He said \\"hi\\"\\nNew line'


def test_unescape():
    assert py_.unescape('a\\nb\\"c') == 'a\nb"c'


def test_comment_before_and_inline():
    lf = parse_sample()
    by_key = {e.key: e for e in lf.entries}
    assert "#Rule" in by_key["rule_agot_buildings_bla"].comment_before
    assert by_key["key_inline_comment"].comment_inline == "# trailing comment"
    assert lf.trailing.strip() == "# trailing block"


def test_key_at_column_zero_parsed():
    # the EN files hold keys without a leading space
    lf = parse_sample()
    assert lf.entries[0].key == "rule_agot_buildings_bla"


def test_unrecognized_line_warns():
    lf = py_.parse_text('l_english:\n garbage line without quotes\n', source_name="x.yml")
    assert len(lf.warnings) == 1
    assert not lf.entries


def test_missing_closing_quote_salvaged():
    # a real defect in the BLA files: there is no closing quote
    lf = py_.parse_text('l_english:\n broken:0 "Text without closing quote\n', source_name="x.yml")
    assert len(lf.entries) == 1
    assert lf.entries[0].text == "Text without closing quote"
    assert len(lf.warnings) == 1
    assert "no closing quote" in lf.warnings[0]


def test_missing_header_warns_but_parses():
    lf = py_.parse_text(' key:0 "text"\n', source_name="x.yml")
    assert lf.warnings
    assert len(lf.entries) == 1


def test_fully_commented_file_is_not_an_error():
    """In the vanilla localisation there are files commented out by the Paradox
    editor whole: no header, no keys. There is nothing to complain about there."""
    lf = py_.parse_text(
        "# === [LocEditor:RedundantFile] File contains no active keys ===\n"
        "# b_something: \"Что-то\"\n", source_name="x.yml")
    assert lf.entries == []
    assert lf.warnings == []


def test_key_with_apostrophe():
    """Keys with an apostrophe are in the vanilla CK3 localisation (b_ka'abir).

    The former character class did not allow them: the line was not recognised as
    a record, a translation for it could not be set up, and at a write into the mod
    it would have vanished.
    """
    lf = py_.parse_text(
        'l_english:\n'
        ' b_mansa\'l-kharaz:0 "Mansa\'l-Kharaz"\n'
        ' b_ka\'abir: "Ka\'abir"\n', source_name="x.yml")
    assert [e.key for e in lf.entries] == ["b_mansa'l-kharaz", "b_ka'abir"]
    assert [e.text for e in lf.entries] == ["Mansa'l-Kharaz", "Ka'abir"]
    assert lf.warnings == []


def test_commented_out_entry_stays_comment():
    """The widened class of a key must not turn comments into records."""
    lf = py_.parse_text('l_english:\n#b_old:0 "Старое"\n a:0 "A"\n', source_name="x.yml")
    assert [e.key for e in lf.entries] == ["a"]
    assert "#b_old" in lf.entries[0].comment_before


def test_roundtrip_semantic():
    lf = parse_sample()
    rendered = py_.render(lf.language, lf.entries, lf.trailing)
    lf2 = py_.parse_text(rendered)
    assert lf2.language == lf.language
    assert [(e.key, e.version, e.text, e.comment_inline) for e in lf2.entries] == \
           [(e.key, e.version, e.text, e.comment_inline) for e in lf.entries]
    # the second run is stable byte for byte
    assert py_.render(lf2.language, lf2.entries, lf2.trailing) == rendered


def test_real_newline_escaped_on_write():
    """A real line break in a translation used to tear a record in two.

    Pressing Enter in the translation field or pasting text out of a messenger is
    an ordinary thing; in the file of the mod after that the first half was left
    without a closing quote, and the second stopped being a record.
    """
    entry = LocEntry(key="k", version="0", text="Первая строка\nВторая строка")
    rendered = py_.render("russian", [entry])

    assert len(rendered.rstrip("\n").split("\n")) == 2      # the header and one record
    again = py_.parse_text(rendered)
    assert len(again.entries) == 1
    assert again.entries[0].text == "Первая строка\\nВторая строка"
    assert again.warnings == []


def test_windows_newline_escaped():
    rendered = py_.render("russian", [LocEntry(key="k", version="0", text="а\r\nб\rв")])
    assert py_.parse_text(rendered).entries[0].text == "а\\nб\\nв"


def test_existing_escape_untouched():
    entry = LocEntry(key="k", version="0", text="Абзац\\n\\nВторой")
    assert py_.parse_text(py_.render("russian", [entry])).entries[0].text == "Абзац\\n\\nВторой"


def test_raw_quote_inside_value_preserved():
    """A bare quote inside a value is the norm of the format: in the vanilla CK3
    localisation there are 8413 such records. Escaping them will not do, the text would shift."""
    entry = LocEntry(key="k", version="0", text='Он сказал "нет" и ушёл')
    assert py_.parse_text(py_.render("russian", [entry])).entries[0].text == 'Он сказал "нет" и ушёл'


def test_write_file_bom(tmp_path):
    p = tmp_path / "out_l_russian.yml"
    py_.write_file(p, "russian", [LocEntry(key="k", version="0", text="привет")])
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").startswith("l_russian:\n")
    lf = py_.parse_file(p)
    assert lf.language == "russian"
    assert lf.entries[0].text == "привет"


# ---------- real data ----------

@requires_realdata
@pytest.mark.skipif(not realdata_available(), reason="нет реальных деревьев BLA")
def test_real_en_tree_counts():
    files = [p for p in REALDATA_EN.rglob("*.yml") if "_l_english" in p.name]
    assert len(files) == 30
    # 5276 ordinary records + 1 salvaged row without a closing quote
    total = sum(len(py_.parse_file(p).entries) for p in files)
    assert total == 5277


@requires_realdata
@pytest.mark.skipif(not realdata_available(), reason="нет реальных деревьев BLA")
def test_real_ru_tree_counts():
    files = [p for p in REALDATA_RU.rglob("*.yml") if "_l_russian" in p.name and "_updated" not in p.name]
    assert len(files) == 30
    # 4342 ordinary records + 1 salvaged row without a closing quote
    total = sum(len(py_.parse_file(p).entries) for p in files)
    assert total == 4343


@requires_realdata
@pytest.mark.skipif(not realdata_available(), reason="нет реальных деревьев BLA")
def test_real_roundtrip_all_files():
    files = [p for p in REALDATA_EN.rglob("*.yml") if "_l_english" in p.name]
    files += [p for p in REALDATA_RU.rglob("*.yml") if "_l_russian" in p.name and "_updated" not in p.name]
    assert files
    for p in files:
        lf = py_.parse_file(p)
        rendered = py_.render(lf.language, lf.entries, lf.trailing)
        lf2 = py_.parse_text(rendered, source_name=p.name)
        assert [(e.key, e.version, e.text) for e in lf2.entries] == \
               [(e.key, e.version, e.text) for e in lf.entries], p.name
