"""Loading a translation from a ready localisation tree by a command of its own."""
from __future__ import annotations

import sqlite3

import pytest

from pdxloc import project
from pdxloc.core import loc_import, paradox_yaml, unit_ops
from pdxloc.core.loc_import import ImportOptions, import_translations
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

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
    """The translation of somebody else's mod is accepted into empty rows."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n'}, "other")

    report = import_translations(db, pid, other)

    assert report.files_found == 1
    assert report.imported == 1               # b — accepted
    assert report.skipped_existing == 1       # a — a translation is there already
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
    assert get_unit(db, "b")["ru_text"] is None      # the preview writes nothing


def test_skips_equal_to_source_and_markers(db, make_tree):
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n b:0 "World"\n c:0 "Gold" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'},
                      "other")

    report = import_translations(db, pid, other)

    assert report.skipped_equal == 1 and report.skipped_marked == 1
    assert report.imported == 0
    # with the rule switched off a copy of the original is accepted after all —
    # sometimes it is a lawful translation (proper names, numbers)
    report2 = import_translations(db, pid, other, ImportOptions(skip_equal_to_source=False))
    assert report2.imported == 1
    assert get_unit(db, "b")["ru_text"] == "World"


def test_unknown_keys_counted(db, make_tree):
    """A folder not from this mod was named — that has to show, not a silent zero."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n zzz:0 "Что-то"\n b:0 "Мир"\n'}, "other")

    report = import_translations(db, pid, other)

    assert report.unknown_keys == 1
    assert report.imported == 1


def test_import_is_undoable_as_one_batch(db, make_tree):
    """The batch is taken off by one Ctrl+Z — otherwise a bulk operation cannot be undone."""
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
    with pytest.raises(FileNotFoundError, match="not found"):
        import_translations(db, pid, tmp_path / "нет-такой")


# --- the three steps separately -----------------------------------------


def plan_for(db, pid, folder, options=None):
    """Parse the tree and count the plan — the way the import window does it."""
    langs = project.languages(db, pid)
    rel_paths = [r["rel_path"] for r in db.execute(
        "SELECT rel_path FROM files WHERE project_id = ? AND is_deleted = 0", (pid,))]
    tree = loc_import.read_tree(folder, rel_paths, langs.src_lang, langs.tgt_lang)
    return tree, loc_import.build_plan(db, pid, tree, options)


def test_the_plan_touches_nothing(db, make_tree):
    """The preview is obliged to be harmless: it is counted for every tick."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n'}, "other")

    _, plan = plan_for(db, pid, other, ImportOptions(overwrite=True))

    assert plan.report.imported == 2
    assert [c.key for c in plan.changes] == ["a", "b"]
    assert get_unit(db, "a")["ru_text"] == "Привет"      # the database is untouched
    assert get_unit(db, "b")["ru_text"] is None


def test_the_tree_is_read_once_and_reused_for_every_rule_set(db, make_tree, monkeypatch):
    """The rules of acceptance do not change the files on the disk — no point rereading them.

    Every switch of a tick in the window used to parse the whole tree anew, and on
    a big mod that is seconds.
    """
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n'}, "other")
    reads: list = []
    real = paradox_yaml.parse_file
    monkeypatch.setattr(paradox_yaml, "parse_file",
                        lambda p, **kw: (reads.append(p), real(p, **kw))[1])

    tree, _ = plan_for(db, pid, other)
    assert len(reads) == 1

    # two different rule sets over one and the same parsed tree
    careful = loc_import.build_plan(db, pid, tree, ImportOptions())
    bold = loc_import.build_plan(db, pid, tree, ImportOptions(overwrite=True))

    assert careful.report.imported == 1        # only the empty row
    assert bold.report.imported == 2           # and the one that already had a translation
    assert len(reads) == 1, "диск читали заново ради галки"


def test_a_failure_midway_leaves_the_project_untouched(db, make_tree, monkeypatch):
    """Either the whole batch or nothing.

    The former path committed every row separately: a break midway left half of it
    accepted, and there was nothing to tell which half.
    """
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n b:0 "Мир"\n'}, "other")
    _, plan = plan_for(db, pid, other, ImportOptions(overwrite=True))

    def die(*args, **kwargs):
        raise sqlite3.OperationalError("диск кончился на середине")

    # We fall on the last step — already after the rows are updated and the history
    # is written: it is exactly those two records the rollback is obliged to take off.
    monkeypatch.setattr(loc_import.tm, "upsert_many", die)
    with pytest.raises(sqlite3.OperationalError):
        loc_import.apply_plan(db, plan, batch_id=unit_ops.new_batch_id())

    assert get_unit(db, "a")["ru_text"] == "Привет"
    assert get_unit(db, "b")["ru_text"] is None
    assert unit_ops.last_batch(db) is None, "история пачки тоже должна откатиться"


def test_reading_can_be_cancelled(db, make_tree):
    """A cancellation during the reading comes before the writing, so the project stays as it was."""
    pid = setup(db, make_tree)
    other = make_tree({"m_l_russian.yml":
                       'l_russian:\n a:0 "Здравствуй"\n'}, "other")

    with pytest.raises(loc_import.ImportCancelled):
        import_translations(db, pid, other, ImportOptions(overwrite=True),
                            should_cancel=lambda: True)

    assert get_unit(db, "a")["ru_text"] == "Привет"
