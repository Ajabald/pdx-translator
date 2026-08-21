"""The .pdxtm schema of version 2: the index of similar rows inside the database.

The index lives in the file of the database and is not built at the opening of a
project: over the vanilla localisation (244 thousand records) the building takes
half a second, while keeping such an index in memory would cost 94 MB and three
seconds at every start.
"""
from __future__ import annotations

import sqlite3

import pytest

from pdxloc.core import tm, tm_import
from pdxloc.project import tm_meta

EN = 'l_english:\n a:0 "The Bridge Must Be Paid"\n b:0 "Winter is coming"\n'
RU = 'l_russian:\n a:0 "Мост должен быть оплачен"\n b:0 "Зима близко"\n'


@pytest.fixture
def loc_tree(tmp_path):
    loc = tmp_path / "localization"
    for lang, text in (("english", EN), ("russian", RU)):
        d = loc / lang
        d.mkdir(parents=True)
        with open(d / f"mod_l_{lang}.yml", "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    return loc


def _fts_rows(path) -> int:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT COUNT(*) FROM tm_fts").fetchone()[0]
    finally:
        conn.close()


def test_new_base_has_index(loc_tree, tmp_path):
    out = tmp_path / "mod.pdxtm"
    report = tm_import.build_tm_from_dirs(
        loc_tree / "english", loc_tree / "russian", out, name="Мод")

    assert report.pairs == 2
    assert tm_meta(out)["schema_version"] == str(tm_import.TM_SCHEMA_VERSION)
    assert _fts_rows(out) == 2      # the index is filled, not merely created


def test_index_finds_by_word(loc_tree, tmp_path):
    out = tmp_path / "mod.pdxtm"
    tm_import.build_tm_from_dirs(loc_tree / "english", loc_tree / "russian", out, name="Мод")

    conn = sqlite3.connect(f"file:{out.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT e.en_text FROM tm_fts f JOIN tm_entries e ON e.id = f.rowid "
            "WHERE tm_fts MATCH ?", ('"bridge"',)).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["The Bridge Must Be Paid"]


def test_project_export_base_has_index(db, tmp_path):
    """A database exported out of a project has to prompt similar rows as well."""
    from pdxloc.core.tm_import import export_project_tm

    db.execute("INSERT INTO projects (id, name, en_root, ru_root) VALUES (1, 'P', 'e', 'r')")
    db.execute("INSERT INTO files (id, project_id, rel_path) VALUES (1, 1, 'm.yml')")
    db.execute(
        "INSERT INTO units (file_id, key, en_text, ru_text, en_hash, status) "
        "VALUES (1, 'k', 'Winter is coming', 'Зима близко', ?, 'translated')",
        (tm.en_hash("Winter is coming"),))
    db.commit()

    out = tmp_path / "project.pdxtm"
    report = export_project_tm(db, out, name="Проект")

    assert report.pairs == 1
    assert _fts_rows(out) == 1


def _v1_base(path):
    """A database of the former schema — such lie with users after past versions."""
    conn = sqlite3.connect(str(path))
    conn.executescript(tm_import.TM_DDL)
    conn.executemany(
        "INSERT INTO tm_meta (key, value) VALUES (?, ?)",
        [("format", "pdxtm"), ("schema_version", "1"), ("name", "Старая"),
         ("src_lang", "english"), ("tgt_lang", "russian"), ("kind", "import")])
    conn.executemany(
        "INSERT INTO tm_entries (en_hash, en_text, ru_text, source) VALUES (?, ?, ?, 'import')",
        [(tm.en_hash(en), en, ru) for en, ru in
         [("The Bridge Must Be Paid", "Мост должен быть оплачен"),
          ("Winter is coming", "Зима близко")]])
    conn.commit()
    conn.close()
    return path


def test_build_index_on_old_base(tmp_path):
    old = _v1_base(tmp_path / "old.pdxtm")
    assert tm_meta(old)["schema_version"] == "1"

    assert tm_import.build_fts_index(old) == 2

    assert tm_meta(old)["schema_version"] == "2"
    assert _fts_rows(old) == 2


def test_build_index_is_idempotent(tmp_path):
    old = _v1_base(tmp_path / "old.pdxtm")
    tm_import.build_fts_index(old)
    size = old.stat().st_size

    assert tm_import.build_fts_index(old) == 2      # a repeat neither spoils nor grows the file

    assert _fts_rows(old) == 2
    assert old.stat().st_size == size


def test_index_matches_entries_after_rebuild(loc_tree, tmp_path):
    """An index with external content does not refresh itself on inserts — we check
    that the building of a database does not leave it behind the table."""
    out = tmp_path / "mod.pdxtm"
    tm_import.build_tm_from_dirs(loc_tree / "english", loc_tree / "russian", out, name="Мод")
    conn = sqlite3.connect(f"file:{out.as_posix()}?mode=ro", uri=True)
    try:
        entries = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
        indexed = conn.execute("SELECT COUNT(*) FROM tm_fts").fetchone()[0]
    finally:
        conn.close()
    assert entries == indexed
