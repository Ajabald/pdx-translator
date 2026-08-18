"""Главный сценарий инструмента: вышла новая версия мода.

Проверяем, что переводы переживают обновление, изменения классифицируются,
редакции оригинала копятся, а массовые операции откатываются.
"""
from __future__ import annotations

from pdxloc.core import unit_ops
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status
from pdxloc.core.textdiff import COSMETIC, MEANINGFUL

from test_scanner import get_unit, make_project

EN_V1 = ('l_english:\n'
         ' greet:0 "Winter is coming"\n'
         ' desc:0 "The old lord of Winterfell"\n'
         ' keep:0 "Unchanged line"\n')
RU_V1 = ('l_russian:\n'
         ' greet:0 "Зима близко"\n'
         ' desc:0 "Старый лорд Винтерфелла"\n'
         ' keep:0 "Неизменная строка"\n')


def setup(db, make_tree):
    en = make_tree({"m_l_english.yml": EN_V1}, "en")
    ru = make_tree({"m_l_russian.yml": RU_V1}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    return pid, make_tree


def test_translations_survive_update(db, make_tree):
    """Переводы не теряются, когда автор мода правит оригинал."""
    pid, tree = setup(db, make_tree)
    tree({"m_l_english.yml": EN_V1.replace(
        '"The old lord of Winterfell"', '"The young lord of Winterfell"')}, "en")
    scan_project(db, pid)
    u = get_unit(db, "desc")
    assert u["ru_text"] == "Старый лорд Винтерфелла"      # перевод на месте
    assert u["status"] == Status.STALE.value
    assert u["prev_en_text"] == "The old lord of Winterfell"
    assert u["en_changed_at"] is not None


def test_machine_translation_does_not_survive_a_changed_original(db, make_tree):
    """Машинный перевод прежней редакции не остаётся при новом оригинале.

    Его никто не читал, и относится он к другому тексту. Оставить как есть —
    значит держать перевод чужой строки под видом почти готового: он и в мод
    уедет по галке «включая машинный». Ведёт себя как «Авто»: сброс.
    """
    pid, tree = setup(db, make_tree)
    unit_id = get_unit(db, "desc")["id"]
    unit_ops.save_machine_text(db, unit_id, "Машинный перевод старого текста",
                               batch_id=unit_ops.new_batch_id())
    assert get_unit(db, "desc")["status"] == Status.MACHINE.value

    tree({"m_l_english.yml": EN_V1.replace(
        '"The old lord of Winterfell"', '"The young lord of Winterfell"')}, "en")
    scan_project(db, pid)

    u = get_unit(db, "desc")
    assert u["status"] == Status.UNTRANSLATED.value
    assert u["ru_text"] is None


def test_change_kind_cosmetic_vs_meaningful(db, make_tree):
    pid, tree = setup(db, make_tree)
    tree({"m_l_english.yml": (
        'l_english:\n'
        ' greet:0 "Winter is coming."\n'                       # косметика: точка
        ' desc:0 "The young lord of Winterfell"\n'             # смысл: слово
        ' keep:0 "Unchanged line"\n')}, "en")
    stats = scan_project(db, pid)
    assert stats.changed_cosmetic == 1
    assert stats.changed_meaningful == 1
    assert get_unit(db, "greet")["change_kind"] == COSMETIC
    assert get_unit(db, "desc")["change_kind"] == MEANINGFUL
    assert get_unit(db, "keep")["status"] == Status.TRANSLATED.value    # не тронута


def test_source_history_accumulates(db, make_tree):
    """Каждая редакция оригинала запоминается, а не только последняя."""
    pid, tree = setup(db, make_tree)
    unit_id = get_unit(db, "greet")["id"]
    assert len(unit_ops.source_history(db, unit_id)) == 1

    tree({"m_l_english.yml": EN_V1.replace('"Winter is coming"', '"Winter has come"')}, "en")
    scan_project(db, pid)
    tree({"m_l_english.yml": EN_V1.replace('"Winter is coming"', '"Winter came early"')}, "en")
    scan_project(db, pid)

    history = unit_ops.source_history(db, unit_id)
    assert [h["en_text"] for h in history] == [
        "Winter came early", "Winter has come", "Winter is coming"]
    # база для диффа осталась той, на которой основан перевод
    assert get_unit(db, "greet")["prev_en_text"] == "Winter is coming"


def test_repeated_scan_does_not_duplicate_history(db, make_tree):
    pid, _tree = setup(db, make_tree)
    scan_project(db, pid)
    scan_project(db, pid)
    unit_id = get_unit(db, "greet")["id"]
    assert len(unit_ops.source_history(db, unit_id)) == 1


def test_mass_actualize_cosmetic(db, make_tree):
    pid, tree = setup(db, make_tree)
    tree({"m_l_english.yml": (
        'l_english:\n'
        ' greet:0 "Winter is coming."\n'
        ' desc:0 "The young lord of Winterfell"\n'
        ' keep:0 "Unchanged line"\n')}, "en")
    scan_project(db, pid)

    ids = unit_ops.cosmetic_stale_ids(db, pid)
    assert len(ids) == 1
    batch = unit_ops.new_batch_id()
    assert unit_ops.actualize(db, ids, batch_id=batch) == 1
    assert get_unit(db, "greet")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "desc")["status"] == Status.STALE.value      # смысловая осталась

    # и это можно откатить
    assert unit_ops.undo_batch(db, batch) == 1
    assert get_unit(db, "greet")["status"] == Status.STALE.value


def test_status_change_keeps_previous_source(db, make_tree):
    """Смена статуса больше не стирает прежнюю редакцию оригинала."""
    pid, tree = setup(db, make_tree)
    tree({"m_l_english.yml": EN_V1.replace(
        '"The old lord of Winterfell"', '"The young lord of Winterfell"')}, "en")
    scan_project(db, pid)
    unit_id = get_unit(db, "desc")["id"]
    unit_ops.set_status(db, [unit_id], Status.REVIEWED)
    u = get_unit(db, "desc")
    assert u["status"] == Status.REVIEWED.value
    assert u["prev_en_text"] == "The old lord of Winterfell"    # раньше терялось
    assert u["change_kind"] is None                            # но пометка снята


def test_history_records_manual_edit_and_undo(db, make_tree):
    _pid, _ = setup(db, make_tree)
    unit_id = get_unit(db, "greet")["id"]
    batch = unit_ops.new_batch_id()
    unit_ops.save_ru_text(db, unit_id, "Зима на пороге", batch_id=batch)
    assert get_unit(db, "greet")["ru_text"] == "Зима на пороге"

    history = unit_ops.unit_history(db, unit_id)
    assert history[0]["ru_text"] == "Зима близко"      # состояние ДО правки
    assert unit_ops.undo_batch(db, batch) == 1
    assert get_unit(db, "greet")["ru_text"] == "Зима близко"


def test_history_limit(db, make_tree):
    _pid, _ = setup(db, make_tree)
    unit_id = get_unit(db, "greet")["id"]
    for i in range(unit_ops.HISTORY_LIMIT + 10):
        unit_ops.save_ru_text(db, unit_id, f"вариант {i}")
    assert len(unit_ops.unit_history(db, unit_id)) <= unit_ops.HISTORY_LIMIT


def test_last_batch(db, make_tree):
    _pid, _ = setup(db, make_tree)
    ids = [get_unit(db, k)["id"] for k in ("greet", "desc")]
    batch = unit_ops.new_batch_id()
    unit_ops.set_status(db, ids, Status.REVIEWED, batch_id=batch)
    info = unit_ops.last_batch(db)
    assert info is not None
    assert info[0] == batch and info[2] == 2
