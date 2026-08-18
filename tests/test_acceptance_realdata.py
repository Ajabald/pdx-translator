"""Приёмочный тест на реальных деревьях BLA.

Проверяет: импорт без потерь, статистику, экспорт с семантической
эквивалентностью текущему RU-дереву пользователя и шум проверок по наборам
правил.
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

# Эталонные числа, зафиксированы при первом прогоне (2026-07-30)
EXPECTED_UNITS = 5275          # 5277 записей − 2 внутрифайловых дубликата
EXPECTED_TRANSLATED = 3694     # переведено (translated)
EXPECTED_AUTO = 4              # заполнено из TM при импорте
EXPECTED_ARCHIVED = 46         # переводы ключей, которых нет в оригинале
EXPECTED_MARKERS = 594         # строк с маркером «ТРЕБУЕТ ПЕРЕВОДА» -> untranslated


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
    # все маркерные строки должны были стать untranslated (или auto из TM)
    marker_count = 0
    for p in REALDATA_RU.rglob("*.yml"):
        if "_l_russian" not in p.name or "_updated" in p.name:
            continue
        lf = paradox_yaml.parse_file(p)
        marker_count += sum(1 for e in lf.entries if LEGACY_MARKER in e.comment_inline)
    assert marker_count == EXPECTED_MARKERS
    # ни один маркер не должен попасть в переведённые
    bad = conn.execute(
        """SELECT COUNT(*) FROM units u JOIN files f ON f.id = u.file_id
           WHERE f.project_id = ? AND u.status IN ('translated','reviewed')
             AND u.ru_text = u.en_text""",
        (pid,),
    ).fetchone()[0]
    assert bad == 0


def test_export_semantic_equivalence(imported, tmp_path):
    """Экспорт translated_only эквивалентен старому RU-дереву.

    Для каждого ключа, который (а) есть в EN и (б) переведён в старом дереве
    (ru != en, без маркера), экспортированный текст совпадает.
    """
    conn, pid, _ = imported
    out = tmp_path / "export"
    report = export_project(conn, pid, ExportOptions(mode="translated_only"), out_root=out)
    # 12 файлов целиком без переводов не пишутся вовсе
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

        # ключи старого дерева, обязанные попасть в экспорт
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
    assert checked > 3500   # достаточно массивная проверка


# --- шум проверок --------------------------------------------------------
#
# Числа сняты на этом же дереве (2026-08-10) и держатся здесь, а не только в
# документации: настройка проверок затевалась ради снижения шума, а шум —
# единственное её свойство, которое нельзя увидеть на синтетических парах.
# Дерево живое и с обновлением мода поедет, как и `EXPECTED_UNITS` выше;
# поменялись числа — сверься, что виновато обновление, а не правило.

CUSTOM = qa_rules.CUSTOM        # встроенные значения, без пресета
EXPECTED_ISSUES = {"strict": 353, CUSTOM: 149, "ck3_ru": 149, "quiet": 27}
# Главный вклад в «строгий»: эвристика длины, потому и выключена по умолчанию
EXPECTED_STRICT_LEN_RATIO = 204


def _issues(conn, pid, preset):
    return qa.run_qa(conn, pid,
                     ruleset=qa_rules.resolve({"preset": preset}, locale="ru"))


@pytest.mark.parametrize("preset,expected", sorted(EXPECTED_ISSUES.items()))
def test_issue_count_per_preset(imported, preset, expected):
    conn, pid, _ = imported
    assert len(_issues(conn, pid, preset)) == expected


def test_presets_are_monotonic_on_live_data(imported):
    """Строгий шумнее встроенного, тот — рекомендованного, тот — тихого.

    На синтетике монотонность закрыта `test_qa_defaults.py`, но там пары
    подобраны под правила. Здесь наоборот: правила встречаются с текстом,
    которого никто не подбирал.
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
