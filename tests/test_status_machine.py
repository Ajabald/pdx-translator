"""Статус «Машинный»: чего он не должен касаться.

Машинный перевод отличается от всего остального в проекте одним свойством: его
не читал человек. Отсюда весь набор ограничений, и каждое здесь закреплено
отдельно, потому что нарушение любого из них тихое.

Главных два. Он **не попадает в память переводов** — иначе машинная догадка
начала бы подставляться в другие строки и в другие проекты от имени готового
перевода. И он **не уходит в мод** без явной галки — иначе игроки прочтут то,
чего не читал никто.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pdxloc.core import qa, tm, unit_ops                    # noqa: E402
from pdxloc.core.exporter import export_project             # noqa: E402
from pdxloc.core.models import ExportOptions                # noqa: E402
from pdxloc.core.paradox_yaml import parse_file             # noqa: E402
from pdxloc.core.scanner import scan_project                # noqa: E402
from pdxloc.core.statuses import STATUS_ORDER, Status       # noqa: E402

from test_scanner import get_unit, make_project             # noqa: E402

EN = 'l_english:\n a:0 "Hello"\n b:0 "World"\n'


def project_with_machine_row(db, make_tree):
    """Проект, где `a` переведена машинно, а `b` не тронута."""
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    db.execute("UPDATE units SET ru_text = 'Привет', status = ? WHERE key = 'a'",
               (Status.MACHINE.value,))
    db.commit()
    return pid


# --- место в порядке и в палитрах ---

def test_machine_ranks_before_auto() -> None:
    """Подстановка из памяти — чужая работа руками, машинный перевод — ничья.

    Порядок здесь рабочий, а не алфавитный: наименее достоверное идёт первым,
    чтобы попадаться на глаза раньше.
    """
    order = list(STATUS_ORDER)
    assert order.index(Status.MACHINE) < order.index(Status.AUTO)
    assert order.index(Status.UNTRANSLATED) < order.index(Status.MACHINE)


def test_machine_has_a_colour_in_both_palettes() -> None:
    """Без записи в палитре `theme.status_color` падает на первой отрисовке."""
    from pdxloc.gui import theme

    for palette in (theme._LIGHT, theme._DARK):
        assert f"status.{Status.MACHINE}" in palette


def test_label_says_it_is_unchecked() -> None:
    """«Машинный» в одиночку читается как законченное состояние."""
    from pdxloc.core import statuses

    assert "unchecked" in statuses.STATUS_LABELS[Status.MACHINE]


# --- не попадает в память переводов ---

def test_machine_row_does_not_reach_the_memory(db, make_tree) -> None:
    pid = project_with_machine_row(db, make_tree)
    assert tm.feed_from_project(db, pid) == 0
    assert db.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0] == 0


def test_machine_row_is_not_exported_to_a_memory_database(
        db, make_tree, tmp_path) -> None:
    from pdxloc.core import tm_import

    project_with_machine_row(db, make_tree)
    out = tmp_path / "db.pdxtm"
    report = tm_import.export_project_tm(db, out, name="p")
    assert report.pairs == 0


# --- не уходит в мод без явной галки ---

def test_export_skips_machine_by_default(db, make_tree, tmp_path) -> None:
    pid = project_with_machine_row(db, make_tree)
    out = tmp_path / "out"
    report = export_project(db, pid, ExportOptions(mode="translated_only"),
                            out_root=out)
    assert report.keys_written == 0
    target = out / "m_l_russian.yml"
    if target.is_file():
        assert not parse_file(target).entries


def test_export_writes_machine_when_asked(db, make_tree, tmp_path) -> None:
    pid = project_with_machine_row(db, make_tree)
    out = tmp_path / "out"
    export_project(db, pid,
                   ExportOptions(mode="translated_only", include_machine=True),
                   out_root=out)
    entries = {e.key: e.text for e in parse_file(out / "m_l_russian.yml").entries}
    assert entries == {"a": "Привет"}


# --- правка человеком снимает пометку ---

def test_editing_a_machine_row_makes_it_translated(db, make_tree) -> None:
    """Иначе правка не доехала бы до мода: машинные строки туда не пишутся."""
    pid = project_with_machine_row(db, make_tree)
    unit_id = get_unit(db, "a")["id"]
    unit_ops.save_ru_text(db, unit_id, "Здравствуй")
    assert get_unit(db, "a")["status"] == Status.TRANSLATED.value
    # и теперь строка уже своя — память её принимает
    assert tm.feed_from_project(db, pid) == 1


def test_clearing_a_machine_row_returns_it_to_untranslated(db, make_tree) -> None:
    project_with_machine_row(db, make_tree)
    unit_id = get_unit(db, "a")["id"]
    unit_ops.save_ru_text(db, unit_id, "")
    assert get_unit(db, "a")["status"] == Status.UNTRANSLATED.value


def test_machine_status_needs_a_translation(db, make_tree) -> None:
    """Пустая машинная строка — бессмыслица: статус говорит о наличии текста."""
    project_with_machine_row(db, make_tree)
    unit_id = get_unit(db, "b")["id"]          # b без перевода
    unit_ops.set_status(db, [unit_id], Status.MACHINE)
    assert get_unit(db, "b")["status"] == Status.UNTRANSLATED.value


# --- миграция схемы ---

def test_migration_widens_the_status_check(tmp_path, make_tree) -> None:
    """v5→v6 пересобирает `units` ради CHECK — данные обязаны доехать целыми.

    Список статусов задан CHECK-ограничением, а его SQLite менять не умеет.
    Ограничение стоит того, чтобы его чинить: именно оно ловит опечатку в
    статусе прямо на записи.
    """
    from pdxloc import db as db_mod
    from pdxloc import project

    en = make_tree({"m_l_english.yml": EN}, "en")
    path = tmp_path / "old.pdxproj"
    conn = project.create_project(path, name="Old", src_root=en,
                                  tgt_root=make_tree({}, "ru"))
    scan_project(conn, 1)
    conn.execute("UPDATE units SET ru_text = 'Привет', status = 'translated' "
                 "WHERE key = 'a'")
    before = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
    before_a = conn.execute(
        "SELECT ru_text, status FROM units WHERE key = 'a'").fetchone()[:]

    # откатываем к v5: прежний CHECK без 'machine'
    old = ("'untranslated','auto','translated','reviewed','stale','ignored','custom'")
    conn.execute("ALTER TABLE units RENAME TO units_v5")
    conn.execute(f"""
        CREATE TABLE units (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            key TEXT NOT NULL, en_version TEXT NOT NULL DEFAULT '',
            en_text TEXT, en_hash TEXT, prev_en_text TEXT, ru_text TEXT,
            status TEXT NOT NULL DEFAULT 'untranslated' CHECK (status IN ({old})),
            line_no INTEGER, comment_before TEXT NOT NULL DEFAULT '',
            comment_inline TEXT NOT NULL DEFAULT '',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            en_changed_at TEXT, change_kind TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT,
            UNIQUE(file_id, key))
    """)
    # колонки перечислены поимённо: у нынешней таблицы их больше (v8 дописала
    # кеш замечаний), и «SELECT *» подсунул бы старой схеме лишние значения
    v5_cols = ("id, file_id, key, en_version, en_text, en_hash, prev_en_text, "
               "ru_text, status, line_no, comment_before, comment_inline, "
               "is_deleted, en_changed_at, change_kind, created_at, updated_at")
    conn.execute(f"INSERT INTO units ({v5_cols}) SELECT {v5_cols} FROM units_v5")
    conn.execute("DROP TABLE units_v5")
    conn.execute("UPDATE schema_meta SET value = '5' WHERE key = 'schema_version'")
    conn.commit()
    conn.close()

    again = project.open_project(path, [])
    try:
        assert again.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == str(db_mod.SCHEMA_VERSION)
        assert again.execute("SELECT COUNT(*) FROM units").fetchone()[0] == before
        assert again.execute(
            "SELECT ru_text, status FROM units WHERE key = 'a'").fetchone()[:] \
            == before_a
        # а теперь новый статус принимается
        again.execute("UPDATE units SET status = ? WHERE key = 'a'",
                      (Status.MACHINE.value,))
        assert not again.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        again.close()


def test_unknown_status_is_still_refused(db, make_tree) -> None:
    """Ограничение не ослабили: опечатка в статусе обязана падать на записи."""
    import sqlite3

    import pytest

    project_with_machine_row(db, make_tree)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE units SET status = 'machine_translated' WHERE key = 'a'")


# --- ворота в окне записи ---

def test_export_dialog_keeps_machine_out_by_default(db, make_tree, qtbot) -> None:
    """Единственные ворота наружу, и по умолчанию они закрыты."""
    from pdxloc.gui.export_dialog import ExportDialog

    pid = project_with_machine_row(db, make_tree)
    dialog = ExportDialog(db, pid)
    qtbot.addWidget(dialog)
    assert not dialog.machine_check.isChecked()
    assert not dialog.machine_warning.isVisible()


def test_export_dialog_warns_the_moment_the_tick_goes_on(db, make_tree, qtbot) -> None:
    """Предупреждение стоит там, где принимается решение, а не модалкой потом."""
    from pdxloc.gui.export_dialog import ExportDialog

    pid = project_with_machine_row(db, make_tree)
    dialog = ExportDialog(db, pid)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.machine_check.setChecked(True)
    assert dialog.machine_warning.isVisible()
    assert dialog.machine_warning.text()


def test_export_dialog_says_how_many_machine_rows_there_are(
        db, make_tree, qtbot) -> None:
    """Число видно до решения, а не после записи."""
    from pdxloc.gui.export_dialog import ExportDialog

    pid = project_with_machine_row(db, make_tree)
    dialog = ExportDialog(db, pid)
    qtbot.addWidget(dialog)
    assert "1" in dialog.machine_check.text()


def test_the_tick_is_dead_when_there_is_no_machine_translation(
        db, make_tree, qtbot) -> None:
    from pdxloc.gui.export_dialog import ExportDialog

    en = make_tree({"m_l_english.yml": EN}, "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    scan_project(db, pid)
    dialog = ExportDialog(db, pid)
    qtbot.addWidget(dialog)
    assert not dialog.machine_check.isEnabled()


# --- проверка его видит ---

def test_qa_checks_machine_rows(db, make_tree) -> None:
    """Потерянная подстановка — самое частое, что приносит машинный перевод."""
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Gain $VALUE$"\n'}, "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    scan_project(db, pid)
    db.execute("UPDATE units SET ru_text = 'Получить', status = ? WHERE key = 'a'",
               (Status.MACHINE.value,))
    db.commit()
    codes = [i.code for i in qa.run_qa(db, pid, only_translated=True)]
    assert "dollar_mismatch" in codes


def test_inconsistency_report_ignores_machine_rows(db, make_tree) -> None:
    """«Один оригинал переведён по-разному» — про людей, а не про машину."""
    en = make_tree(
        {"m_l_english.yml": 'l_english:\n a:0 "Gold"\n b:0 "Gold"\n'}, "en")
    pid = make_project(db, en, make_tree({}, "ru"))
    scan_project(db, pid)
    db.execute("UPDATE units SET ru_text='Золото', status=? WHERE key='a'",
               (Status.TRANSLATED.value,))
    db.execute("UPDATE units SET ru_text='Деньги', status=? WHERE key='b'",
               (Status.MACHINE.value,))
    db.commit()
    assert qa.find_inconsistent(db, pid) == {}
