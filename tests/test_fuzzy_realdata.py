"""Скорость поиска похожих строк на настоящей базе.

Синтетика ничего не говорит о времени: узкое место — полнотекстовый запрос по
сотням тысяч записей. Берём ванильную базу CK3 из папки Bdd, копируем во
временную папку (файл пользователя не трогаем) и меряем на ней.
"""
from __future__ import annotations

import shutil
import time

import pytest

from ck3loc import project, settings
from ck3loc.core import fuzzy, tm_import

pytestmark = pytest.mark.realdata

# Запрос идёт при каждом переходе на строку, поэтому бюджет — как у отрисовки.
# Замер на ванильной базе (244 тыс. записей): ~16 мс, запас втрое.
BUDGET_MS = 50


def _biggest_base():
    bases = project.list_tm_databases(settings.bdd_dir())
    if not bases:
        return None
    return max(bases, key=lambda item: int(item[1].get("entries", 0) or 0))


@pytest.fixture(scope="module")
def indexed_base(tmp_path_factory):
    found = _biggest_base()
    if found is None:
        pytest.skip("в папке Bdd нет баз памяти переводов")
    path, meta = found
    if int(meta.get("entries", 0) or 0) < 10_000:
        pytest.skip("базы слишком малы, замер бессмысленен")
    copy = tmp_path_factory.mktemp("bdd") / path.name
    shutil.copy2(path, copy)
    tm_import.build_fts_index(copy)
    return copy, int(meta["entries"])


def test_similar_lookup_is_fast(indexed_base, tmp_path):
    path, entries = indexed_base
    conn = project.create_project(
        tmp_path / "p.ck3proj", name="P", src_root="e", tgt_root="r")
    try:
        project.attach_tm_sources(conn, [path])
        queries = [
            "The Bridge Must Be Paid",
            "Send down a dozen more spears to quiet the crowd.",
            "You are a member of the Kingsguard",
            "Grant the land to your loyal vassal",
        ]
        for q in queries:                       # прогрев кэша страниц
            fuzzy.lookup_similar(conn, q)

        started = time.perf_counter()
        for q in queries:
            fuzzy.lookup_similar(conn, q)
        per_query_ms = (time.perf_counter() - started) / len(queries) * 1000
    finally:
        conn.close()

    print(f"\nбаза {entries} записей · {per_query_ms:.1f} мс на запрос")
    assert per_query_ms < BUDGET_MS
