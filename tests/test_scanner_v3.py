"""Тесты v3-M1: правило ru==en, конфликты, дубликаты, _updated в оригинале."""
from __future__ import annotations

from ck3loc.core.exporter import export_project
from ck3loc.core.models import ExportOptions
from ck3loc.core.paradox_yaml import parse_file
from ck3loc.core.scanner import LEGACY_MARKER, scan_project
from ck3loc.core.statuses import Status

from test_scanner import get_unit, make_project


def test_ru_equals_en_accepted_in_translated_file(db, make_tree):
    """Совпадающий с оригиналом перевод — норма (имена, «OK», числа),
    если в файле есть и настоящие переводы."""
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
    """Файл — тупая копия оригинала: ничего не переведено."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Hello"\n b:0 "World"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "a")["status"] == Status.UNTRANSLATED.value
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


def test_marker_still_wins_over_equality(db, make_tree):
    """Маркер старых скриптов сильнее правила равенства."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Привет"\n b:0 "World" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


def test_existing_untranslated_not_flipped_by_equality(db, make_tree):
    """Уже известная непереведённая строка не становится переведённой из-за
    того, что кто-то положил рядом копию оригинала (защита живых данных)."""
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Привет"\n b:0 "World" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value
    # экспорт с фолбэком стёр бы маркер — проверяем, что рескан не «переведёт» строку
    make_tree({"m_l_russian.yml":
               'l_russian:\n a:0 "Привет"\n b:0 "World"\n'}, "ru")
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


def test_conflict_detected_when_en_also_changed(db, make_tree):
    """Раньше правка перевода на диске терялась молча, если EN тоже изменился."""
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello there"\n'}, "en")
    make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Здравствуйте"\n'}, "ru")
    stats = scan_project(db, pid)
    assert stats.ru_conflicts == 1
    rel, key, db_ru, disk_ru = stats.ru_conflict_list[0]
    assert key == "a" and db_ru == "Привет" and disk_ru == "Здравствуйте"
    assert get_unit(db, "a")["ru_text"] == "Привет"      # база главнее
    assert get_unit(db, "a")["status"] == Status.STALE.value


def test_ru_duplicate_keys_counted(db, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n'}, "en")
    ru = make_tree({"m_l_russian.yml":
                    'l_russian:\n a:0 "Первый"\n a:0 "Второй"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert len(stats.duplicate_keys_ru) == 1
    assert get_unit(db, "a")["ru_text"] == "Второй"      # последний побеждает


def test_updated_in_source_tree_is_scanned(db, make_tree):
    """«_updated» отсеивается только в дереве перевода: в оригинале это
    легальное имя файла."""
    en = make_tree({"mod_updated_events_l_english.yml":
                    'l_english:\n evt:0 "Event text"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.files_en == 1
    assert get_unit(db, "evt") is not None


def test_fallback_export_writes_marker(db, make_tree, tmp_path):
    """Непереведённые строки в режиме фолбэка помечаются, чтобы следующий
    скан не принял их за готовый перевод."""
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
    assert entries["a"].comment_inline == ""       # переведённые — без пометок
