"""Canaries on the critical path: set up a project → scan → translate → write.

The reason is a concrete one. The matching of EN and RU files silently stopped
working for the most ordinary layout of workshop mods, and the application showed
a project of 138 thousand rows with zero translations — while a ready translation
lay right there on the disk. Not a single test fell over: they all checked
particulars, and not one asked the main thing — «and was the translation found?».

Here that is exactly what is checked, over all the layouts that occur in the
wild. The tests are deliberately crude: they are not about details but about the
tool doing its work at all.
"""
from __future__ import annotations

import pytest

from pdxloc import project
from pdxloc.core import tm
from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.scanner import scan_project
from pdxloc.core.statuses import Status

EN = (
    'l_english:\n'
    ' greet:0 "Hello"\n'
    ' bye:0 "Goodbye"\n'
    ' again:0 "Hello"\n'          # a repeat — the auto-substitution is checked with it
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


def layout_flat(root):
    """The roots point straight at the language folders."""
    write(root / "en" / "agot" / "foo_l_english.yml", EN)
    write(root / "ru" / "agot" / "foo_l_russian.yml", RU)
    return root / "en", root / "ru"


def layout_workshop(root):
    """As in the workshop: two mods, the root is the localization folder."""
    write(root / "2962333032" / "localization" / "english" / "agot" / "foo_l_english.yml", EN)
    write(root / "2962803371" / "localization" / "russian" / "agot" / "foo_l_russian.yml", RU)
    return (root / "2962333032" / "localization",
            root / "2962803371" / "localization")


def layout_same_tree(root):
    """The original and the translation in one mod: localization/<language>/…"""
    write(root / "mod" / "localization" / "english" / "foo_l_english.yml", EN)
    write(root / "mod" / "localization" / "russian" / "foo_l_russian.yml", RU)
    return root / "mod" / "localization", root / "mod" / "localization"


def layout_deep(root):
    """The language folder is not the first segment of the path."""
    write(root / "en" / "sub" / "english" / "foo_l_english.yml", EN)
    write(root / "ru" / "sub" / "russian" / "foo_l_russian.yml", RU)
    return root / "en", root / "ru"


LAYOUTS = {
    "папки языка": layout_flat,
    "мастерская: два мода": layout_workshop,
    "один мод": layout_same_tree,
    "язык в глубине пути": layout_deep,
}


@pytest.fixture(params=list(LAYOUTS), ids=list(LAYOUTS))
def scanned(request, tmp_path):
    en_root, ru_root = LAYOUTS[request.param](tmp_path)
    conn = project.create_project(
        tmp_path / "p.pdxproj", name="P", src_root=en_root, tgt_root=ru_root)
    stats = scan_project(conn, 1)
    yield conn, stats
    conn.close()


@pytest.mark.parametrize("layout", ["папки языка", "один мод", "язык в глубине пути"])
def test_the_offered_translation_folder_is_the_real_one(layout, tmp_path) -> None:
    """The window creating a project must not send the translation past the mod.

    The offer used to be a guess by the folder name, and for a mod holding both
    languages in one tree it answered a folder outside the mod. Nothing failed:
    the project simply found no translation and later offered to write there.
    """
    from pdxloc.core import relocate

    en_root, ru_root = LAYOUTS[layout](tmp_path)

    assert relocate.suggest_target_root(en_root) == ru_root


def test_a_translation_in_another_mod_is_not_invented(tmp_path) -> None:
    """Two mods of the workshop: the pack lives elsewhere and cannot be guessed.

    The offer then stays inside the mod being translated — the write belongs
    there — and the pack is pointed at by hand, in «Change translation folder».
    """
    from pdxloc.core import relocate

    en_root, ru_root = layout_workshop(tmp_path)

    offered = relocate.suggest_target_root(en_root)
    assert offered == en_root and offered != ru_root


def test_existing_translation_is_never_lost(scanned) -> None:
    """The main canary: the translation lies on the disk — it is obliged to be found.

    Zero translated with a non-empty translation tree means the matching of files
    is broken, and such a project cannot be worked with.
    """
    conn, _ = scanned
    translated = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL AND ru_text <> ''"
    ).fetchone()[0]
    assert translated > 0, "перевод есть на диске, но проект его не увидел"


def test_translations_land_on_the_right_keys(scanned) -> None:
    conn, _ = scanned
    rows = dict(conn.execute(
        "SELECT key, ru_text FROM units WHERE ru_text IS NOT NULL").fetchall())
    assert rows["greet"] == "Привет"
    assert rows["bye"] == "Пока"


def test_paired_files_are_not_treated_as_orphans(scanned) -> None:
    """An orphaned RU file goes into the archive — that is how a whole translation was lost at once."""
    conn, stats = scanned
    assert stats.files_ru >= stats.files_en
    assert conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0] == 0


def test_memory_is_filled_from_the_translation(scanned) -> None:
    """An empty translation memory = silent hints and no auto-substitution."""
    conn, _ = scanned
    assert [h.ru_text for h in tm.lookup(conn, "Hello")] == ["Привет"]


def test_repeated_string_is_autofilled(scanned) -> None:
    """An exact match with an already translated row is substituted by itself."""
    conn, _ = scanned
    row = conn.execute(
        "SELECT status, ru_text FROM units WHERE key = 'again'").fetchone()
    assert row["ru_text"] == "Привет"
    assert row["status"] == Status.AUTO.value      # «substituted, check it»


def test_nothing_is_left_untranslated_when_everything_matches(scanned) -> None:
    conn, _ = scanned
    left = conn.execute(
        "SELECT COUNT(*) FROM units WHERE status = ?",
        (Status.UNTRANSLATED.value,)).fetchone()[0]
    assert left == 0


def test_export_writes_the_translation_back(scanned, tmp_path) -> None:
    """We close the circle: what was read has to be written back into the mod."""
    conn, _ = scanned
    out = tmp_path / "out_mod"
    export_project(conn, 1, ExportOptions(), out_root=out, backup=False)
    written = list(out.rglob("*_l_russian.yml"))
    assert written, "запись перевода в мод не создала ни одного файла"
    text = written[0].read_text(encoding="utf-8-sig")
    assert "Привет" in text and "Пока" in text


def test_rescan_is_idempotent(scanned) -> None:
    """A repeated scan must neither lose translations nor breed the archive."""
    conn, _ = scanned
    before = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
    scan_project(conn, 1)
    after = conn.execute(
        "SELECT COUNT(*) FROM units WHERE ru_text IS NOT NULL").fetchone()[0]
    assert after == before
    assert conn.execute("SELECT COUNT(*) FROM legacy_translations").fetchone()[0] == 0
