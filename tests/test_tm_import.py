"""Тесты сборки баз памяти переводов и их подключения к проекту."""
from __future__ import annotations

import pytest

from ck3loc import project, settings
from ck3loc.core import tm, tm_import
from ck3loc.core.scanner import scan_project
from ck3loc.core.statuses import Status

VANILLA_EN = ('l_english:\n'
              ' k_hello:0 "Hello"\n'
              ' k_gold:0 "Gold"\n'
              ' k_same:0 "OK"\n'
              ' k_lonely:0 "No translation"\n')
VANILLA_RU = ('l_russian:\n'
              ' k_hello:0 "Привет"\n'
              ' k_gold:0 "Золото"\n'
              ' k_same:0 "OK"\n')


def build_vanilla(tmp_path, make_tree, name="Ваниль CK3"):
    en = make_tree({"vanilla_l_english.yml": VANILLA_EN}, "game_en")
    ru = make_tree({"vanilla_l_russian.yml": VANILLA_RU}, "game_ru")
    out = tmp_path / "Bdd" / "vanilla_EN-RU.ck3tm"
    report = tm_import.build_tm_from_dirs(en, ru, out, name=name, kind="game")
    return out, report


def test_build_from_dirs(tmp_path, make_tree):
    out, report = build_vanilla(tmp_path, make_tree)
    assert out.is_file()
    assert report.files == 1
    assert report.pairs == 2          # k_same (== оригиналу) и k_lonely не в счёт
    assert report.skipped == 2
    meta = project.tm_meta(out)
    assert meta["format"] == "ck3tm"
    assert meta["kind"] == "game"
    assert meta["name"] == "Ваниль CK3"
    assert meta["src_lang"] == "english" and meta["tgt_lang"] == "russian"
    assert meta["entries"] == "2"


def test_sibling_dir_autodetect(tmp_path, make_tree):
    """Указана только папка оригинала — соседняя папка языка находится сама."""
    root = tmp_path / "localization"
    (root / "english").mkdir(parents=True)
    (root / "russian").mkdir(parents=True)
    for path, text in ((root / "english" / "a_l_english.yml", VANILLA_EN),
                       (root / "russian" / "a_l_russian.yml", VANILLA_RU)):
        with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    out = tmp_path / "auto.ck3tm"
    report = tm_import.build_tm_from_dirs(root / "english", None, out, name="Авто")
    assert report.pairs == 2


def test_missing_target_dir(tmp_path, make_tree):
    en = make_tree({"a_l_english.yml": VANILLA_EN}, "en")
    with pytest.raises(FileNotFoundError):
        tm_import.build_tm_from_dirs(en, None, tmp_path / "x.ck3tm", name="X")


def test_attached_db_used_for_lookup(tmp_path, make_tree, monkeypatch):
    """Подключённая база даёт подсказки и автозаполнение в проекте."""
    tm_path, _ = build_vanilla(tmp_path, make_tree)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tm_path.parent)

    en = make_tree({"mod_l_english.yml":
                    'l_english:\n m1:0 "Hello"\n m2:0 "Unique text"\n'}, "en")
    ru = make_tree({}, "ru")
    proj_path = tmp_path / "p.ck3proj"
    conn = project.create_project(proj_path, name="P", src_root=en, tgt_root=ru)
    project.set_tm_sources(conn, [tm_path.name])
    project.attach_tm_sources(conn, project.project_tm_paths(conn))

    hits = tm.lookup(conn, "Hello")
    assert [h.ru_text for h in hits] == ["Привет"]
    assert hits[0].origin == "Ваниль CK3"

    stats = scan_project(conn, 1)
    assert stats.auto_filled == 1
    row = conn.execute("SELECT ru_text, status FROM units WHERE key='m1'").fetchone()
    assert row["ru_text"] == "Привет" and row["status"] == Status.AUTO.value
    assert conn.execute("SELECT ru_text FROM units WHERE key='m2'").fetchone()[0] is None
    conn.close()


def test_own_translation_wins_over_game_db(tmp_path, make_tree, monkeypatch):
    tm_path, _ = build_vanilla(tmp_path, make_tree)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tm_path.parent)
    proj_path = tmp_path / "p.ck3proj"
    conn = project.create_project(proj_path, name="P", src_root="e", tgt_root="r")
    project.set_tm_sources(conn, [tm_path.name])
    project.attach_tm_sources(conn, project.project_tm_paths(conn))

    tm.upsert(conn, "Hello", "Здравствуйте")     # свой перевод
    conn.commit()
    hits = tm.lookup(conn, "Hello")
    assert hits[0].ru_text == "Здравствуйте" and hits[0].origin == "Проект"
    assert {h.ru_text for h in hits} == {"Здравствуйте", "Привет"}
    conn.close()


def test_ambiguous_variants_block_autofill(tmp_path, make_tree, monkeypatch):
    """Если база и проект расходятся в переводе, автозаполнение молчит."""
    tm_path, _ = build_vanilla(tmp_path, make_tree)
    monkeypatch.setattr(settings, "bdd_dir", lambda: tm_path.parent)
    en = make_tree({"mod_l_english.yml": 'l_english:\n m1:0 "Hello"\n'}, "en")
    ru = make_tree({}, "ru")
    conn = project.create_project(
        tmp_path / "p2.ck3proj", name="P", src_root=en, tgt_root=ru)
    project.set_tm_sources(conn, [tm_path.name])
    project.attach_tm_sources(conn, project.project_tm_paths(conn))
    tm.upsert(conn, "Hello", "Здравствуйте")
    conn.commit()
    stats = scan_project(conn, 1)
    assert stats.auto_filled == 0
    assert conn.execute("SELECT status FROM units WHERE key='m1'").fetchone()[0] == \
        Status.UNTRANSLATED.value
    conn.close()


def test_export_project_tm(tmp_path, make_tree):
    en = make_tree({"m_l_english.yml": 'l_english:\n a:0 "Hello"\n b:0 "World"\n'}, "en")
    ru = make_tree({"m_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    conn = project.create_project(tmp_path / "p.ck3proj", name="Мой мод",
                                  src_root=en, tgt_root=ru)
    scan_project(conn, 1)
    out = tmp_path / "share.ck3tm"
    report = tm_import.export_project_tm(conn, out, name="Мой мод EN-RU")
    conn.close()
    assert report.pairs == 1
    meta = project.tm_meta(out)
    assert meta["kind"] == "project-export" and meta["name"] == "Мой мод EN-RU"


def test_list_tm_databases_skips_junk(tmp_path, make_tree, monkeypatch):
    tm_path, _ = build_vanilla(tmp_path, make_tree)
    (tm_path.parent / "broken.ck3tm").write_bytes(b"not a database")
    monkeypatch.setattr(settings, "bdd_dir", lambda: tm_path.parent)
    found = project.list_tm_databases()
    assert [p.name for p, _ in found] == [tm_path.name]
