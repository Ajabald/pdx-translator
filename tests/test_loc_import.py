"""Загрузка перевода из готового дерева локализации отдельной командой."""
from __future__ import annotations

from ck3loc.core import unit_ops
from ck3loc.core.loc_import import ImportOptions, import_translations
from ck3loc.core.scanner import scan_project
from ck3loc.core.statuses import Status

from test_scanner import get_unit, make_project

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n c:0 "Gold"\n'
RU_START = 'l_russian:\n a:0 "Привет"\n'


def setup(db, make_tree):
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU_START}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    return pid


def test_fills_empty_translations(db, make_tree, tmp_path):
    """Перевод чужого мода принимается в пустые строки."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n'}, "other")

    report = import_translations(db, pid, other)

    assert report.files_found == 1
    assert report.imported == 1               # b — принят
    assert report.skipped_existing == 1       # a — перевод уже есть
    assert get_unit(db, "b")["ru_text"] == "Мир"
    assert get_unit(db, "b")["status"] == Status.TRANSLATED.value
    assert get_unit(db, "a")["ru_text"] == "Привет"


def test_overwrite_existing(db, make_tree):
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Здравствуй"\n'}, "other")

    report = import_translations(db, pid, other, ImportOptions(overwrite=True))

    assert report.imported == 1
    assert get_unit(db, "a")["ru_text"] == "Здравствуй"


def test_dry_run_changes_nothing(db, make_tree):
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml": 'l_russian:\n b:0 "Мир"\n'}, "other")

    report = import_translations(db, pid, other, dry_run=True)

    assert report.imported == 1
    assert report.samples == [("b", "", "Мир")]
    assert get_unit(db, "b")["ru_text"] is None      # предпросмотр ничего не пишет


def test_skips_equal_to_source_and_markers(db, make_tree):
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n b:0 "World"\n c:0 "Gold" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'},
                      "other")

    report = import_translations(db, pid, other)

    assert report.skipped_equal == 1 and report.skipped_marked == 1
    assert report.imported == 0
    # с выключенным правилом копия оригинала всё же принимается — иногда это
    # законный перевод (имена собственные, числа)
    report2 = import_translations(db, pid, other, ImportOptions(skip_equal_to_source=False))
    assert report2.imported == 1
    assert get_unit(db, "b")["ru_text"] == "World"


def test_unknown_keys_counted(db, make_tree):
    """Указали папку не от этого мода — это должно быть видно, а не молча ноль."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n zzz:0 "Что-то"\n b:0 "Мир"\n'}, "other")

    report = import_translations(db, pid, other)

    assert report.unknown_keys == 1
    assert report.imported == 1


def test_import_is_undoable_as_one_batch(db, make_tree):
    """Пачка снимается одним Ctrl+Z — иначе массовую операцию не откатить."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n'}, "other")
    batch = unit_ops.new_batch_id()

    import_translations(db, pid, other, ImportOptions(overwrite=True), batch_id=batch)
    assert get_unit(db, "a")["ru_text"] == "Здравствуй"
    assert get_unit(db, "b")["ru_text"] == "Мир"

    last = unit_ops.last_batch(db)
    assert last is not None and last[0] == batch and last[1] == "import"
    unit_ops.undo_batch(db, batch)

    assert get_unit(db, "a")["ru_text"] == "Привет"
    assert get_unit(db, "b")["ru_text"] is None


def test_missing_folder_reported(db, make_tree, tmp_path):
    pid = setup(db, make_tree)
    try:
        import_translations(db, pid, tmp_path / "нет-такой")
    except FileNotFoundError as e:
        assert "не найдена" in str(e)
    else:
        raise AssertionError("ожидалась FileNotFoundError")
