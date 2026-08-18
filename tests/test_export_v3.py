"""Тесты v3-M3: язык перевода из проекта, trailing, пропуск неизменных файлов."""
from __future__ import annotations

from pdxloc.core import paradox_yaml
from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.paradox_yaml import map_relpath
from pdxloc.core.scanner import scan_project

EN = 'l_english:\n#Заголовок раздела\n a:0 "Hello"\n b:0 "World"\n# хвост файла\n'


def make_french_project(db, en_root, ru_root, name="fr"):
    cur = db.execute(
        "INSERT INTO projects (name, en_root, ru_root, src_lang, tgt_lang) "
        "VALUES (?, ?, ?, 'english', 'french')", (name, str(en_root), str(ru_root)))
    db.commit()
    return cur.lastrowid


def test_map_relpath_any_languages():
    assert map_relpath("a_l_english.yml", "english", "french") == "a_l_french.yml"
    assert map_relpath("dir/x_l_english_MOD.yml", "english", "simp_chinese") == \
        "dir/x_l_simp_chinese_MOD.yml"
    # каталог языка тоже меняется: моды мастерской лежат как
    # localization/<язык>/…, и корнем указывают саму localization
    assert map_relpath("english/x_l_english.yml", "english", "french") == \
        "french/x_l_french.yml"
    # но только целым сегментом — english_notes не папка языка
    assert map_relpath("english_notes/x_l_english.yml", "english", "french") == \
        "english_notes/x_l_french.yml"


def test_french_export_names_and_header(db, make_tree, tmp_path):
    en = make_tree({"mod_l_english.yml": EN}, "en")
    fr = make_tree({"mod_l_french.yml": 'l_french:\n a:0 "Bonjour"\n'}, "fr")
    pid = make_french_project(db, en, fr)
    scan_project(db, pid)
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(mode="translated_only"), out_root=out)
    target = out / "mod_l_french.yml"
    assert target.is_file()
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8-sig").startswith("l_french:\n")
    lf = paradox_yaml.parse_file(target)
    assert lf.language == "french"
    assert {e.key: e.text for e in lf.entries} == {"a": "Bonjour"}


def test_trailing_preserved(db, make_tree, tmp_path):
    from test_scanner import make_project

    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    assert db.execute("SELECT trailing FROM files").fetchone()[0].strip() == "# хвост файла"
    out = tmp_path / "out"
    export_project(db, pid, ExportOptions(mode="all_fallback_en"), out_root=out)
    text = (out / "mod_l_russian.yml").read_text(encoding="utf-8-sig")
    assert "# хвост файла" in text
    assert "#Заголовок раздела" in text


def test_unchanged_file_not_rewritten(db, make_tree, tmp_path):
    from test_scanner import make_project

    en = make_tree({"mod_l_english.yml": EN}, "en")
    ru = make_tree({"mod_l_russian.yml": 'l_russian:\n a:0 "Привет"\n'}, "ru")
    pid = make_project(db, en, ru)
    scan_project(db, pid)
    out = tmp_path / "out"
    r1 = export_project(db, pid, ExportOptions(mode="translated_only"), out_root=out)
    assert r1.files_written == 1 and r1.files_unchanged == 0
    target = out / "mod_l_russian.yml"
    mtime = target.stat().st_mtime_ns

    r2 = export_project(db, pid, ExportOptions(mode="translated_only"), out_root=out)
    assert r2.files_written == 0 and r2.files_unchanged == 1
    assert target.stat().st_mtime_ns == mtime      # файл не тронут

    # правка перевода -> файл снова пишется
    db.execute("UPDATE units SET ru_text = 'Здравствуй' WHERE key = 'a'")
    db.commit()
    r3 = export_project(db, pid, ExportOptions(mode="translated_only"), out_root=out)
    assert r3.files_written == 1 and r3.files_unchanged == 0


def test_scan_uses_project_languages(db, make_tree):
    """Дерево перевода ищется по языку проекта, а не по «russian»."""
    en = make_tree({"mod_l_english.yml": EN}, "en")
    fr = make_tree({
        "mod_l_french.yml": 'l_french:\n a:0 "Bonjour"\n',
        "mod_l_russian.yml": 'l_russian:\n a:0 "Привет"\n',   # чужой язык — игнорируем
    }, "fr")
    pid = make_french_project(db, en, fr)
    scan_project(db, pid)
    row = db.execute("SELECT ru_text FROM units WHERE key = 'a'").fetchone()
    assert row["ru_text"] == "Bonjour"
