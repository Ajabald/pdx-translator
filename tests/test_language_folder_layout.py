"""Корень проекта — папка `localization`, а не папка языка внутри неё.

Так устроены моды в мастерской: `.../<id>/localization/english/...` и
`.../<id>/localization/russian/...`. Указать корнем именно `localization` —
самое естественное действие, и раньше в этом случае не находилось ни одной
пары: сопоставление меняло метку языка только в имени файла, а каталог
`english/` оставляло как есть и искало `english/agot/foo_l_russian.yml`.
Результат — проект на 138 тысяч строк с нулём переводов.
"""
from __future__ import annotations

import pytest

from pdxloc import project
from pdxloc.core.paradox_yaml import map_relpath
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

EN = (
    'l_english:\n'
    ' greet:0 "Hello"\n'
    ' bye:0 "Goodbye"\n'
)
RU = (
    'l_russian:\n'
    ' greet:0 "Привет"\n'
    ' bye:0 "Пока"\n'
)


def write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(text)


# --- сопоставление путей ------------------------------------------------


def test_language_folder_is_mapped_too() -> None:
    assert map_relpath(
        "english/agot/00_glossary_l_english.yml", "english", "russian"
    ) == "russian/agot/00_glossary_l_russian.yml"


def test_mapping_is_reversible() -> None:
    en = "english/agot/00_glossary_l_english.yml"
    ru = map_relpath(en, "english", "russian")
    assert map_relpath(ru, "russian", "english") == en


def test_nested_replace_folder_is_mapped(tmp_path) -> None:
    """У русификаторов рядом лежит `localization/replace/<lang>`."""
    assert map_relpath(
        "replace/english/agot/foo_l_english.yml", "english", "russian"
    ) == "replace/russian/agot/foo_l_russian.yml"


def test_flat_layout_still_works() -> None:
    """Корень уже указан на папку языка — в пути языка нет, менять нечего."""
    assert map_relpath("agot/foo_l_english.yml", "english", "russian") == \
        "agot/foo_l_russian.yml"


def test_only_whole_segments_are_replaced() -> None:
    """Папка `english_notes` — не папка языка, трогать её нельзя."""
    assert map_relpath(
        "english_notes/foo_l_english.yml", "english", "russian"
    ) == "english_notes/foo_l_russian.yml"


# --- живое сканирование -------------------------------------------------


@pytest.fixture
def mods(tmp_path):
    """Два мода мастерской: оригинал и отдельный мод-русификатор."""
    en_root = tmp_path / "2962333032" / "localization"
    ru_root = tmp_path / "2962803371" / "localization"
    write(en_root / "english" / "agot" / "00_glossary_l_english.yml", EN)
    write(ru_root / "russian" / "agot" / "00_glossary_l_russian.yml", RU)
    return en_root, ru_root


def test_scan_finds_translations_when_root_is_the_localization_folder(mods, tmp_path):
    en_root, ru_root = mods
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="AGOT", src_root=en_root, tgt_root=ru_root)
    stats = scan_project(conn, 1)

    assert stats.files_en == 1
    assert stats.files_ru == 1, "RU-файл не нашёл пары — сопоставление путей сломано"

    rows = dict(conn.execute(
        "SELECT key, ru_text FROM units WHERE ru_text IS NOT NULL").fetchall())
    assert rows == {"greet": "Привет", "bye": "Пока"}
    untranslated = conn.execute(
        "SELECT COUNT(*) FROM units WHERE status = ?",
        (Status.UNTRANSLATED.value,)).fetchone()[0]
    assert untranslated == 0
    conn.close()


def test_translated_rows_feed_the_project_memory(mods, tmp_path):
    """Без этого пустует память переводов, и автоподстановка молчит."""
    from pdxloc.core import tm

    en_root, ru_root = mods
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="AGOT", src_root=en_root, tgt_root=ru_root)
    scan_project(conn, 1)
    assert [h.ru_text for h in tm.lookup(conn, "Hello")] == ["Привет"]
    conn.close()


def test_no_orphans_when_the_pair_is_found(mods, tmp_path):
    """Раньше каждый RU-файл считался осиротевшим и попадал в архив."""
    en_root, ru_root = mods
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="AGOT", src_root=en_root, tgt_root=ru_root)
    scan_project(conn, 1)
    archived = conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0]
    assert archived == 0
    conn.close()
