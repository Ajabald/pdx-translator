"""Тесты v2-веток сканера: auto-ignore и рескан ignored/custom."""
from __future__ import annotations

from pdxloc.core import tm
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status
from pdxloc.core.unit_ops import set_status

from test_scanner import get_unit, make_project

TAG = "[GetPlayer.GetDynasty.GetNameNoTooltip]"


def test_new_markup_only_key_auto_ignored(db, make_tree):
    en = make_tree({"m_l_english.yml":
                    f'l_english:\n tag_key:0 "{TAG}"\n text_key:0 "Real text"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.auto_ignored == 1
    assert get_unit(db, "tag_key")["status"] == Status.IGNORED.value
    assert get_unit(db, "text_key")["status"] == Status.UNTRANSLATED.value


def test_existing_untranslated_tag_migrates_to_ignored(db, make_tree):
    # строка уже в БД как untranslated (создана до v2) -> рескан переводит в ignored
    en = make_tree({"m_l_english.yml": f'l_english:\n tag_key:0 "{TAG}"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    db.execute("UPDATE units SET status = 'untranslated' WHERE key = 'tag_key'")
    db.commit()
    stats = scan_project(db, pid)
    assert stats.auto_ignored == 1
    assert get_unit(db, "tag_key")["status"] == Status.IGNORED.value


def test_translated_tag_string_not_ignored(db, make_tree):
    # если в RU есть перевод тега (напр. другой тег) — статус translated, не ignored
    en = make_tree({"m_l_english.yml": f'l_english:\n tag_key:0 "{TAG}"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n tag_key:0 "[GetOther]"\n'}, "ru")
    pid = make_project(db, en, ru)
    stats = scan_project(db, pid)
    assert stats.auto_ignored == 0
    assert get_unit(db, "tag_key")["status"] == Status.TRANSLATED.value


def test_ignored_stays_ignored_when_still_markup(db, make_tree):
    en = make_tree({"m_l_english.yml": f'l_english:\n tag_key:0 "{TAG}"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"m_l_english.yml": 'l_english:\n tag_key:0 "$OTHER_VAR$"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "tag_key")
    assert u["status"] == Status.IGNORED.value
    assert u["en_text"] == "$OTHER_VAR$"


def test_ignored_becomes_untranslated_when_text_appears(db, make_tree):
    en = make_tree({"m_l_english.yml": f'l_english:\n tag_key:0 "{TAG}"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    make_tree({"m_l_english.yml": 'l_english:\n tag_key:0 "Now real text"\n'}, "en")
    scan_project(db, pid)
    assert get_unit(db, "tag_key")["status"] == Status.UNTRANSLATED.value


def test_manual_ignored_survives_rescan(db, make_tree):
    # пользователь руками игнорировал обычную строку — рескан без изменений не трогает
    en = make_tree({"m_l_english.yml": 'l_english:\n k:0 "Some text"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    set_status(db, [get_unit(db, "k")["id"]], Status.IGNORED)
    scan_project(db, pid)
    assert get_unit(db, "k")["status"] == Status.IGNORED.value


def test_custom_becomes_stale_on_en_change(db, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n k:0 "Text v1"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n k:0 "Перевод"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    set_status(db, [get_unit(db, "k")["id"]], Status.CUSTOM)
    make_tree({"m_l_english.yml": 'l_english:\n k:0 "Text v2"\n'}, "en")
    scan_project(db, pid)
    u = get_unit(db, "k")
    assert u["status"] == Status.STALE.value
    assert u["prev_en_text"] == "Text v1"
    assert u["ru_text"] == "Перевод"


def test_custom_survives_unchanged_rescan(db, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n k:0 "Text"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n k:0 "Перевод"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    set_status(db, [get_unit(db, "k")["id"]], Status.CUSTOM)
    scan_project(db, pid)
    assert get_unit(db, "k")["status"] == Status.CUSTOM.value


def test_bulk_apply_can_be_undone(db, make_tree):
    """Массовая подстановка из памяти обязана откатываться Ctrl+Z.

    Трогает она только пустые строки, то есть «терять нечего», — но охват у
    неё тысячи строк разом, и вернуть их к «не переведено» иначе нечем.
    Отмена, которая молча не охватывает одну операцию из трёх, учит не
    доверять отмене вообще.
    """
    from pdxloc.core import unit_ops

    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Same"\n b:0 "Same"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    tm.upsert(db, "Same", "Одинаково")
    scan_project(db, pid)

    assert get_unit(db, "a")["ru_text"] == "Одинаково"
    assert get_unit(db, "a")["status"] == Status.AUTO.value

    batch = unit_ops.last_batch(db)
    assert batch is not None, "подстановка не оставила пачки в истории"
    unit_ops.undo_batch(db, batch[0])

    back = get_unit(db, "a")
    assert back["ru_text"] is None
    assert back["status"] == Status.UNTRANSLATED.value


def test_bulk_apply_writes_nothing_when_there_is_no_match(db, make_tree):
    """Пустой отбор не должен заводить пачку: Ctrl+Z предложил бы пустоту."""
    from pdxloc.core import unit_ops

    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Unheard of"\n'}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)

    assert tm.bulk_apply(db, pid) == 0
    assert unit_ops.last_batch(db) is None


def test_bulk_apply_skips_ignored(db, make_tree):
    # два одинаковых EN: один переведён, второй ignored -> TM не заполняет ignored
    en = make_tree({"m_l_english.yml":
                    'l_english:\n a:0 "Same"\n b:0 "Same"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Одинаково"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    set_status(db, [get_unit(db, "b")["id"]], Status.IGNORED)
    # сброс auto, чтобы проверить повторный bulk_apply
    db.execute("UPDATE units SET ru_text = NULL WHERE key='b' AND status='ignored'")
    db.commit()
    scan_project(db, pid)
    assert get_unit(db, "b")["status"] == Status.IGNORED.value
    assert get_unit(db, "b")["ru_text"] is None
