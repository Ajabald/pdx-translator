"""The root of a project is the `localization` folder, not the language folder inside it.

That is how the mods in the workshop are built: `.../<id>/localization/english/...`
and `.../<id>/localization/russian/...`. Pointing the root at `localization`
itself is the most natural thing to do, and in that case not a single pair used to
be found: the matching changed the language mark only in the name of the file
while leaving the `english/` directory as it was, and looked for
`english/agot/foo_l_russian.yml`. The result was a project of 138 thousand rows
with zero translations.
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


# --- the matching of paths ----------------------------------------------


def test_language_folder_is_mapped_too() -> None:
    assert map_relpath(
        "english/agot/00_glossary_l_english.yml", "english", "russian"
    ) == "russian/agot/00_glossary_l_russian.yml"


def test_mapping_is_reversible() -> None:
    en = "english/agot/00_glossary_l_english.yml"
    ru = map_relpath(en, "english", "russian")
    assert map_relpath(ru, "russian", "english") == en


def test_nested_replace_folder_is_mapped(tmp_path) -> None:
    """The Russian packs have a `localization/replace/<lang>` lying next to it."""
    assert map_relpath(
        "replace/english/agot/foo_l_english.yml", "english", "russian"
    ) == "replace/russian/agot/foo_l_russian.yml"


def test_flat_layout_still_works() -> None:
    """The root already points at a language folder — there is no language in the path, nothing to change."""
    assert map_relpath("agot/foo_l_english.yml", "english", "russian") == \
        "agot/foo_l_russian.yml"


def test_only_whole_segments_are_replaced() -> None:
    """The folder `english_notes` is no language folder, it must not be touched."""
    assert map_relpath(
        "english_notes/foo_l_english.yml", "english", "russian"
    ) == "english_notes/foo_l_russian.yml"


# --- a live scan --------------------------------------------------------


@pytest.fixture
def mods(tmp_path):
    """Two workshop mods: the original and a separate Russian-pack mod."""
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
    """Without this the translation memory stands empty and the auto-substitution keeps quiet."""
    from pdxloc.core import tm

    en_root, ru_root = mods
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="AGOT", src_root=en_root, tgt_root=ru_root)
    scan_project(conn, 1)
    assert [h.ru_text for h in tm.lookup(conn, "Hello")] == ["Привет"]
    conn.close()


def test_no_orphans_when_the_pair_is_found(mods, tmp_path):
    """Every RU file used to count as orphaned and land in the archive."""
    en_root, ru_root = mods
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="AGOT", src_root=en_root, tgt_root=ru_root)
    scan_project(conn, 1)
    archived = conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0]
    assert archived == 0
    conn.close()
