"""An acceptance test on the real BLA trees.

It checks: an import without losses, the statistics, an export semantically
equivalent to the user's current RU tree, and the noise of the checks under the
rule sets.
"""
from __future__ import annotations

import pytest

from pdxloc.core import paradox_yaml, qa, qa_rules
from pdxloc.core.exporter import export_project
from pdxloc.core.models import ExportOptions
from pdxloc.core.paradox_yaml import map_relpath
from pdxloc.core.scanner import LEGACY_MARKER, scan_project

from conftest import REALDATA_EN, REALDATA_RU, realdata_available
from test_scanner import make_project

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not realdata_available(), reason="нет реальных деревьев BLA"),
]

# The reference numbers, pinned down at the first run (2026-07-30)
EXPECTED_UNITS = 5275          # 5277 records − 2 duplicates inside files
EXPECTED_TRANSLATED = 3694     # translated
EXPECTED_AUTO = 4              # filled from the TM at the import
EXPECTED_ARCHIVED = 46         # translations of keys that are not in the original
EXPECTED_MARKERS = 594         # rows with the «ТРЕБУЕТ ПЕРЕВОДА» marker -> untranslated


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    import sqlite3

    from pdxloc.db import init_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    pid = make_project(conn, REALDATA_EN, REALDATA_RU, name="BLA")
    stats = scan_project(conn, pid)
    return conn, pid, stats


def test_import_counts(imported):
    conn, pid, stats = imported
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(status = 'translated') AS translated,
                  SUM(status = 'auto') AS auto
           FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.is_deleted = 0""",
        (pid,),
    ).fetchone()
    assert row["total"] == EXPECTED_UNITS
    assert row["translated"] == EXPECTED_TRANSLATED
    assert row["auto"] == EXPECTED_AUTO
    assert stats.archived == EXPECTED_ARCHIVED
    assert conn.execute(
        "SELECT COUNT(*) FROM legacy_translations").fetchone()[0] == EXPECTED_ARCHIVED
    assert stats.files_en == 30
    assert len(stats.duplicate_keys) == 2


def test_marker_entries_untranslated(imported):
    conn, pid, _ = imported
    # every marker row had to become untranslated (or auto out of the TM)
    marker_count = 0
    for p in REALDATA_RU.rglob("*.yml"):
        if "_l_russian" not in p.name or "_updated" in p.name:
            continue
        lf = paradox_yaml.parse_file(p)
        marker_count += sum(1 for e in lf.entries if LEGACY_MARKER in e.comment_inline)
    assert marker_count == EXPECTED_MARKERS
    # not a single marker must get into the translated ones
    bad = conn.execute(
        """SELECT COUNT(*) FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.status IN ('translated','reviewed')
             AND u.ru_text = u.en_text""",
        (pid,),
    ).fetchone()[0]
    assert bad == 0


def test_export_semantic_equivalence(imported, tmp_path):
    """The translated_only export is equivalent to the old RU tree.

    For every key that (a) is in the EN and (b) is translated in the old tree
    (ru != en, without a marker), the exported text coincides.
    """
    conn, pid, _ = imported
    out = tmp_path / "export"
    report = export_project(conn, pid, ExportOptions(mode="translated_only"), out_root=out)
    # 12 files entirely without translations are not written at all
    assert report.files_written == 18

    checked = 0
    for en_path in REALDATA_EN.rglob("*.yml"):
        if "_l_english" not in en_path.name:
            continue
        rel = en_path.relative_to(REALDATA_EN).as_posix()
        en_keys = {e.key: e for e in paradox_yaml.parse_file(en_path).entries}
        old_ru_path = REALDATA_RU / map_relpath(rel, "english", "russian")
        if not old_ru_path.is_file():
            continue
        old_ru = {e.key: e for e in paradox_yaml.parse_file(old_ru_path).entries}

        # the keys of the old tree that are obliged to get into the export
        expected = {
            key: e.text for key, e in old_ru.items()
            if key in en_keys
            and LEGACY_MARKER not in e.comment_inline
            and e.text and e.text != en_keys[key].text
        }
        new_path = out / map_relpath(rel, "english", "russian")
        if not expected:
            continue
        assert new_path.is_file(), rel
        new_ru = {e.key: e.text for e in paradox_yaml.parse_file(new_path).entries}
        for key, text in expected.items():
            assert key in new_ru, f"{rel}: потерян ключ {key}"
            assert new_ru[key] == text, f"{rel}: текст изменился у {key}"
        checked += len(expected)
    assert checked > 3500   # a massive enough check


# --- the noise of the checks ---------------------------------------------
#
# The numbers are taken off this same tree (2026-08-10) and are kept here and not
# only in the documentation: the setting up of the checks was started for the sake
# of lowering the noise, and the noise is the only property of it that cannot be
# seen on synthetic pairs. The tree is a live one and will move with an update of
# the mod, as `EXPECTED_UNITS` above will; if the numbers changed, check that it
# is the update that is to blame and not a rule.

CUSTOM = qa_rules.CUSTOM        # the built-in values, without a preset
EXPECTED_ISSUES = {"strict": 353, CUSTOM: 149, "ck3_ru": 149, "quiet": 27}
# The main contribution to the «strict» one: the length heuristic, hence it is off by default
EXPECTED_STRICT_LEN_RATIO = 204


def _issues(conn, pid, preset):
    return qa.run_qa(conn, pid,
                     ruleset=qa_rules.resolve({"preset": preset}, locale="ru"))


@pytest.mark.parametrize("preset,expected", sorted(EXPECTED_ISSUES.items()))
def test_issue_count_per_preset(imported, preset, expected):
    conn, pid, _ = imported
    assert len(_issues(conn, pid, preset)) == expected


def test_presets_are_monotonic_on_live_data(imported):
    """The strict one is noisier than the built-in, that one than the recommended, that one than the quiet.

    On synthetics the monotonicity is covered by `test_qa_defaults.py`, but there
    the pairs are picked to fit the rules. Here it is the other way round: the
    rules meet a text nobody picked.
    """
    conn, pid, _ = imported
    counts = {p: len(_issues(conn, pid, p))
              for p in ("strict", CUSTOM, "ck3_ru", "quiet")}
    assert counts["strict"] >= counts[CUSTOM] >= counts["ck3_ru"] >= counts["quiet"]


def test_length_heuristic_is_the_bulk_of_strict_noise(imported):
    conn, pid, _ = imported
    codes = [i.code for i in _issues(conn, pid, "strict")]
    assert codes.count("len_ratio") == EXPECTED_STRICT_LEN_RATIO
    assert "len_ratio" not in qa_rules.resolve().active_ids()


def test_export_bom_and_header(imported, tmp_path):
    conn, pid, _ = imported
    out = tmp_path / "export2"
    export_project(conn, pid, ExportOptions(mode="translated_only"), out_root=out)
    for p in out.rglob("*.yml"):
        raw = p.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), p.name
        assert raw.decode("utf-8-sig").startswith("l_russian:\n"), p.name
