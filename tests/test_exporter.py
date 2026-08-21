"""Tests of the exporter."""
from __future__ import annotations

from pathlib import Path

from pdxloc.core import paradox_yaml
from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.scanner import scan_project

from test_scanner import make_project

EN = 'l_english:\n#Comment\n greet:0 "Hello"\n bye:0 "Goodbye"\n stale_key:0 "Changed"\n'
RU = 'l_russian:\n greet:0 "Привет"\n stale_key:0 "Старый перевод"\n'


def setup_project(db, make_tree):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": RU}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    return pid


def test_translated_only(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    out = tmp_path / "out"
    report = export_project(db, pid, ExportOptions(mode="translated_only"), out_root=out)
    assert report.files_written == 1
    assert report.keys_written == 2
    assert report.keys_skipped == 1
    lf = paradox_yaml.parse_file(out / "mod_l_russian.yml")
    assert lf.language == "russian"
    keys = {e.key: e.text for e in lf.entries}
    assert keys == {"greet": "Привет", "stale_key": "Старый перевод"}


def test_all_fallback_en(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    out = tmp_path / "out"
    report = export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)
    assert report.keys_written == 3
    assert report.keys_fallback_en == 1
    keys = {e.key: e.text for e in paradox_yaml.parse_file(out / "mod_l_russian.yml").entries}
    assert keys["bye"] == "Goodbye"     # a fallback to EN


def test_bom_and_header(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(), out_root=out)
    raw = (out / "mod_l_russian.yml").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").startswith("l_russian:\n")


def test_comments_preserved_markers_dropped(db, make_tree, tmp_path):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml":
                    'l_russian:\n greet:0 "Привет" # !!! ТРЕБУЕТ ПЕРЕВОДА\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)
    text = (out / "mod_l_russian.yml").read_text(encoding="utf-8-sig")
    assert "#Comment" in text                  # the comment from EN is kept
    entries = {e.key: e for e in paradox_yaml.parse_file(out / "mod_l_russian.yml").entries}
    # greet is marked with a marker in the input file -> it counts as untranslated,
    # goes into the export as the original and gets a fresh marker
    assert entries["greet"].text == "Hello"
    assert "ТРЕБУЕТ ПЕРЕВОДА" in entries["greet"].comment_inline
    # the marker is set by the fact of being untranslated, not copied from the input
    assert all("ТРЕБУЕТ ПЕРЕВОДА" in e.comment_inline for e in entries.values())


def test_stale_excluded_when_disabled(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    # we edit the EN -> stale_key will become stale
    make_tree({"mod_l_english.yml":
               EN.replace('"Changed"', '"Changed again"')}, "en")
    scan_project(db, pid)
    out = tmp_path / "out"
    report = export_project(
        db, pid, ExportOptions(mode="translated_only", include_stale=False), out_root=out)
    keys = {e.key for e in paradox_yaml.parse_file(out / "mod_l_russian.yml").entries}
    assert "stale_key" not in keys
    report2 = export_project(
        db, pid, ExportOptions(mode="translated_only", include_stale=True),
        out_root=tmp_path / "out2")
    out2 = tmp_path / "out2" / "mod_l_russian.yml"
    keys2 = {e.key for e in paradox_yaml.parse_file(out2).entries}
    assert "stale_key" in keys2
    # the report is what a human sees after the write; it is obliged to agree with the file
    assert report.keys_written == len(keys)
    assert report2.keys_written == len(keys2) == len(keys) + 1


def test_orphans_not_exported(db, make_tree, tmp_path):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({
        "mod_l_russian.yml": RU.rstrip() + '\n orphan_key:0 "Сирота"\n',
        "extra_l_russian.yml": 'l_russian:\n lonely:0 "Одинокий"\n',
    }, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)
    keys = {e.key for e in paradox_yaml.parse_file(out / "mod_l_russian.yml").entries}
    assert "orphan_key" not in keys
    assert not (out / "extra_l_russian.yml").exists()


def test_export_respects_en_order(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)
    keys = [e.key for e in paradox_yaml.parse_file(out / "mod_l_russian.yml").entries]
    assert keys == ["greet", "bye", "stale_key"]   # the order of the EN file


def test_interrupted_write_leaves_the_previous_file_whole(db, make_tree, tmp_path, monkeypatch):
    """An interrupted write leaves no truncated file in the mod.

    A localisation file is overwritten in place, while the game reads every `*.yml`
    in the folder in a row: a stump it will load as a real one and show the player
    half a translation. That is why we write next to it and swap the ready one in.
    """
    pid = setup_project(db, make_tree)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(), out_root=out)
    target = out / "mod_l_russian.yml"
    before = target.read_bytes()

    db.execute("UPDATE units SET ru_text = 'Здравствуй' WHERE key = 'greet'")
    db.commit()

    def die(*args, **kwargs):
        raise OSError("диск отвалился на середине")

    monkeypatch.setattr("pdxloc.core.exporter.os.replace", die)
    try:
        export_project(db, pid, ExportOptions(), out_root=out)
    except OSError:
        pass

    assert target.read_bytes() == before        # the former version is intact


# --- the backups of overwritten files ---

def test_backup_keeps_previous_version(db, make_tree, tmp_path):
    """Overwriting a changed file leaves the former version in a backup."""
    pid = setup_project(db, make_tree)
    out, backups = tmp_path / "out", tmp_path / "backups"
    export_project(db, pid, ExportOptions(), out_root=out, backup_root=backups)
    before = (out / "mod_l_russian.yml").read_bytes()

    db.execute("UPDATE units SET ru_text = 'Здравствуй' WHERE key = 'greet'")
    db.commit()
    report = export_project(db, pid, ExportOptions(), out_root=out, backup_root=backups)

    assert report.files_written == 1
    assert report.backup_dir is not None
    copy = Path(report.backup_dir) / "mod_l_russian.yml"
    assert copy.read_bytes() == before
    assert "Здравствуй" in (out / "mod_l_russian.yml").read_text(encoding="utf-8-sig")


def test_no_backup_when_file_unchanged(db, make_tree, tmp_path):
    """The file was not overwritten — there is nothing to copy, no snapshot folder is set up."""
    pid = setup_project(db, make_tree)
    out, backups = tmp_path / "out", tmp_path / "backups"
    export_project(db, pid, ExportOptions(), out_root=out, backup_root=backups)
    report = export_project(db, pid, ExportOptions(), out_root=out, backup_root=backups)

    assert report.files_unchanged == 1
    assert report.backup_dir is None
    assert not backups.exists()


def test_backup_disabled(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    out, backups = tmp_path / "out", tmp_path / "backups"
    export_project(db, pid, ExportOptions(), out_root=out, backup_root=backups)
    db.execute("UPDATE units SET ru_text = 'Здравствуй' WHERE key = 'greet'")
    db.commit()
    report = export_project(db, pid, ExportOptions(), out_root=out,
                            backup=False, backup_root=backups)

    assert report.files_written == 1
    assert report.backup_dir is None
    assert not backups.exists()


def test_backups_pruned(tmp_path):
    """We keep only the latest snapshots — a backup does not turn into an archive of versions."""
    from pdxloc.core.exporter import _prune_backups

    project_dir = tmp_path / "test"
    for day in range(1, 9):
        (project_dir / f"2026-08-{day:02d}_120000").mkdir(parents=True)
    _prune_backups(project_dir, keep=3)

    assert [p.name for p in sorted(project_dir.iterdir())] == [
        "2026-08-06_120000", "2026-08-07_120000", "2026-08-08_120000"]


def test_pruning_does_not_touch_foreign_folders(tmp_path):
    """A foreign folder in `backups/<project>/` is no snapshot, and we have no right to delete it.

    Any subfolder used to count as a snapshot, and `rmtree` does not ask: a folder
    put there by a human went away together with the old snapshots silently. Our
    own can be told from a foreign one exactly — a snapshot has a strict name with
    the time in it.
    """
    from pdxloc.core.exporter import _prune_backups

    project_dir = tmp_path / "test"
    for day in range(1, 5):
        (project_dir / f"2026-08-{day:02d}_120000").mkdir(parents=True)
    foreign = project_dir / "мои заметки"
    foreign.mkdir()
    (foreign / "важное.txt").write_text("не удаляй", encoding="utf-8")
    # it looks like a snapshot but is not: it does not fit the template
    almost = project_dir / "2026-08-01"
    almost.mkdir()

    _prune_backups(project_dir, keep=1)

    assert foreign.is_dir(), "чужая папка снесена"
    assert (foreign / "важное.txt").read_text(encoding="utf-8") == "не удаляй"
    assert almost.is_dir(), "папка, лишь похожая на снимок, снесена"
    # while our own old snapshots are taken away after all, otherwise the cleaning stopped working
    assert [p.name for p in sorted(project_dir.iterdir())
            if p.name[:4].isdigit() and "_" in p.name] == ["2026-08-04_120000"]


def test_a_snapshot_name_matches_what_pruning_looks_for(tmp_path):
    """The name of a snapshot and the template of the cleaning are obliged to agree.

    They are at different ends of the module, and parting ways costs them nothing:
    change the format of the name — and the cleaning stops recognising its own
    snapshots and will pile them up forever, breaking nothing noticeably at that.
    """
    from datetime import datetime

    from pdxloc.core import exporter

    name = datetime.now().strftime(exporter.SNAPSHOT_NAME)
    assert exporter._SNAPSHOT_RE.match(name), (
        f"снимок называется {name}, а чистка ищет другое")
