"""Deleting a project file together with its WAL companions.

A project is months of work in one SQLite file. The connection is opened in WAL
mode, so `-wal` and `-shm` live next to it: deleting only the main file is not
enough — the next project with the same name would pick up a foreign journal.
"""
from __future__ import annotations

import sqlite3

import pytest

from pdxloc import project
from pdxloc.core import trash

EN = 'l_english:\n a:0 "Hello"\n'
RU = 'l_russian:\n a:0 "Привет"\n'


@pytest.fixture
def made(tmp_path, make_tree, monkeypatch):
    monkeypatch.setattr(trash, "available", lambda: False)   # in the tests without the recycle bin
    en = make_tree({"m_l_english.yml": EN}, "en")
    ru = make_tree({"m_l_russian.yml": RU}, "ru")
    path = tmp_path / "p.pdxproj"
    conn = project.create_project(path, name="P", src_root=en, tgt_root=ru)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return path


def test_companions_include_wal_files(made) -> None:
    made.with_name(made.name + "-wal").touch()
    made.with_name(made.name + "-shm").touch()
    names = {p.name for p in project.project_companions(made)}
    assert names == {made.name, f"{made.name}-wal", f"{made.name}-shm"}


def test_delete_removes_the_whole_set(made) -> None:
    made.with_name(made.name + "-wal").touch()
    made.with_name(made.name + "-shm").touch()
    removed = project.delete_project_file(made)
    assert len(removed) == 3
    assert not made.exists()
    assert not made.with_name(made.name + "-wal").exists()
    assert not made.with_name(made.name + "-shm").exists()


def test_backups_are_kept_unless_asked(made) -> None:
    """A copy made before a schema migration is the last line of defence, by default it is intact."""
    backup = made.with_name(f"{made.name}.v3.bak")
    backup.touch()
    project.delete_project_file(made)
    assert backup.exists()

    made.touch()
    project.delete_project_file(made, with_backups=True)
    assert not backup.exists()


def test_missing_file_is_not_an_error(tmp_path) -> None:
    assert project.delete_project_file(tmp_path / "нет.pdxproj").removed == []


def test_deletion_past_the_recycle_bin_is_reported(made, monkeypatch) -> None:
    """The recycle bin did not take everything — the caller is obliged to learn of it.

    Windows does not put a file into the recycle bin if it does not fit its quota,
    and a translation project weighs hundreds of megabytes. The delete dialog
    promises the recycle bin, so the refusal is obliged to reach the human instead
    of getting lost inside.
    """
    monkeypatch.setattr(trash, "available", lambda: True)
    monkeypatch.setattr(trash, "_shell_delete", lambda path: False)   # the recycle bin refused

    report = project.delete_project_file(made)

    assert made in report.removed
    assert report.bypassed_trash == report.removed
    assert not made.exists()


def test_the_recycle_bin_leaves_nothing_to_report(made, monkeypatch) -> None:
    """The file went into the recycle bin — there is nothing to warn about."""
    taken: list = []
    monkeypatch.setattr(trash, "available", lambda: True)
    monkeypatch.setattr(trash, "_shell_delete",
                        lambda path: (taken.append(path), path.unlink())[0] is None)

    report = project.delete_project_file(made)

    assert made in report.removed
    assert report.bypassed_trash == []
    assert taken == [made]


def test_open_project_cannot_be_deleted(made) -> None:
    """A busy file is obliged to raise an error, not to be deleted by halves."""
    conn = project.open_project(made)
    try:
        with pytest.raises(OSError):
            project.delete_project_file(made)
        assert made.exists()
    finally:
        conn.close()


def test_deleted_project_stops_being_openable(made) -> None:
    """The file is gone — a read-only connection does not open at all."""
    project.delete_project_file(made)
    with pytest.raises(sqlite3.OperationalError):
        sqlite3.connect(f"file:{made.as_posix()}?mode=ro", uri=True)
