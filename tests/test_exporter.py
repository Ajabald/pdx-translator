"""Тесты экспортёра."""
from __future__ import annotations

from pathlib import Path

from ck3loc.core import paradox_yaml
from ck3loc.core.exporter import export_project
from ck3loc.core.models import ExportOptions
from ck3loc.core.scanner import scan_project

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
    assert keys["bye"] == "Goodbye"     # fallback на EN


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
    assert "#Comment" in text                  # комментарий из EN сохранён
    entries = {e.key: e for e in paradox_yaml.parse_file(out / "mod_l_russian.yml").entries}
    # greet помечен маркером во входном файле -> считается непереведённым,
    # уходит в экспорт оригиналом и получает свежий маркер
    assert entries["greet"].text == "Hello"
    assert "ТРЕБУЕТ ПЕРЕВОДА" in entries["greet"].comment_inline
    # маркер ставится по факту непереведённости, а не копируется из входа
    assert all("ТРЕБУЕТ ПЕРЕВОДА" in e.comment_inline for e in entries.values())


def test_stale_excluded_when_disabled(db, make_tree, tmp_path):
    pid = setup_project(db, make_tree)
    # правим EN -> stale_key станет stale
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
    keys2 = {e.key for e in paradox_yaml.parse_file(tmp_path / "out2" / "mod_l_russian.yml").entries}
    assert "stale_key" in keys2


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
    assert keys == ["greet", "bye", "stale_key"]   # порядок EN-файла


# --- резервные копии перезаписываемых файлов ---

def test_backup_keeps_previous_version(db, make_tree, tmp_path):
    """Перезапись изменившегося файла оставляет прежнюю версию в бэкапе."""
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
    """Файл не переписывался — копировать нечего, папка снимка не заводится."""
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
    """Держим только последние снимки — бэкап не превращается в архив версий."""
    from ck3loc.core.exporter import _prune_backups

    project_dir = tmp_path / "test"
    for day in range(1, 9):
        (project_dir / f"2026-08-{day:02d}_120000").mkdir(parents=True)
    _prune_backups(project_dir, keep=3)

    assert [p.name for p in sorted(project_dir.iterdir())] == [
        "2026-08-06_120000", "2026-08-07_120000", "2026-08-08_120000"]
