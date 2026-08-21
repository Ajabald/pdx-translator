"""Tests of v3-M1: the ru==en rule, conflicts, duplicates, _updated in the original."""
from __future__ import annotations

from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.paradox_yaml import parse_file
from pdxloc.core.scanner import LEGACY_MARKER, scan_project
from pdxloc.core.statuses import Status

from test_scanner import get_unit, make_project


def test_ru_equals_en_accepted_in_translated_file(db, make_tree):
    """A translation coinciding with the original is the norm (names, «OK», numbers),
    if the file holds real translations as well."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n greet:0 "Hello"\n name:0 "Stark"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n greet:0 "Привет"\n name:0 "Stark"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    u = get_unit(db, "name")
    assert u["status"] == Status.TRANSLATED.value
    assert u["ru_text"] == "Stark"


def test_ru_equals_en_rejected_in_copy_file(db, make_tree):
    """The file is a dumb copy of the original: nothing is translated."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Hello"\n b:0 "World"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "a")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


def test_marker_still_wins_over_equality(db, make_tree):
    """The marker of the old scripts is stronger than the rule of equality."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Привет"\n b:0 "World" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


def test_existing_untranslated_not_flipped_by_equality(db, make_tree):
    """A row already known as untranslated does not become translated because
    somebody put a copy of the original next to it (protection of live data)."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Привет"\n b:0 "World" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value
    # an export with a fallback would erase the marker — we check that a rescan does not «translate» the row
    make_tree({"m_l_russian.yml":
               'l_russian:\n a:0 "Привет"\n b:0 "World"\n'}, "ru")
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


def test_conflict_detected_when_en_also_changed(db, make_tree):
    """An edit of the translation on the disk used to be lost silently if the EN changed too."""
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello there"\n'}, "en")
    make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Здравствуйте"\n'}, "ru")
    stats = scan_project(db, pid)
    assert stats.ru_conflicts == 1
    _rel, key, db_ru, disk_ru = stats.ru_conflict_list[0]
    assert key == "a" and db_ru == "Привет" and disk_ru == "Здравствуйте"
    assert get_unit(db, "a")["ru_text"] == "Привет"      # the database rules
    assert get_unit(db, "a")["status"] == Status.STALE.value


def test_ru_duplicate_keys_counted(db, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Первый"\n a:0 "Второй"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert len(stats.duplicate_keys_ru) == 1
    assert get_unit(db, "a")["ru_text"] == "Второй"      # the last one wins


def test_updated_in_source_tree_is_scanned(db, make_tree):
    """«_updated» is sifted out only in the translation tree: in the original that is
    a lawful file name."""
    en = make_tree({"mod_updated_events_l_english.yml":
                    'l_english:\n evt:0 "Event text"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.files_en == 1
    assert get_unit(db, "evt") is not None


def test_fallback_export_writes_marker(db, make_tree, tmp_path):
    """Untranslated rows in fallback mode are marked, so that the next scan does not
    take them for a ready translation."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)
    entries = {e.key: e for e in parse_file(out / "m_l_russian.yml").entries}
    assert entries["b"].text == "World"
    assert LEGACY_MARKER in entries["b"].comment_inline
    assert entries["a"].comment_inline == ""       # the translated ones without marks
