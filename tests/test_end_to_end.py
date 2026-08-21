"""End-to-end scenarios: three paths of a translator whole, from setting up to the write into the mod.

The other tests check the nodes separately; here what matters is that they work
together — a translation survives an update of the mod, a write reads back without
losses, and a rollback returns exactly what was there.
"""
from __future__ import annotations

import pytest

from pdxloc import project as P
from pdxloc.core import fuzzy, loc_import, tm, tm_import, unit_ops
from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.paradox_yaml import parse_file
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

NL = chr(10)

EN_V1 = ('l_english:\n'
         ' greet:0 "Hello, [GetName]!"\n'
         ' bye:0 "Farewell, friend."\n'
         ' tags:0 "[GetTitle]"\n'
         ' long:0 "The bridge must be paid.\\n\\nOr blood will."\n'
         ' gone:0 "This key disappears later"\n')

# the same localisation after an update of the mod: the formatting, the meaning, a new and a deleted key
EN_V2 = ('l_english:\n'
         ' greet:0 "Hello, [GetName]!!"\n'
         ' bye:0 "Farewell, my dear friend."\n'
         ' tags:0 "[GetTitle]"\n'
         ' long:0 "The bridge must be paid.\\n\\nOr blood will."\n'
         ' fresh:0 "Brand new line"\n')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline=NL) as f:
        f.write(text)


@pytest.fixture
def mod(tmp_path):
    """A project on the tree of a mod, five rows, four of them translated."""
    en = tmp_path / "mod" / "localization" / "english"
    write(en / "m_l_english.yml", EN_V1)
    conn = P.create_project(tmp_path / "p.pdxproj", name="Тест",
                            src_root=en, tgt_root=tmp_path / "out")
    scan_project(conn, 1)
    ids = {r["key"]: r["id"] for r in conn.execute("SELECT id, key FROM units")}
    unit_ops.save_ru_text(conn, ids["greet"], "Привет, [GetName]!")
    unit_ops.save_ru_text(conn, ids["bye"], "Прощай, друг.")
    unit_ops.save_ru_text(conn, ids["long"], "Мост должен быть оплачен." + NL + NL + "Или кровь.")
    unit_ops.save_ru_text(conn, ids["gone"], "Этот ключ потом исчезнет")
    yield conn, tmp_path, en, ids
    conn.close()


def test_translate_from_scratch_and_write_to_mod(mod):
    """Path 1: translate from scratch and write into the mod."""
    conn, tmp_path, _en, _ids = mod
    out = tmp_path / "out"

    assert conn.execute("SELECT status FROM units WHERE key='tags'").fetchone()[0] \
        == Status.IGNORED.value, "строка из одной разметки не требует перевода"
    assert tm.lookup(conn, "Farewell, friend.")[0].ru_text == "Прощай, друг."

    report = export_project(conn, 1, ExportOptions(), out_root=out,
                            backup_root=tmp_path / "bak")
    assert (report.files_written, report.keys_written) == (1, 4)

    written = out / "m_l_russian.yml"
    assert written.read_bytes().startswith(b"\xef\xbb\xbf"), "игра читает только файлы с BOM"
    lf = parse_file(written)
    assert lf.language == "russian" and lf.warnings == []
    texts = {e.key: e.text for e in lf.entries}
    assert texts["long"] == "Мост должен быть оплачен.\\n\\nИли кровь."

    stats = scan_project(conn, 1)
    assert (stats.new, stats.ru_conflicts) == (0, 0), "повторный скан ничего не выдумывает"


def test_existing_translation_is_picked_up(tmp_path):
    """Path 2: a ready translation already lies next to it."""
    en = tmp_path / "mod" / "localization" / "english"
    ru = tmp_path / "mod" / "localization" / "russian"
    write(en / "m_l_english.yml", 'l_english:\n a:0 "Hello"\n b:0 "World"\n')
    write(ru / "m_l_russian.yml", 'l_russian:\n a:0 "Привет"\n b:0 "World"\n old:0 "Осиротевший"\n')

    conn = P.create_project(tmp_path / "p.pdxproj", name="Готовый", src_root=en, tgt_root=ru)
    try:
        scan_project(conn, 1)
        got = {r["key"]: r["status"] for r in conn.execute("SELECT key, status FROM units")}
        assert got["a"] == Status.TRANSLATED.value
        # a coincidence with the original is a lawful translation (names, numbers),
        # but only because the file holds at least one real one
        assert got["b"] == Status.TRANSLATED.value
        assert conn.execute(
            "SELECT COUNT(*) FROM legacy_translations WHERE key='old'").fetchone()[0] == 1
    finally:
        conn.close()


def test_copy_of_source_is_not_a_translation(tmp_path):
    en = tmp_path / "mod" / "localization" / "english"
    ru = tmp_path / "mod" / "localization" / "russian"
    write(en / "c_l_english.yml", 'l_english:\n a:0 "Hello"\n b:0 "World"\n')
    write(ru / "c_l_russian.yml", 'l_russian:\n a:0 "Hello"\n b:0 "World"\n')

    conn = P.create_project(tmp_path / "p.pdxproj", name="Копия", src_root=en, tgt_root=ru)
    try:
        scan_project(conn, 1)
        statuses = {r["status"] for r in conn.execute("SELECT status FROM units")}
        assert statuses == {Status.UNTRANSLATED.value}
    finally:
        conn.close()


def test_mod_update_keeps_translations(mod):
    """Path 3: an update of the mod has come out."""
    conn, _tmp, en, ids = mod
    write(en / "m_l_english.yml", EN_V2)

    scan_project(conn, 1)

    rows = {r["key"]: r for r in conn.execute(
        "SELECT key, status, change_kind, ru_text, prev_en_text, is_deleted FROM units")}
    assert rows["greet"]["status"] == Status.STALE.value
    assert rows["greet"]["change_kind"] == "cosmetic"
    assert rows["greet"]["ru_text"] == "Привет, [GetName]!", "перевод обязан пережить обновление"
    assert rows["greet"]["prev_en_text"] == "Hello, [GetName]!"
    assert rows["bye"]["change_kind"] == "meaningful"
    assert rows["fresh"]["status"] == Status.UNTRANSLATED.value
    assert rows["gone"]["is_deleted"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM legacy_translations WHERE key='gone'").fetchone()[0] == 1
    assert len(unit_ops.source_history(conn, ids["greet"])) == 2

    batch = unit_ops.new_batch_id()
    assert unit_ops.actualize(conn, unit_ops.cosmetic_stale_ids(conn, 1), batch_id=batch) == 1
    assert conn.execute("SELECT status FROM units WHERE key='greet'").fetchone()[0] \
        == Status.TRANSLATED.value
    unit_ops.undo_batch(conn, batch)
    assert conn.execute("SELECT status FROM units WHERE key='greet'").fetchone()[0] \
        == Status.STALE.value


def test_memory_base_gives_similar_lines(mod, tmp_path):
    """The database of the main mod prompts similar rows to a submod."""
    conn, _tmp, _en, _ids = mod
    other = tmp_path / "mod2" / "localization"
    write(other / "english" / "b_l_english.yml",
          'l_english:\n x:0 "The bridge must be paid."\n y:0 "The bridge must be repaired."\n')
    write(other / "russian" / "b_l_russian.yml",
          'l_russian:\n x:0 "Мост должен быть оплачен."\n y:0 "Мост должен быть починен."\n')

    best, _ = tm_import.resolve_target_dir(other / "english", tmp_path / "mod2",
                                           "english", "russian")
    assert best == other / "russian"
    base = tmp_path / "Bdd" / "mod_english-russian.pdxtm"
    assert tm_import.build_tm_from_dirs(other / "english", best, base, name="Мод").pairs == 2

    P.attach_tm_sources(conn, [base])
    hits = fuzzy.lookup_similar(conn, "The bridge must be repaid.")
    assert hits and all(0.6 <= h.score <= 1.0 for h in hits)
    assert any("Мост" in h.ru_text for h in hits)
    assert len(fuzzy.concordance(conn, "bridge")) >= 2


def test_import_from_mod_and_undo(mod, tmp_path):
    """Somebody else's translation is accepted in a batch and taken off by one command."""
    conn, _tmp, _en, _ids = mod
    other = tmp_path / "other"
    write(other / "m_l_russian.yml",
          'l_russian:\n greet:0 "Здравствуй, [GetName]!"\n fresh:0 "Совсем новая строка"\n')
    before = conn.execute("SELECT ru_text FROM units WHERE key='greet'").fetchone()[0]

    preview = loc_import.import_translations(conn, 1, other, dry_run=True)
    assert conn.execute("SELECT ru_text FROM units WHERE key='greet'").fetchone()[0] == before
    assert preview.skipped_existing == 1, "занятые строки без перезаписи не трогаем"

    batch = unit_ops.new_batch_id()
    report = loc_import.import_translations(
        conn, 1, other, loc_import.ImportOptions(overwrite=True), batch_id=batch)
    assert report.imported == 1        # fresh will appear only after an update of the mod
    unit_ops.undo_batch(conn, batch)
    assert conn.execute("SELECT ru_text FROM units WHERE key='greet'").fetchone()[0] == before


def test_rewrite_makes_backup(mod, tmp_path):
    conn, _tmp, _en, ids = mod
    out, bak = tmp_path / "out", tmp_path / "bak"
    export_project(conn, 1, ExportOptions(), out_root=out, backup_root=bak)

    unit_ops.save_ru_text(conn, ids["bye"], "Прощай, дорогой друг.")
    report = export_project(conn, 1, ExportOptions(), out_root=out, backup_root=bak)

    assert report.backup_dir is not None
    from pathlib import Path
    snapshot = Path(report.backup_dir) / "m_l_russian.yml"
    assert "Прощай, друг." in snapshot.read_text(encoding="utf-8-sig")
